"""
Clinderma RAG Engine — V2 (Gemini LLM + FAISS Semantic Search + Conversation Memory)

Orchestrates:
  1. Greeting detection
  2. Phone number → Kylas CRM lead capture
  3. Order tracking intent
  4. Human agent handoff intent
  5. Grounded RAG: FAISS semantic retrieval → Gemini LLM generation → Grounding verification
"""

import re
from typing import Dict, Any
from app.core.config import settings
from app.providers.vector_provider import get_vector_store
from app.providers.llm_provider import get_llm_provider
from app.providers.crm_provider import get_crm_provider
from app.providers.order_provider import get_order_provider
from app.services.language_service import LanguageService
from app.services.handoff_manager import handoff_manager
from app.services.session_manager import session_manager
from app.models.schemas import ChatRequest, KBSource

GREETINGS = {
    "hi", "hello", "hey", "hallo", "namaste", "good morning", "good afternoon",
    "good evening", "hy", "hola", "kasa kay", "ssup", "sup", "hii", "hiii",
    "namaskar", "namaskaar"
}


class RAGEngine:
    def __init__(self):
        self.vector_store = get_vector_store()
        self.llm_provider = get_llm_provider()
        self.crm_provider = get_crm_provider()
        self.order_provider = get_order_provider()

    def process_chat(self, req: ChatRequest) -> Dict[str, Any]:
        message = req.message.strip()
        session_id = req.session_id
        detected_lang = LanguageService.detect_language(message)
        lang = req.language or detected_lang

        # Save user message to session transcript
        handoff_manager.add_transcript(session_id, "user", message)

        # ── 1. Phone Number Detection → Kylas CRM Lead Capture ──
        phone_match = re.search(r'(?:\+91[\-\s]?)?[6-9]\d{9}', message)
        if phone_match:
            phone_no = phone_match.group(0)
            self.crm_provider.create_lead(
                phone_number=phone_no,
                name="Website Visitor",
                concern=f"Captured via chat session {session_id}",
                channel=req.channel or "website"
            )
            response_text = f"Thank you! I've saved your contact number ({phone_no}) for our Skin Coach team. A dermatological expert will reach out to you shortly. 😊"
            if lang == "hi":
                response_text = f"धन्यवाद! मैंने हमारी स्किन कोच टीम के लिए आपका संपर्क नंबर ({phone_no}) सहेज लिया है। एक विशेषज्ञ जल्द ही आपसे संपर्क करेगा। 😊"
            elif lang == "mr":
                response_text = f"धन्यवाद! मी आमच्या स्किन कोच टीमसाठी तुमचा संपर्क क्रमांक ({phone_no}) जतन केला आहे. एक तज्ज्ञ लवकरच तुमच्याशी संपर्क साधेल. 😊"

            handoff_manager.add_transcript(session_id, "bot", response_text)
            return self._build_response(response_text, True, 1.0, False, None, [], lang, session_id)

        # ── 2. Greeting / Small-Talk Detection ──
        clean_msg = re.sub(r'[^\w\s]', '', message.lower().strip())
        if clean_msg in GREETINGS:
            ans = ("👋 Hello! Welcome to **Clinderma** — your dermatologist-led skincare partner.\n\n"
                   "I can help you with:\n"
                   "• 🩺 Acne & pigmentation treatment details\n"
                   "• 💊 Product usage & regimen guidance\n"
                   "• 📦 Order tracking\n"
                   "• 👩‍⚕️ Connecting you with a Skin Coach\n\n"
                   "How can I assist you today?")
            if lang == "hi":
                ans = ("👋 नमस्ते! **क्लिंडरमा** में आपका स्वागत है — आपका त्वचा विशेषज्ञ स्किनकेयर पार्टनर।\n\n"
                       "मैं आपकी मदद कर सकता हूँ:\n"
                       "• 🩺 एक्ने और पिगमेंटेशन उपचार\n"
                       "• 💊 उत्पाद उपयोग मार्गदर्शन\n"
                       "• 📦 ऑर्डर ट्रैकिंग\n"
                       "• 👩‍⚕️ स्किन कोच से कनेक्ट\n\n"
                       "आज मैं आपकी कैसे सहायता कर सकता हूँ?")
            elif lang == "mr":
                ans = ("👋 नमस्कार! **क्लिंडरमा** मध्ये आपले स्वागत — तुमचा त्वचातज्ज्ञ स्किनकेअर पार्टनर।\n\n"
                       "मी तुम्हाला मदत करू शकतो:\n"
                       "• 🩺 मुरुम आणि पिगमेंटेशन उपचार\n"
                       "• 💊 उत्पादन वापर मार्गदर्शन\n"
                       "• 📦 ऑर्डर ट्रॅकिंग\n"
                       "• 👩‍⚕️ स्किन कोचशी कनेक्ट\n\n"
                       "आज मी तुम्हाला कशी मदत करू?")

            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(ans, True, 1.0, False, None, [], lang, session_id)

        # ── 3. Order Tracking Intent ──
        if any(w in message.lower() for w in ["order", "track", "delivery", "status", "package", "clin-"]):
            order_data = self.order_provider.get_order_status(message)
            if order_data.get("found"):
                items_str = ", ".join(order_data.get("items", []))
                ans = (
                    f"📦 **Order Status for {order_data.get('order_id')}**\n\n"
                    f"• **Status**: {order_data.get('status')}\n"
                    f"• **Customer**: {order_data.get('customer_name')}\n"
                    f"• **Items**: {items_str}\n"
                    f"• **Estimated Delivery**: {order_data.get('estimated_delivery')}\n\n"
                    f"🔗 [Track your package live]({order_data.get('tracking_url')})"
                )
                handoff_manager.add_transcript(session_id, "bot", ans)
                return self._build_response(ans, True, 0.95, False, None, [], lang, session_id)

        # ── 4. Human Agent / Skin Coach Handoff Intent ──
        handoff_keywords = ["human", "agent", "skin coach", "talk to doctor", "call me",
                            "escalate", "representative", "real person", "speak to someone"]
        if any(w in message.lower() for w in handoff_keywords):
            handoff_manager.create_handoff(
                session_id=session_id,
                user_phone=req.user_phone,
                reason=f"User requested human escalation: '{message}'",
                channel=req.channel or "website"
            )
            ans = "I'm transferring your conversation to a live Clinderma Skin Coach. Please stay on this chat — an expert will join you shortly. 🩺"
            if lang == "hi":
                ans = "मैं आपकी बातचीत को एक लाइव क्लिंडरमा स्किन कोच को ट्रांसफर कर रहा हूँ। कृपया इस चैट पर बने रहें — एक विशेषज्ञ जल्द ही जुड़ेंगे। 🩺"
            elif lang == "mr":
                ans = "मी तुमचे संभाषण लाइव क्लिंडरमा स्किन कोचकडे हस्तांतरित करत आहे. कृपया या चॅटवर राहा — एक तज्ज्ञ लवकरच सामील होतील. 🩺"

            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(ans, True, 1.0, True, "User requested human handoff", [], lang, session_id)

        # ── 5. Grounded RAG: Semantic Search → LLM Generation ──

        # Retrieve relevant KB chunks via FAISS semantic search
        chunks = self.vector_store.search(message, top_k=3)

        # Get conversation history for multi-turn context
        history = session_manager.get_history(session_id)

        # Generate grounded answer via Gemini LLM
        result = self.llm_provider.generate_grounded_answer(
            query=message,
            context_chunks=chunks,
            language=lang,
            conversation_history=history
        )

        # Build KB source citations
        sources = [
            KBSource(
                id=c.get("id", ""),
                source=c.get("source", ""),
                category=c.get("category", ""),
                question=c.get("question", ""),
                score=c.get("score", 0.0)
            ) for c in chunks if c.get("score", 0) >= settings.GROUNDING_THRESHOLD
        ]

        # Trigger handoff if answer is not grounded
        if result.get("handoff_recommended") and not result.get("grounded"):
            handoff_manager.create_handoff(
                session_id=session_id,
                reason=f"Unresolved / Low confidence query: '{message}'",
                channel=req.channel or "website"
            )

        handoff_manager.add_transcript(session_id, "bot", result["answer"])

        return self._build_response(
            result["answer"], result["grounded"], result["confidence"],
            result.get("handoff_recommended", False), result.get("handoff_reason"),
            sources, lang, session_id
        )

    @staticmethod
    def _build_response(answer, grounded, confidence, handoff_rec, handoff_reason, sources, lang, session_id):
        return {
            "answer": answer,
            "grounded": grounded,
            "confidence": confidence,
            "handoff_recommended": handoff_rec,
            "handoff_reason": handoff_reason,
            "sources": sources,
            "language": lang,
            "session_id": session_id
        }


rag_engine = RAGEngine()
