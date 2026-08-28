"""
Clinderma RAG Engine — V3.1 (Multi-Source Grounded Retrieval + Conversational Query Rewriting + Dual-Intent Lead Capture)

Orchestrates:
  1. Multi-turn Session & Turn Tracking
  2. Dual Entity Extraction (Name + 10-digit Indian Mobile Number)
  3. Real-time Kylas CRM Lead Sync & SQLite Storage
  4. Conversational Query Rewriting for Multi-Turn Accuracy (eliminates follow-up amnesia)
  5. Dual-Intent Message Handling (captures contact info + answers medical question simultaneously)
  6. Greeting & Small-Talk Handling
  7. Real-time Order Tracking
  8. Explicit Skin Coach / Human Handoff Intent
  9. Multi-Source FAISS Semantic Retrieval (573 chunks: FAQs + Module + 51 Blogs + Kandid AI)
  10. Gemini 3.6 Flash Grounded Answer Generation
  11. Graceful & Concise Out-of-KB Redirection
"""

import re
from typing import Dict, Any, Optional
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

LEAD_INVITATIONS = {
    "en": "\n\n💬 *By the way, could I have your name and WhatsApp/mobile number? That way, our dermatologists and Skin Coaches can save your skin profile and share personalized routine steps with you!*",
    "hi": "\n\n💬 *वैसे, क्या मुझे आपका नाम और व्हाट्सएप/मोबाइल नंबर मिल सकता है? ताकि हमारे स्किन कोच आपके लिए एक व्यक्तिगत रूटीन तैयार कर सकें और आपसे संपर्क कर सकें!*",
    "mr": "\n\n💬 *तसेच, मला तुमचे नाव आणि व्हॉट्सअॅप/मोबाईल नंबर मिळू शकेल का? जेणेकरून आमचे स्किन कोच तुमच्या त्वचेसाठी योग्य मार्गदर्शन करू शकतील आणि संपर्क साधू शकतील!*"
}


def extract_phone(text: str) -> Optional[str]:
    """Extract a 10-digit Indian phone number with optional +91 or leading 0."""
    match = re.search(r'(?:\+91[\-\s]?)?[6-9]\d{9}', text)
    if match:
        return match.group(0).strip()
    return None


def extract_name(text: str) -> Optional[str]:
    """Extract user name from conversational phrases, submissions, and contact pairs."""
    patterns = [
        r'(?:my name is|i am|i\'m|this is|myself)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
        r'(?:name\s*[:=\-]\s*)([A-Za-z]+(?:\s+[A-Za-z]+)?)',
        r'^([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*[,|\-]?\s*(?:\+91[\-\s]?)?[6-9]\d{9}',
        r'(?:\+91[\-\s]?)?[6-9]\d{9}\s*[,|\-]?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)',
        r'^([A-Za-z]+(?:\s+[A-Za-z]+)?)$'
    ]
    stopwords = {
        "hi", "hello", "hey", "yes", "no", "ok", "okay", "thanks",
        "thank you", "please", "help", "order", "track", "what", "how",
        "why", "acne", "pimple", "skin", "coach", "doctor", "medicine",
        "treatment", "face", "cream", "sunscreen", "product", "routine"
    }
    for pat in patterns:
        m = re.search(pat, text.strip(), re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in stopwords and len(candidate) >= 2 and not any(c.isdigit() for c in candidate):
                return candidate.title()
    return None


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

        # Retrieve session context
        turn_count = session_manager.get_turn_count(session_id)
        captured_info = session_manager.get_captured_info(session_id)
        already_has_lead = session_manager.is_lead_captured(session_id)

        # ── 1. Phone & Name Extraction → Kylas CRM Lead Sync ──
        phone_no = extract_phone(message)
        name_candidate = extract_name(message) or captured_info.get("name")
        dual_intent_ack = ""

        if phone_no:
            clean_name = name_candidate or "Web Visitor"
            self.crm_provider.create_lead(
                phone_number=phone_no,
                name=clean_name,
                concern=f"Captured via chat session {session_id}",
                channel=req.channel or "website"
            )
            handoff_manager.update_user_contact(session_id, user_name=clean_name, user_phone=phone_no)

            disp_name = f", {clean_name}" if clean_name and clean_name != "Web Visitor" else ""
            clean_digits = re.sub(r'[^\d]', '', message)

            # If user message was ONLY providing contact info (short message):
            if len(clean_digits) >= 10 and len(message.split()) <= 8:
                if lang == "hi":
                    resp = f"धन्यवाद{disp_name}! मैंने आपकी जानकारी ({phone_no}) सहेज ली है। हमारी क्लिंडरमा स्किन कोच टीम जल्द ही आपसे संपर्क करेगी। 🩺\n\nक्या आपकी त्वचा या रूटीन के बारे में ऐसा कुछ है जो आप अभी मुझसे पूछना चाहते हैं?"
                elif lang == "mr":
                    resp = f"धन्यवाद{disp_name}! मी तुमची माहिती ({phone_no}) जतन केली आहे. आमची क्लिंडरमा स्किन कोच टीम लवकरच तुमच्याशी संपर्क साधेल. 🩺\n\nतुमच्या त्वचेबद्दल किंवा रूटीनबद्दल मला आणखी काही विचारायचे आहे का?"
                else:
                    resp = f"Thank you{disp_name}! I've saved your details ({phone_no}). Our Clinderma Skin Coach team has your contact information and will be happy to assist you directly. 🩺\n\nIs there anything specific about your skin or routine you'd like to ask me right now?"

                handoff_manager.add_transcript(session_id, "bot", resp)
                return self._build_response(resp, True, 1.0, False, None, [], lang, session_id)
            else:
                # Dual intent: Contact info provided alongside a clinical question
                if lang == "hi":
                    dual_intent_ack = f"धन्यवाद{disp_name}! मैंने आपका नंबर ({phone_no}) हमारी स्किन कोच टीम के लिए सुरक्षित कर लिया है। 🩺\n\n"
                elif lang == "mr":
                    dual_intent_ack = f"धन्यवाद{disp_name}! मी तुमचा नंबर ({phone_no}) आमच्या स्किन कोच टीमसाठी सेव्ह केला आहे. 🩺\n\n"
                else:
                    dual_intent_ack = f"Thank you{disp_name}! I've saved your contact details ({phone_no}) for our Clinderma Skin Coach team. 🩺\n\n"

        # If user only gave their name in response to a previous prompt:
        if name_candidate and not phone_no and not already_has_lead and turn_count in (2, 3, 4) and len(message.split()) <= 4:
            handoff_manager.update_user_contact(session_id, user_name=name_candidate)
            if lang == "hi":
                resp = f"आपसे मिलकर अच्छा लगा, {name_candidate}! क्या मुझे आपका 10-अंकों का व्हाट्सएप/मोबाइल नंबर भी मिल सकता है? ताकि हमारे स्किन कोच आपकी स्किन रिपोर्ट भेज सकें। 😊"
            elif lang == "mr":
                resp = f"तुम्हाला भेटून आनंद झाला, {name_candidate}! मला तुमचा 10-अंकी व्हॉट्सअॅप/मोबाईल नंबर मिळू शकेल का? जेणेकरून आमचे स्किन कोच तुमचा रिपोर्ट शेअर करू शकतील. 😊"
            else:
                resp = f"Nice to meet you, {name_candidate}! Could I also have your 10-digit WhatsApp/mobile number? That way our Skin Coach team can send over your personalized routine notes. 😊"

            handoff_manager.add_transcript(session_id, "bot", resp)
            return self._build_response(resp, True, 1.0, False, None, [], lang, session_id)

        # ── 2. Greeting / Small-Talk Detection ──
        clean_msg = re.sub(r'[^\w\s]', '', message.lower().strip())
        if clean_msg in GREETINGS:
            ans = ("👋 Hello! Welcome to **Clinderma** — your dermatologist-led skincare partner.\n\n"
                   "I can help you with:\n"
                   "• 🩺 Acne & pigmentation treatment details\n"
                   "• 🌿 Ingredients, moisturizers & barrier repair\n"
                   "• 📦 Order tracking\n"
                   "• 👩‍⚕️ Connecting with a Skin Coach\n\n"
                   "How can I assist you with your skin today?")
            if lang == "hi":
                ans = ("👋 नमस्ते! **क्लिंडरमा** में आपका स्वागत है — आपका त्वचा विशेषज्ञ स्किनकेयर पार्टनर।\n\n"
                       "मैं आपकी मदद कर सकता हूँ:\n"
                       "• 🩺 एक्ने और पिगमेंटेशन उपचार\n"
                       "• 🌿 स्किनकेयर सामग्री और बैरियर रिपेयर\n"
                       "• 📦 ऑर्डर ट्रैकिंग\n"
                       "• 👩‍⚕️ स्किन कोच से कनेक्ट\n\n"
                       "आज मैं आपकी त्वचा की देखभाल में कैसे सहायता कर सकता हूँ?")
            elif lang == "mr":
                ans = ("👋 नमस्कार! **क्लिंडरमा** मध्ये आपले स्वागत — तुमचा त्वचातज्ज्ञ स्किनकेअर पार्टनर।\n\n"
                       "मी तुम्हाला मदत करू शकतो:\n"
                       "• 🩺 मुरुम आणि पिगमेंटेशन उपचार\n"
                       "• 🌿 स्किनकेअर घटक आणि बॅरियर रिपेअर\n"
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
                user_phone=req.user_phone or phone_no,
                reason=f"User requested human escalation: '{message}'",
                channel=req.channel or "website"
            )
            ans = "I'm connecting your conversation with a live Clinderma Skin Coach. Please stay on this chat — a skincare expert will join you shortly. 🩺"
            if not already_has_lead and not phone_no:
                ans += "\n\nCould you please share your **Name** and **Mobile Number** so our team can follow up with your consultation?"
            if lang == "hi":
                ans = "मैं आपकी बातचीत को एक लाइव क्लिंडरमा स्किन कोच से जोड़ रहा हूँ। कृपया इस चैट पर बने रहें — एक विशेषज्ञ जल्द ही जुड़ेंगे। 🩺"
                if not already_has_lead and not phone_no:
                    ans += "\n\nकृपया अपना **नाम** और **मोबाइल नंबर** साझा करें ताकि हमारी टीम आपसे संपर्क कर सके।"
            elif lang == "mr":
                ans = "मी तुमचे संभाषण लाइव क्लिंडरमा स्किन कोचशी जोडत आहे. कृपया या चॅटवर राहा — एक तज्ज्ञ लवकरच सामील होतील. 🩺"
                if not already_has_lead and not phone_no:
                    ans += "\n\nकृपया तुमचे **नाव** आणि **मोबाईल नंबर** शेअर करा जेणेकरून आमची टीम तुमच्याशी संपर्क साधू शकेल."

            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(ans, True, 1.0, True, "User requested human handoff", [], lang, session_id)

        # ── 5. Multi-Source Grounded RAG: Conversational Search → LLM Generation ──
        history = session_manager.get_history(session_id)
        prior_history = history[:-1] if len(history) > 1 else []

        # Condense follow-up questions only when prior multi-turn context exists
        if prior_history and turn_count > 1:
            search_query = self.llm_provider.condense_query(message, prior_history)
        else:
            search_query = message

        chunks = self.vector_store.search(search_query, top_k=3)

        # Fallback to raw message if condensed query returned no chunks or sub-threshold score
        if not chunks or (chunks and chunks[0].get("score", 0.0) < settings.GROUNDING_THRESHOLD and search_query != message):
            fallback_chunks = self.vector_store.search(message, top_k=3)
            if fallback_chunks and fallback_chunks[0].get("score", 0.0) > (chunks[0].get("score", 0.0) if chunks else 0.0):
                chunks = fallback_chunks

        result = self.llm_provider.generate_grounded_answer(
            query=message,
            context_chunks=chunks,
            language=lang,
            conversation_history=history
        )

        final_answer = result["answer"]
        is_grounded = result.get("grounded", False)
        sources = []

        if is_grounded:
            sources = [
                KBSource(
                    id=c.get("id", ""),
                    source=c.get("source", ""),
                    category=c.get("category", ""),
                    question=c.get("question", ""),
                    score=c.get("score", 0.0)
                ) for c in chunks if c.get("score", 0) >= settings.GROUNDING_THRESHOLD
            ]

            # Prepend dual-intent acknowledgement if contact was shared alongside the question
            if dual_intent_ack:
                final_answer = f"{dual_intent_ack}{final_answer}"

            # ── Natural Turn-Based Lead Prompting (Turns 2-3) ──
            # If user hasn't provided contact details yet and conversation is ongoing:
            elif turn_count in (2, 3) and not already_has_lead and not phone_no:
                invitation = LEAD_INVITATIONS.get(lang, LEAD_INVITATIONS["en"])
                final_answer = f"{final_answer}{invitation}"

        else:
            # Out-of-KB query: Register handoff in background
            handoff_manager.create_handoff(
                session_id=session_id,
                reason=f"Out-of-scope / Unresolved query: '{message}'",
                channel=req.channel or "website"
            )

        handoff_manager.add_transcript(session_id, "bot", final_answer)

        return self._build_response(
            final_answer, is_grounded, result.get("confidence", 0.0),
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
