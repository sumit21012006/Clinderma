"""
Clinderma RAG Engine — V3.1 (Multi-Source Grounded Retrieval + Conversational Query Rewriting + Dual-Intent Lead Capture)

Orchestrates:
  1. Multi-turn Session & Turn Tracking
  2. Dual Entity Extraction (Name + 10-digit Indian Mobile Number)
  3. Real-time Kylas CRM Lead Sync & SQLite Storage
  4. Conversational Query Rewriting for Multi-Turn Accuracy (eliminates follow-up amnesia)
  5. Dual-Intent Message Handling (captures contact info + answers medical question simultaneously)
  6. Greeting & Small-Talk Handling
  7. Explicit Product/Shop Recommendations
  8. Explicit Skin Coach / Human Handoff Intent
  9. Multi-Source FAISS Semantic Retrieval (573 chunks: FAQs + Module + 51 Blogs + Kandid AI)
  10. Gemini Grounded Answer Generation
  11. Graceful & Concise Out-of-KB Redirection
"""

import re
from typing import Dict, Any, Optional
from app.core.config import settings
from app.providers.vector_provider import get_vector_store
from app.providers.llm_provider import get_llm_provider
from app.providers.crm_provider import get_crm_provider
from app.services.language_service import LanguageService
from app.services.handoff_manager import handoff_manager
from app.services.session_manager import session_manager
from app.models.schemas import ChatRequest, KBSource

GREETINGS = {
    "hi", "hello", "hey", "hallo", "namaste", "good morning", "good afternoon",
    "good evening", "hy", "hola", "kasa kay", "ssup", "sup", "hii", "hiii",
    "namaskar", "namaskaar"
}

SKIN_TEST_LINKS = {
    "en": "[Take the Clinderma skin test](https://www.theclinderma.com/en/skin-test)",
    "hi": "[क्लिंडरमा स्किन टेस्ट लें](https://www.theclinderma.com/hi/skin-test)",
    "mr": "[क्लिंडरमा स्किन टेस्ट घ्या](https://www.theclinderma.com/mr/skin-test)",
}

PHONE_PROMPTS = {
    "en": "Before we continue, please share your 10-digit WhatsApp/mobile number. This helps us keep your chat connected and you won’t be asked again when you start a new chat.",
    "hi": "आगे बढ़ने से पहले कृपया अपना 10-अंकों का व्हाट्सऐप/मोबाइल नंबर साझा करें। इससे आपकी चैट जुड़ी रहेगी और नई चैट शुरू करने पर नंबर दोबारा नहीं माँगा जाएगा।",
    "mr": "पुढे जाण्यापूर्वी कृपया तुमचा 10-अंकी व्हॉट्सअॅप/मोबाईल नंबर शेअर करा. यामुळे तुमची चॅट जोडलेली राहील आणि नवीन चॅट सुरू केल्यावर नंबर पुन्हा विचारला जाणार नाही.",
}

SHOP_URL = "https://www.theclinderma.com/en/shop"
PRODUCT_INTENT_WORDS = (
    "product", "products", "kit", "cream", "serum", "recommend", "suggest", "buy", "shop",
    "उत्पाद", "क्रीम", "सीरम", "किट", "प्रोडक्ट", "खरीद", "उत्पादन", "खरेदी",
)
DARK_SPOT_WORDS = (
    "dark spot", "dark spots", "acne mark", "acne marks", "pigmentation", "uneven tone",
    "काले दाग", "दाग", "पिगमेंटेशन", "काळे डाग", "डाग",
)
ACNE_WORDS = ("acne", "pimple", "breakout", "मुँहास", "पिंपल", "एक्ने", "मुरुम")


def skin_test_cta(lang: str) -> str:
    return SKIN_TEST_LINKS.get(lang, SKIN_TEST_LINKS["en"])


def phone_prompt(lang: str) -> str:
    return PHONE_PROMPTS.get(lang, PHONE_PROMPTS["en"])


def has_product_intent(message: str) -> bool:
    lowered = message.lower()
    return any(word in lowered for word in PRODUCT_INTENT_WORDS)


def has_order_intent(message: str) -> bool:
    lowered = message.lower()
    phrases = ("track my order", "track order", "order status", "delivery status", "my delivery", "my package")
    return any(phrase in lowered for phrase in phrases) or "clin-" in lowered


def product_recommendation(message: str, lang: str) -> str:
    lowered = message.lower()
    if any(word in lowered for word in DARK_SPOT_WORDS):
        if lang == "hi":
            return ("डार्क स्पॉट्स या पिंपल के निशानों के लिए क्लिंडरमा शॉप पर [Epifade Cream](https://www.theclinderma.com/en/products/epifade-cream) उपलब्ध है। "
                    "यदि एक्ने के साथ पिगमेंटेशन भी है, तो [Anti-Acne + Pigmentation Kit](https://www.theclinderma.com/en/products/anti-acne-pigmentation-kit-calm-gut-reset) एक विकल्प है, लेकिन इसमें प्रिस्क्रिप्शन जेल है। "
                    "इसे खरीदने या इस्तेमाल करने से पहले स्किन टेस्ट और त्वचा विशेषज्ञ की समीक्षा कराएँ।")
        if lang == "mr":
            return ("डार्क स्पॉट्स किंवा मुरुमांच्या डागांसाठी क्लिंडरमा शॉपमध्ये [Epifade Cream](https://www.theclinderma.com/en/products/epifade-cream) उपलब्ध आहे. "
                    "मुरुमांसोबत पिगमेंटेशनही असल्यास [Anti-Acne + Pigmentation Kit](https://www.theclinderma.com/en/products/anti-acne-pigmentation-kit-calm-gut-reset) हा पर्याय आहे, पण त्यात प्रिस्क्रिप्शन जेल आहे. "
                    "खरेदी किंवा वापरापूर्वी स्किन टेस्ट आणि त्वचातज्ज्ञांचा सल्ला घ्या.")
        return ("For dark spots or post-acne marks, Clinderma’s shop lists [Epifade Cream](https://www.theclinderma.com/en/products/epifade-cream). "
                "If you also have active acne, the [Anti-Acne + Pigmentation Kit](https://www.theclinderma.com/en/products/anti-acne-pigmentation-kit-calm-gut-reset) is another option, but it contains a prescription acne gel. "
                "Because the right choice depends on your skin and current routine, take the skin test and get a dermatologist review before purchasing or using it.")

    if any(word in lowered for word in ACNE_WORDS):
        if lang == "hi":
            return ("एक्ने-प्रोन त्वचा के लिए क्लिंडरमा शॉप पर [Acnetrol Moisturiser](https://www.theclinderma.com/en/products/acnetrol-moisturiser) और [Anti-Acne Kit – Cleanse + Gut + Calm](https://www.theclinderma.com/en/products/anti-acne-kit-cleanse-gut-calm) उपलब्ध हैं। "
                    "किट में प्रिस्क्रिप्शन एक्ने जेल है और यह गर्भावस्था या स्तनपान के दौरान उपयुक्त नहीं है। "
                    "आपकी त्वचा के लिए सही विकल्प तय करने से पहले स्किन टेस्ट और त्वचा विशेषज्ञ की समीक्षा जरूरी है।")
        if lang == "mr":
            return ("मुरुम-प्रवण त्वचेसाठी क्लिंडरमा शॉपमध्ये [Acnetrol Moisturiser](https://www.theclinderma.com/en/products/acnetrol-moisturiser) आणि [Anti-Acne Kit – Cleanse + Gut + Calm](https://www.theclinderma.com/en/products/anti-acne-kit-cleanse-gut-calm) उपलब्ध आहेत. "
                    "किटमध्ये प्रिस्क्रिप्शन मुरुमांचे जेल आहे आणि ते गर्भावस्था किंवा स्तनपानाच्या काळात योग्य नाही. "
                    "योग्य पर्याय ठरवण्यापूर्वी स्किन टेस्ट आणि त्वचातज्ज्ञांचा आढावा आवश्यक आहे.")
        return ("For acne-prone skin, Clinderma’s shop lists [Acnetrol Moisturiser](https://www.theclinderma.com/en/products/acnetrol-moisturiser) and the [Anti-Acne Kit – Cleanse + Gut + Calm](https://www.theclinderma.com/en/products/anti-acne-kit-cleanse-gut-calm). "
                "The kit contains a prescription acne gel and is not suitable during pregnancy or breastfeeding. "
                "Because active acne and skin sensitivity vary, complete the skin test and get a dermatologist review before choosing or using a treatment kit.")

    if lang == "hi":
        return f"क्लिंडरमा के क्लींजर, मॉइस्चराइज़र, एक्ने केयर और उपचार किट [आधिकारिक शॉप]({SHOP_URL}) पर उपलब्ध हैं। सही उत्पाद आपकी त्वचा, एक्ने की स्थिति, पिगमेंटेशन और मौजूदा रूटीन पर निर्भर करता है। बिना जाँच के कोई प्रिस्क्रिप्शन उत्पाद शुरू न करें; पहले स्किन टेस्ट पूरा करें ताकि उपयुक्त विकल्प की समीक्षा की जा सके।"
    if lang == "mr":
        return f"क्लिंडरमाचे क्लींजर, मॉइश्चरायझर, मुरुमांसाठीची उत्पादने आणि ट्रीटमेंट किट [अधिकृत शॉप]({SHOP_URL}) वर उपलब्ध आहेत. योग्य पर्याय तुमची त्वचा, मुरुमांची स्थिती, पिगमेंटेशन आणि सध्याची रुटीन यावर अवलंबून असतो. तपासणीशिवाय प्रिस्क्रिप्शन उत्पादन सुरू करू नका; प्रथम स्किन टेस्ट पूर्ण करा."
    return (f"Clinderma’s cleansers, moisturisers, acne care, and treatment kits are available in the [official shop]({SHOP_URL}). "
            "The best match depends on your skin type, whether you have active acne or pigmentation, and what you already use. "
            "Please don’t start a prescription product without review; complete the skin test first so the appropriate options can be checked for you.")


def suggested_questions(message: str, lang: str):
    lowered = message.lower()
    if lang == "hi":
        return ["एक्ने के इलाज में कितना समय लगता है?", "डार्क स्पॉट्स के लिए कौन सा क्लिंडरमा उत्पाद है?"]
    if lang == "mr":
        return ["मुरुमांच्या उपचाराला किती वेळ लागतो?", "डार्क स्पॉट्ससाठी कोणते क्लिंडरमा उत्पादन आहे?"]
    if any(word in lowered for word in DARK_SPOT_WORDS):
        return ["How long do dark spots take to fade?", "Which Clinderma product is for dark spots?"]
    if "acne" in lowered or "pimple" in lowered:
        return ["How long will acne treatment take?", "What causes recurring acne?"]
    return ["How does Clinderma treatment work?", "What can help with dark spots?"]


def extract_phone(text: str) -> Optional[str]:
    """Extract a 10-digit Indian phone number with optional +91 or leading 0."""
    match = re.search(r'(?<!\d)(?:(?:\+91|0)[\-\s]?)?[6-9]\d{9}(?!\d)', text)
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

    def warmup(self) -> None:
        """Prime query embedding and FAISS retrieval before the first visitor message."""
        if not settings.RAG_WARMUP_ENABLED:
            return

        try:
            self.vector_store.search(settings.RAG_WARMUP_QUERY, top_k=1)
            print("[RAG] Retrieval warmup complete")
        except Exception as exc:
            # Warmup is an optimization; startup must remain available if it fails.
            print(f"[RAG] Retrieval warmup skipped: {exc}")

    def process_chat(self, req: ChatRequest) -> Dict[str, Any]:
        message = req.message.strip()
        session_id = req.session_id
        detected_lang = LanguageService.detect_language(message)
        lang = req.language or detected_lang

        # Restore a previously captured browser identity into a newly created chat session.
        captured_info = session_manager.get_captured_info(session_id)
        already_has_lead = session_manager.is_lead_captured(session_id)
        browser_phone = extract_phone(req.user_phone or "")
        if browser_phone and not already_has_lead:
            handoff_manager.update_user_contact(session_id, user_phone=browser_phone)
            session_manager.set_phone_required(session_id, False)
            captured_info["phone"] = browser_phone
            already_has_lead = True

        phone_no = extract_phone(message)
        if session_manager.is_phone_required(session_id) and not already_has_lead and not phone_no:
            return self._build_response(
                "", True, 1.0, False, None, [], lang, session_id,
                requires_phone=True,
                phone_prompt_text=phone_prompt(lang),
            )

        # Only accepted messages become part of the conversation history.
        handoff_manager.add_transcript(session_id, "user", message)
        turn_count = session_manager.get_turn_count(session_id)

        # ── 1. Phone & Name Extraction → Kylas CRM Lead Sync ──
        name_candidate = extract_name(message) or captured_info.get("name")
        dual_intent_ack = ""

        if phone_no:
            clean_name = name_candidate or "Web Visitor"
            if not already_has_lead:
                self.crm_provider.create_lead(
                    phone_number=phone_no,
                    name=clean_name,
                    concern=f"Captured via chat session {session_id}",
                    channel=req.channel or "website"
                )
            handoff_manager.update_user_contact(session_id, user_name=clean_name, user_phone=phone_no)
            session_manager.set_phone_required(session_id, False)
            already_has_lead = True

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
                return self._build_response(
                    resp, True, 1.0, False, None, [], lang, session_id,
                    captured_phone=phone_no,
                    suggestions=suggested_questions(message, lang),
                )
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
                resp = f"आपसे मिलकर अच्छा लगा, {name_candidate}! मैंने आपका नाम सेव कर लिया है ताकि यह बातचीत व्यक्तिगत बनी रहे। 😊"
            elif lang == "mr":
                resp = f"तुम्हाला भेटून आनंद झाला, {name_candidate}! हे संभाषण वैयक्तिक राहावे म्हणून मी तुमचे नाव सेव्ह केले आहे. 😊"
            else:
                resp = f"Nice to meet you, {name_candidate}! I’ve saved your name so we can keep this conversation personal. 😊"

            handoff_manager.add_transcript(session_id, "bot", resp)
            session_manager.set_phone_required(session_id, True)
            return self._build_response(
                resp, True, 1.0, False, None, [], lang, session_id,
                requires_phone=True,
                phone_prompt_text=phone_prompt(lang),
            )

        # Prompt from the second user turn onward. Using >= also repairs older/reused
        # sessions that passed turn 2 before the phone-gate state was introduced.
        phone_gate_after_response = turn_count >= 2 and not already_has_lead and not phone_no

        # ── 2. Greeting / Small-Talk Detection ──
        clean_msg = re.sub(r'[^\w\s]', '', message.lower().strip())
        if clean_msg in GREETINGS:
            ans = ("👋 Hello! Welcome to **Clinderma** — your dermatologist-led skincare partner.\n\n"
                   "Tell me what’s been bothering your skin, and I’ll help with acne, pigmentation, treatment timelines, everyday skincare questions, or Clinderma product information. What would you like to understand first?")
            if lang == "hi":
                ans = ("👋 नमस्ते! **क्लिंडरमा** में आपका स्वागत है — आपका त्वचा विशेषज्ञ स्किनकेयर पार्टनर।\n\n"
                       "अपनी त्वचा की परेशानी बताइए। मैं एक्ने, पिगमेंटेशन, उपचार में लगने वाले समय, सामान्य स्किनकेयर सवालों या क्लिंडरमा उत्पादों की जानकारी में आपकी मदद कर सकता हूँ।")
            elif lang == "mr":
                ans = ("👋 नमस्कार! **क्लिंडरमा** मध्ये आपले स्वागत — तुमचा त्वचातज्ज्ञ स्किनकेअर पार्टनर।\n\n"
                       "तुमच्या त्वचेची अडचण सांगा. मी मुरुम, पिगमेंटेशन, उपचाराचा कालावधी, सामान्य स्किनकेअर प्रश्न किंवा क्लिंडरमा उत्पादनांची माहिती देऊ शकतो.")

            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(
                ans, True, 1.0, False, None, [], lang, session_id,
                requires_phone=phone_gate_after_response,
                phone_prompt_text=phone_prompt(lang) if phone_gate_after_response else None,
                suggestions=suggested_questions(message, lang),
            )

        # ── 3. Explicit Clinderma Product / Shop Intent ──
        if has_product_intent(message):
            ans = product_recommendation(message, lang)
            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(
                ans, True, 1.0, False, None, [], lang, session_id,
                requires_phone=phone_gate_after_response,
                phone_prompt_text=phone_prompt(lang) if phone_gate_after_response else None,
                suggestions=suggested_questions(message, lang),
            )

        # ── 4. Order Queries (tracking integration is intentionally disabled in V1) ──
        if has_order_intent(message):
            ans = ("Order tracking isn’t connected in this first chatbot version, so I can’t safely show a live status here. "
                   "Please use the tracking link sent by SMS or email after dispatch, or contact Clinderma at help@theclinderma.com with your order number. "
                   "For general delivery guidance, standard orders are usually delivered within 5–7 business days after confirmation.")
            if lang == "hi":
                ans = ("इस पहले चैटबॉट वर्ज़न में लाइव ऑर्डर ट्रैकिंग जुड़ी नहीं है, इसलिए मैं यहाँ सही स्टेटस नहीं दिखा सकता। "
                       "डिस्पैच के बाद SMS या ईमेल में मिला ट्रैकिंग लिंक देखें, या ऑर्डर नंबर के साथ help@theclinderma.com पर संपर्क करें। "
                       "सामान्यतः कन्फर्मेशन के बाद डिलीवरी में 5–7 कार्यदिवस लगते हैं।")
            elif lang == "mr":
                ans = ("चॅटबॉटच्या या पहिल्या आवृत्तीत लाईव्ह ऑर्डर ट्रॅकिंग जोडलेले नाही, त्यामुळे मी येथे अचूक स्थिती दाखवू शकत नाही. "
                       "डिस्पॅचनंतर SMS किंवा ईमेलमध्ये आलेली ट्रॅकिंग लिंक वापरा, किंवा ऑर्डर क्रमांकासह help@theclinderma.com वर संपर्क करा. "
                       "सामान्यतः कन्फर्मेशननंतर डिलिव्हरीला 5–7 कामकाजाचे दिवस लागतात.")
            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(
                ans, True, 1.0, False, None, [], lang, session_id,
                requires_phone=phone_gate_after_response,
                phone_prompt_text=phone_prompt(lang) if phone_gate_after_response else None,
            )

        # ── 5. Human Agent / Skin Coach Handoff Intent ──
        handoff_keywords = ["human", "agent", "skin coach", "talk to doctor", "call me",
                            "escalate", "representative", "real person", "speak to someone"]
        if any(w in message.lower() for w in handoff_keywords):
            handoff_manager.create_handoff(
                session_id=session_id,
                user_phone=req.user_phone or phone_no,
                reason=f"User requested human escalation: '{message}'",
                channel=req.channel or "website"
            )
            ans = "I’ve noted that you’d like human help from Clinderma. A Skin Coach can review the conversation and follow up with you directly. 🩺"
            if not already_has_lead and not phone_no:
                session_manager.set_phone_required(session_id, True)
            if lang == "hi":
                ans = "मैंने नोट कर लिया है कि आप क्लिंडरमा टीम से मानवीय सहायता चाहते हैं। एक स्किन कोच इस बातचीत की समीक्षा करके आपसे सीधे संपर्क कर सकता है। 🩺"
            elif lang == "mr":
                ans = "तुम्हाला क्लिंडरमा टीमकडून मानवी मदत हवी आहे हे मी नोंदवले आहे. स्किन कोच हे संभाषण पाहून तुमच्याशी थेट संपर्क साधू शकतो. 🩺"

            handoff_manager.add_transcript(session_id, "bot", ans)
            return self._build_response(
                ans, True, 1.0, True, "User requested human handoff", [], lang, session_id,
                requires_phone=not already_has_lead and not phone_no,
                phone_prompt_text=phone_prompt(lang) if not already_has_lead and not phone_no else None,
            )

        # ── 6. Multi-Source Grounded RAG: Conversational Search → LLM Generation ──
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

        requires_phone = phone_gate_after_response
        prompt_text = phone_prompt(lang) if phone_gate_after_response else None

        handoff_manager.add_transcript(session_id, "bot", final_answer)

        return self._build_response(
            final_answer, is_grounded, result.get("confidence", 0.0),
            result.get("handoff_recommended", False), result.get("handoff_reason"),
            sources, lang, session_id,
            requires_phone=requires_phone,
            phone_prompt_text=prompt_text,
            captured_phone=phone_no,
            suggestions=suggested_questions(message, lang),
        )

    @staticmethod
    def _build_response(
        answer, grounded, confidence, handoff_rec, handoff_reason, sources, lang, session_id,
        requires_phone=False, phone_prompt_text=None, captured_phone=None, suggestions=None,
    ):
        if requires_phone:
            session_manager.set_phone_required(session_id, True)
        answer = answer.strip()
        if answer:
            answer = f"{answer}\n\n{skin_test_cta(lang)}"
        if phone_prompt_text:
            phone_prompt_text = f"{phone_prompt_text}\n\n{skin_test_cta(lang)}"
        return {
            "answer": answer,
            "grounded": grounded,
            "confidence": confidence,
            "handoff_recommended": handoff_rec,
            "handoff_reason": handoff_reason,
            "sources": sources,
            "language": lang,
            "session_id": session_id,
            "requires_phone": requires_phone,
            "phone_prompt": phone_prompt_text,
            "captured_phone": captured_phone,
            "suggested_questions": suggestions or [],
        }


rag_engine = RAGEngine()
