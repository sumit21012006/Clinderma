"""
Clinderma LLM Provider — V2 (Gemini 2.0 Flash + Grounded System Prompt)

Pluggable provider architecture:
  - GeminiLLMProvider: Production Gemini 2.0 Flash with strict grounding & multi-lingual
  - LocalGroundedLLMProvider: Fallback text formatter (no external LLM needed)
"""

from typing import List, Dict, Any
from app.providers.base import AbstractLLMProvider
from app.core.config import settings

# ── Clinderma Grounded System Prompt ──
CLINDERMA_SYSTEM_PROMPT = """You are Clinderma's official AI dermatology assistant. You MUST follow these rules strictly:

## IDENTITY
- You represent Clinderma, a dermatologist-led skin treatment platform combining Modern Dermatology, Ayurveda, and Targeted Nutrition.
- You are warm, professional, empathetic, and medically precise.

## GROUNDING RULES (CRITICAL — ZERO HALLUCINATION POLICY)
- You MUST answer ONLY using the CONTEXT provided below. Do NOT use any external knowledge.
- If the context does not contain enough information to answer the question, you MUST say:
  "I don't have that specific information in my knowledge base. Would you like me to connect you with a Clinderma Skin Coach for personalized assistance?"
- NEVER guess, assume, or make up medical information.
- NEVER recommend specific medicines, dosages, or treatments not mentioned in the context.

## RESPONSE STYLE
- Keep answers concise (2-4 sentences for simple questions, more for complex ones).
- Use bullet points for lists.
- Be encouraging and supportive about the treatment journey.
- Address the patient's concern directly without unnecessary preamble.

## LANGUAGE
- Respond in the SAME language the user writes in.
- If the user writes in Hindi (हिन्दी), respond naturally in Hindi.
- If the user writes in Marathi (मराठी), respond naturally in Marathi.
- If the user writes in English, respond in English.
- If the user writes in Hinglish (mixed Hindi-English), respond in Hinglish.

## TONE
- Never promise guaranteed results for pigmentation.
- For acne, you can mention the money-back guarantee if relevant.
- Never promise instant results.
- Under-promise and over-deliver.
- Always set expectations: Acne improves faster than pigmentation.
"""

FALLBACK_RESPONSES = {
    "en": "I don't have that specific information in my knowledge base. Would you like me to connect you with a Clinderma Skin Coach for personalized assistance?",
    "hi": "मेरे पास मेरे ज्ञान कोष में यह विशिष्ट जानकारी नहीं है। क्या आप चाहेंगे कि मैं आपको व्यक्तिगत सहायता के लिए क्लिंडरमा स्किन कोच से जोड़ूं?",
    "mr": "माझ्याकडे माझ्या ज्ञानकोशात ही विशिष्ट माहिती नाही. तुम्हाला वैयक्तिक मदतीसाठी क्लिंडरमा स्किन कोचशी जोडू इच्छिता का?"
}


class GeminiLLMProvider(AbstractLLMProvider):
    """
    Production LLM provider using Gemini 2.0 Flash.
    Generates natural, grounded, multi-lingual answers from retrieved KB context.
    """

    def __init__(self):
        from google import genai
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.LLM_MODEL

    def generate_grounded_answer(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        language: str = "en",
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:

        lang = language.lower() if language in ["en", "hi", "mr"] else "en"

        # If no context chunks found, return grounded fallback immediately
        if not context_chunks:
            return {
                "answer": FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"]),
                "grounded": False,
                "confidence": 0.0,
                "handoff_recommended": True,
                "handoff_reason": "No relevant KB context found for this query."
            }

        top_score = context_chunks[0].get("score", 0.0)

        # If top score is below grounding threshold, don't even send to LLM
        if top_score < settings.GROUNDING_THRESHOLD:
            return {
                "answer": FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"]),
                "grounded": False,
                "confidence": round(top_score, 4),
                "handoff_recommended": True,
                "handoff_reason": f"Top retrieval score ({top_score:.2f}) below threshold ({settings.GROUNDING_THRESHOLD})."
            }

        # Build context from retrieved KB chunks
        context_parts = []
        for i, chunk in enumerate(context_chunks):
            context_parts.append(
                f"--- Source {i+1} (Category: {chunk.get('category', 'N/A')}) ---\n"
                f"Question: {chunk.get('question', '')}\n"
                f"Answer: {chunk.get('answer', '')}\n"
            )
        context_text = "\n".join(context_parts)

        # Build message history for multi-turn context
        messages = []
        if conversation_history:
            for msg in conversation_history[-settings.MAX_HISTORY_TURNS:]:
                role = "user" if msg.get("sender") == "user" else "model"
                messages.append({"role": role, "parts": [{"text": msg.get("message", "")}]})

        # Current user query with context
        user_prompt = f"""## RETRIEVED CONTEXT FROM CLINDERMA KNOWLEDGE BASE:

{context_text}

## USER'S QUESTION:
{query}

Answer the user's question ONLY using the context above. Follow all grounding and language rules from your system instructions."""

        messages.append({"role": "user", "parts": [{"text": user_prompt}]})

        try:
            import time

            # Retry with exponential backoff for rate limit errors
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=messages,
                        config={
                            "system_instruction": CLINDERMA_SYSTEM_PROMPT,
                            "temperature": 0.3,
                            "max_output_tokens": 1024,
                        }
                    )

                    answer = response.text.strip() if response.text else FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"])

                    # Determine handoff recommendation based on confidence
                    handoff_rec = top_score < 0.65
                    handoff_reason = "Moderate confidence — human verification available." if handoff_rec else None

                    return {
                        "answer": answer,
                        "grounded": True,
                        "confidence": round(top_score, 4),
                        "handoff_recommended": handoff_rec,
                        "handoff_reason": handoff_reason
                    }

                except Exception as retry_err:
                    err_str = str(retry_err)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        wait_time = (attempt + 1) * 5
                        print(f"[GeminiLLM] Rate limited, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise retry_err

            # All retries exhausted — fall back to raw KB text
            print(f"[GeminiLLM] All retries exhausted, returning raw KB text")
            fallback_answer = context_chunks[0].get("answer", FALLBACK_RESPONSES["en"])
            return {
                "answer": f"**{context_chunks[0].get('question', '')}**\n\n{fallback_answer}",
                "grounded": True,
                "confidence": round(top_score, 4),
                "handoff_recommended": False,
                "handoff_reason": "LLM rate limited, returning raw KB answer."
            }

        except Exception as e:
            print(f"[GeminiLLM] Generation error: {e}")
            fallback_answer = context_chunks[0].get("answer", FALLBACK_RESPONSES["en"])
            return {
                "answer": f"**{context_chunks[0].get('question', '')}**\n\n{fallback_answer}",
                "grounded": True,
                "confidence": round(top_score, 4),
                "handoff_recommended": False,
                "handoff_reason": f"LLM generation failed ({e}), returning raw KB text."
            }


class LocalGroundedLLMProvider(AbstractLLMProvider):
    """Fallback: Returns raw KB text without LLM processing (zero API cost)."""

    def generate_grounded_answer(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        language: str = "en",
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:

        lang = language.lower() if language in ["en", "hi", "mr"] else "en"

        if not context_chunks:
            return {
                "answer": FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"]),
                "grounded": False,
                "confidence": 0.0,
                "handoff_recommended": True,
                "handoff_reason": "No matching knowledge base entry found."
            }

        top_match = context_chunks[0]
        score = top_match.get("score", 0.0)

        if score < settings.GROUNDING_THRESHOLD:
            return {
                "answer": FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"]),
                "grounded": False,
                "confidence": round(score, 4),
                "handoff_recommended": True,
                "handoff_reason": f"Score ({score}) below threshold."
            }

        answer_text = top_match.get("answer", "")
        formatted_answer = f"**{top_match.get('question', '')}**\n\n{answer_text}"

        return {
            "answer": formatted_answer,
            "grounded": True,
            "confidence": round(score, 4),
            "handoff_recommended": score < 0.65,
            "handoff_reason": "Moderate confidence." if score < 0.65 else None
        }


def get_llm_provider() -> AbstractLLMProvider:
    """Factory function — selects LLM provider based on .env configuration."""
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        return GeminiLLMProvider()
    else:
        return LocalGroundedLLMProvider()
