"""
Clinderma LLM Provider — V3 (Gemini 2.0 Flash + Strict Multi-Source Grounding)

Pluggable provider architecture:
  - GeminiLLMProvider: Production Gemini 2.0 Flash with strict anti-hallucination grounding,
                       multi-source clinical context (FAQs, Module, Blogs, Kandid),
                       and natural multi-lingual capabilities.
  - LocalGroundedLLMProvider: Fallback text formatter (100% offline).
"""

import time
from typing import List, Dict, Any
from app.providers.base import AbstractLLMProvider
from app.core.config import settings

# ── Clinderma Grounded System Prompt ──
CLINDERMA_SYSTEM_PROMPT = """You are Clinderma's official AI Dermatology & Customer Support Assistant.

## IDENTITY & PHILOSOPHY
- You represent Clinderma, a premier dermatologist-led skin treatment platform in India.
- Clinderma treats acne, pigmentation, and barrier concerns as medical conditions (not cosmetic issues) by combining Modern Dermatology, Ayurveda, and Targeted Nutrition.
- You are warm, empathetic, medically accurate, and conversational.

## ZERO-HALLUCINATION & STRICT GROUNDING RULES
1. Answer ONLY using the provided RETRIEVED CONTEXT below (comprising Master FAQs, Clinical Modules, Clinderma Clinical Blogs, and Verified Product Guides).
2. NEVER guess, assume, or fabricate medical advice, diagnoses, or ingredient recommendations that are not present in the context.
3. If the context does not contain sufficient details to answer the user's specific question, DO NOT invent facts. Acknowledge what you can, and clearly state that a Clinderma Skin Coach can provide direct personalized guidance.
4. For general skin guidance (e.g. sunscreen, moisturizers, comedones, pregnancy acne, eyebrow pimples, forehead bumps), provide the clinical facts explained in the context clearly and encouragingly.

## TONE & COMMUNICATION
- Warm, polite, and encouraging. Never sound like a robotic search engine.
- Address the user's concern directly in 2 to 4 concise paragraphs or clean bullet points.
- Under-promise and over-deliver: Acne improves faster (typically 6-8 weeks for initial changes, 3-4 months for stability); Pigmentation takes longer (3-6 months). Never guarantee 100% instant cures.

## LANGUAGE ADAPTATION
- Always respond in the EXACT same language as the user's message:
  - English -> English
  - Hindi (हिन्दी) -> Natural, fluent Hindi
  - Marathi (मराठी) -> Natural, fluent Marathi
  - Hinglish -> Conversational Hinglish
"""

OUT_OF_KB_MESSAGES = {
    "en": (
        "I specialize in Clinderma's dermatologist-led skin treatments, acne, pigmentation, and routine guidance. "
        "I don't have verified clinical information regarding that specific query in my knowledge base.\n\n"
        "I'd be glad to connect you with one of our Clinderma Skin Coaches for personalized assistance! "
        "Could you please share your **Name** and **Mobile Number** so our customer care team can reach out to you? 🩺"
    ),
    "hi": (
        "मैं क्लिंडरमा के त्वचा विशेषज्ञ उपचार, मुँहासे, पिगमेंटेशन और स्किनकेयर रूटीन में माहिर हूँ। "
        "मेरे ज्ञानकोष में इस विशिष्ट विषय के बारे में सत्यापित जानकारी उपलब्ध नहीं है।\n\n"
        "मुझे खुशी होगी अगर हमारे क्लिंडरमा स्किन कोच सीधे आपकी मदद करें! "
        "क्या आप अपना **नाम** और **मोबाइल नंबर** साझा कर सकते हैं ताकि हमारी टीम आपसे संपर्क कर सके? 🩺"
    ),
    "mr": (
        "मी क्लिंडरमाच्या त्वचातज्ज्ञ उपचार, मुरुम, पिगमेंटेशन आणि स्किनकेअर मार्गदर्शनात मदत करतो. "
        "माझ्या ज्ञानकोशात या विशिष्ट विषयाबद्दल माहिती उपलब्ध नाही.\n\n"
        "आमच्या क्लिंडरमा स्किन कोचकडून थेट वैयक्तिक मार्गदर्शन मिळवण्यासाठी, "
        "कृपया तुमचे **नाव** आणि **मोबाईल नंबर** शेअर करू शकता का? 🩺"
    )
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

    def condense_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Condenses a conversational follow-up query with past context into a standalone search query.
        E.g. History: ["Can I use retinol?"], Query: "How often should I use it?" -> "How often should I use retinol for acne?"
        """
        if not conversation_history or len(conversation_history) == 0:
            return query

        clean_q = query.strip()
        words = clean_q.split()
        relative_markers = ["it", "this", "that", "these", "those", "how often", "when", "why", "where", "what about", "is it", "can i", "and", "also", "how to use", "side effects"]
        is_relative = len(words) <= 7 or any(m in clean_q.lower() for m in relative_markers)

        if not is_relative:
            return query

        try:
            recent_turns = conversation_history[-4:]
            hist_str = "\n".join([f"{m.get('sender', 'user')}: {m.get('message', '')[:140]}" for m in recent_turns])

            prompt = f"""Given the following conversation history between a user and a skincare assistant, rephrase the user's latest follow-up question into a standalone, concise skincare search query that captures the subject/topic. If it is already standalone, return it unchanged. Do NOT answer the question, return ONLY the standalone search query.

Conversation History:
{hist_str}

User's Latest Query: {clean_q}
Standalone Search Query:"""

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 40,
                }
            )
            condensed = response.text.strip().replace('"', '').replace("'", "") if response.text else query
            if len(condensed) >= 3 and len(condensed.split()) <= 15:
                return condensed
        except Exception:
            pass

        return query

    def generate_grounded_answer(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        language: str = "en",
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:

        lang = language.lower() if language in ["en", "hi", "mr"] else "en"
        fallback_text = OUT_OF_KB_MESSAGES.get(lang, OUT_OF_KB_MESSAGES["en"])


        # ── STRICT GROUNDING CHECK: Enforce threshold BEFORE calling LLM API ──
        if not context_chunks:
            return {
                "answer": fallback_text,
                "grounded": False,
                "confidence": 0.0,
                "handoff_recommended": True,
                "handoff_reason": "No relevant KB context found for this query."
            }

        top_score = float(context_chunks[0].get("score", 0.0))

        # Refuse queries whose vector similarity is below the grounding threshold (e.g. 0.58)
        if top_score < settings.GROUNDING_THRESHOLD:
            return {
                "answer": fallback_text,
                "grounded": False,
                "confidence": round(top_score, 4),
                "handoff_recommended": True,
                "handoff_reason": f"Top retrieval score ({top_score:.2f}) below grounding threshold ({settings.GROUNDING_THRESHOLD})."
            }

        # Build rich context from retrieved KB chunks
        context_parts = []
        for i, chunk in enumerate(context_chunks):
            source_label = chunk.get('source', 'Knowledge Base')
            category_label = chunk.get('category', 'Clinical Knowledge')
            context_parts.append(
                f"--- Source {i+1}: [{source_label} | {category_label}] ---\n"
                f"Question / Topic: {chunk.get('question', '')}\n"
                f"Content: {chunk.get('answer', '')}\n"
            )
        context_text = "\n".join(context_parts)

        # Build message history for multi-turn context
        messages = []
        if conversation_history:
            for msg in conversation_history[-settings.MAX_HISTORY_TURNS:]:
                role = "user" if msg.get("sender") == "user" else "model"
                messages.append({"role": role, "parts": [{"text": msg.get("message", "")}]})

        user_prompt = f"""## RETRIEVED CONTEXT FROM CLINDERMA KNOWLEDGE BASE:

{context_text}

## USER'S QUESTION:
{query}

Answer the user's question accurately, naturally, and warmly using ONLY the context provided above. Follow all grounding, clinical nuance, and language matching rules from your system instructions."""

        messages.append({"role": "user", "parts": [{"text": user_prompt}]})

        # Generate response with Gemini LLM
        try:
            max_retries = 1
            for attempt in range(max_retries + 1):
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

                    answer = response.text.strip() if response.text else fallback_text
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
                    if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries:
                        time.sleep(1.5)
                        continue
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        break
                    else:
                        raise retry_err

        except Exception as e:
            print(f"[GeminiLLM] Generation error: {e}")

        # Grounded Fallback: Return raw KB text ONLY if query passed grounding threshold
        fallback_q = context_chunks[0].get("question", "")
        fallback_answer = context_chunks[0].get("answer", fallback_text)
        return {
            "answer": f"**{fallback_q}**\n\n{fallback_answer}",
            "grounded": True,
            "confidence": round(top_score, 4),
            "handoff_recommended": False,
            "handoff_reason": "Gemini rate limited — grounded KB fallback returned."
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
        fallback_text = OUT_OF_KB_MESSAGES.get(lang, OUT_OF_KB_MESSAGES["en"])

        if not context_chunks:
            return {
                "answer": fallback_text,
                "grounded": False,
                "confidence": 0.0,
                "handoff_recommended": True,
                "handoff_reason": "No matching knowledge base entry found."
            }

        top_match = context_chunks[0]
        score = float(top_match.get("score", 0.0))

        if score < settings.GROUNDING_THRESHOLD:
            return {
                "answer": fallback_text,
                "grounded": False,
                "confidence": round(score, 4),
                "handoff_recommended": True,
                "handoff_reason": f"Score ({score:.2f}) below threshold ({settings.GROUNDING_THRESHOLD})."
            }

        answer_text = top_match.get("answer", "")
        formatted_answer = f"**{top_match.get('question', '')}**\n\n{answer_text}"

        return {
            "answer": formatted_answer,
            "grounded": True,
            "confidence": round(score, 4),
            "handoff_recommended": False,
            "handoff_reason": None
        }


def get_llm_provider() -> AbstractLLMProvider:
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        return GeminiLLMProvider()
    else:
        return LocalGroundedLLMProvider()
