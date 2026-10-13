"""Deterministic clinical escalation triage.

Clinical safety decisions must not depend on vector retrieval or an LLM.  This
module therefore runs before phone gating, product intent, and RAG generation.
The highest matching severity always wins.
"""

from dataclasses import dataclass
import re
from typing import Dict, Optional, Set, Tuple


@dataclass(frozen=True)
class ClinicalTriageResult:
    severity: str
    reason: str
    matched_trigger: str
    ai_summary: str
    kind: str


CRITICAL_TRIGGER_GROUPS = (
    (
        "Acute allergic or respiratory reaction",
        (
            "allergic reaction", "anaphylaxis", "anaphylactic", "hives",
            "difficulty breathing", "trouble breathing", "cannot breathe",
            "can't breathe", "facial swelling", "face swelling", "lip swelling",
            "lips swelling", "tongue swelling", "throat swelling", "widespread rash",
            "गंभीर एलर्जी", "सांस लेने में कठिनाई", "चेहरे पर सूजन",
            "तीव्र ऍलर्जी", "श्वास घेण्यास त्रास", "चेहऱ्यावर सूज",
        ),
    ),
    (
        "Possible chemical burn or severe barrier injury",
        (
            "chemical burn", "burning really badly", "severe burning", "intense burning",
            "intense stinging", "extreme peeling", "blistering", "skin blister",
            "severe redness", "severe erythema", "raw skin", "skin is burning",
            "बहुत जलन", "तेज जलन", "छाले", "अत्यधिक छिलना",
            "तीव्र जळजळ", "फोड", "खूप त्वचा सोलणे",
        ),
    ),
    (
        "Severe inflammatory lesion or possible infection",
        (
            "cystic swelling", "severe pain", "infection", "pus oozing", "oozing pus",
            "bleeding nodule", "bleeding nodules", "painful swelling", "infected acne",
            "गंभीर दर्द", "इन्फेक्शन", "मवाद", "तीव्र वेदना", "संसर्ग", "पू येणे",
        ),
    ),
)

MODERATE_TRIGGER_GROUPS = (
    (
        "Prescription retinoid or dosage review",
        (
            "isotretinoin", "accutane", "tretinoin dose", "prescription dosage",
            "oral retinoid", "retinoid dosage", "isotretinoin dose",
            "आइसोट्रेटिनोइन", "ट्रेटिनोइन की खुराक", "आयसोट्रेटिनोइन",
            "ट्रेटिनोइन डोस",
        ),
    ),
)

HUMAN_REQUEST_TRIGGERS = (
    "human", "human agent", "agent", "skin coach", "talk to doctor", "call me",
    "escalate", "representative", "real person", "speak to someone", "speak with someone",
    "डॉक्टर से बात", "इंसान से बात", "स्किन कोच", "डॉक्टरांशी बोला", "माणसाशी बोला",
)


@dataclass(frozen=True)
class SemanticClinicalSignals:
    """Meaning-level features extracted from a customer's description."""

    concepts: frozenset[str]
    evidence: Tuple[str, ...]
    intensity: int
    worsening: bool
    persistent: bool
    personal_report: bool


# Patterns map varied wording to clinical concepts. Escalation decisions below
# are made from combinations of these concepts, not from one phrase alone.
CONCEPT_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "airway_distress": (
        r"\b(?:difficulty|trouble|problems?)\s+(?:with\s+)?breath(?:ing)?\b",
        r"\b(?:cannot|can't|cant|struggling\s+to)\s+breathe\b",
        r"\b(?:breathless|wheez(?:e|ing)|choking|gasping)\b",
        r"\b(?:throat\s+(?:feels?\s+)?tight|difficulty\s+swallowing)\b",
        r"\bcan't\s+catch\s+(?:my|their)\s+breath\b",
    ),
    "face_or_airway_swelling": (
        r"\b(?:face|facial|lip|lips|tongue|mouth|throat|eyes?|eyelids?)\b.{0,24}\b(?:swell\w*|puff\w*)\b",
        r"\b(?:swell\w*|puff\w*)\b.{0,24}\b(?:face|facial|lip|lips|tongue|mouth|throat|eyes?|eyelids?)\b",
    ),
    "swelling": (r"\b(?:swell\w*|puffiness|puffy|edema|oedema)\b",),
    "allergic_reaction": (
        r"\b(?:allerg\w*\s+reaction|anaphyla\w*)\b",
        r"\breact(?:ion|ing)\s+(?:badly|severely)\b",
    ),
    "hives": (r"\b(?:hives?|urticaria|welts?|nettle\s+rash)\b",),
    "itching": (
        r"\b(?:itch\w*|prurit\w*|scratch\w*)\b",
        r"खुजली|खाज|खाज सुट|खूप खाज",
    ),
    "skin_lesion": (
        r"\b(?:bumps?|spots?|rash(?:es)?|lumps?|papules?|pimples?|raised\s+(?:spots?|areas?|skin))\b",
        r"\b(?:tiny|small|little)\s+(?:dots?|blisters?|boils?)\b",
        r"दाने|पुरळ|गाठी|फोड",
    ),
    "blistering": (r"\b(?:blister\w*|fluid[- ]filled|vesicles?)\b", r"छाले|फोड"),
    "burning": (
        r"\b(?:burn\w*|sting\w*|skin\s+(?:feels?\s+)?on\s+fire)\b",
        r"जलन|जळजळ",
    ),
    "peeling_or_raw": (
        r"\b(?:peel\w*|raw\s+skin|skin\s+(?:coming|falling)\s+off|open\s+skin)\b",
    ),
    "pain": (r"\b(?:pain\w*|tender\w*|sore\w*|throbbing)\b", r"दर्द|वेदना"),
    "infection": (
        r"\b(?:infect\w*|pus|ooz\w*|discharge|abscess|boil)\b",
        r"इन्फेक्शन|संक्रमण|संसर्ग|मवाद|पू येणे",
    ),
    "bleeding": (r"\b(?:bleed\w*|blood\w*)\b",),
    "systemic_illness": (
        r"\b(?:fever|feverish|chills?|faint\w*|dizz\w*|confus\w*)\b",
    ),
    "widespread": (
        r"\b(?:all\s+over|whole\s+body|widespread|everywhere|spread\w*)\b",
    ),
    "chemical_exposure": (
        r"\b(?:chemical\s+(?:burn|exposure)|acid\s+(?:burn|peel)|bleach)\b",
        r"\b(?:after|from)\s+(?:a\s+)?(?:peel|chemical)\b",
    ),
    "tretinoin": (r"\b(?:tretinoin|retin-a)\b",),
    "oral_retinoid": (r"\b(?:isotretinoin|accutane|oral\s+retinoid)\b",),
    "dosage": (r"\b(?:dose|dosage|how\s+much|increase|decrease|change)\b",),
    "strong_exfoliant": (
        r"\b(?:aha\s*30\s*%?|30\s*%\s*aha|strong\s+(?:acid|exfoliant)|chemical\s+peel)\b",
    ),
}

SEVERE_INTENSITY_PATTERNS = (
    r"\b(?:severe|intense|extreme|unbearable|excruciating|very\s+strong|really\s+bad|terrible)\b",
    r"\b(?:can't|cannot|cant)\s+(?:stop|tolerate|bear|sleep)\b",
    r"बहुत तेज|बहुत ज़्यादा|गंभीर|तीव्र|खूप तीव्र|असह्य",
)
MODERATE_INTENSITY_PATTERNS = (
    r"\b(?:strong|significant|quite\s+bad|a\s+lot|very\s+itchy)\b",
)
MILD_INTENSITY_PATTERNS = (r"\b(?:mild|slight|slightly|a\s+little|minor)\b",)
WORSENING_PATTERNS = (
    r"\b(?:worsen\w*|getting\s+(?:worse|bad)|rapidly|increas\w*|spread\w*)\b",
)
PERSISTENCE_PATTERNS = (
    r"\b(?:persistent|won't\s+stop|will\s+not\s+stop|keeps?\s+(?:coming|itching)|recurr\w*)\b",
    r"\b(?:for|since)\s+(?:several\s+)?(?:days?|weeks?|months?)\b",
)
PERSONAL_REPORT_PATTERNS = (
    r"\b(?:i|i'm|im|i've|ive|me|my|mine)\b",
    r"\b(?:appeared|developed|started|visible|showing|came\s+up|broke\s+out|caused)\b",
    r"\b(?:i\s+am|i'm|im)\s+(?:having|getting|experiencing)\b",
)
NEGATION_WINDOW = re.compile(
    r"\b(?:no|not|without|never|deny|denies|don't|dont|do\s+not|doesn't|doesnt|does\s+not)\b"
    r"(?:\W+\w+){0,5}\W*$"
)


def _normalise(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").casefold()).strip()


def _first_match(message: str, phrases: tuple[str, ...]) -> Optional[str]:
    for phrase in phrases:
        candidate = phrase.casefold()
        if candidate and candidate[0].isalnum() and candidate[-1].isalnum():
            if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", message):
                return phrase
        elif candidate in message:
            return phrase
    return None


def _first_non_negated_phrase(message: str, phrases: tuple[str, ...]) -> Optional[str]:
    """Use explicit phrases only as a negation-aware safety backstop."""
    for phrase in phrases:
        candidate = phrase.casefold()
        match = re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", message)
        if match and not _is_negated(message, match.start()):
            return phrase
    return None


def _has_pattern(message: str, patterns: Tuple[str, ...]) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in patterns)


def _is_negated(message: str, match_start: int) -> bool:
    """Detect a nearby negation such as 'no breathing trouble or swelling'."""
    prefix = message[max(0, match_start - 80):match_start]
    # Do not carry negation through a sentence/clause boundary.
    prefix = re.split(r"[.!?;]|\bbut\b|\bhowever\b", prefix)[-1]
    return bool(NEGATION_WINDOW.search(prefix))


def _extract_semantic_signals(message: str) -> SemanticClinicalSignals:
    normalised = _normalise(message)
    concepts: Set[str] = set()
    evidence = []

    for concept, patterns in CONCEPT_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, normalised, flags=re.IGNORECASE)
            if match and not _is_negated(normalised, match.start()):
                concepts.add(concept)
                evidence.append(f"{concept}: {match.group(0).strip()}")
                break

    if _has_pattern(normalised, SEVERE_INTENSITY_PATTERNS):
        intensity = 3
    elif _has_pattern(normalised, MODERATE_INTENSITY_PATTERNS):
        intensity = 2
    elif _has_pattern(normalised, MILD_INTENSITY_PATTERNS):
        intensity = 1
    else:
        intensity = 1 if concepts else 0

    return SemanticClinicalSignals(
        concepts=frozenset(concepts),
        evidence=tuple(evidence),
        intensity=intensity,
        worsening=_has_pattern(normalised, WORSENING_PATTERNS),
        persistent=_has_pattern(normalised, PERSISTENCE_PATTERNS),
        personal_report=_has_pattern(normalised, PERSONAL_REPORT_PATTERNS),
    )


def _semantic_result(
    severity: str,
    reason: str,
    signals: SemanticClinicalSignals,
) -> ClinicalTriageResult:
    semantic_evidence = list(signals.evidence[:5])
    if signals.intensity >= 3:
        semantic_evidence.append("severe intensity")
    if signals.worsening:
        semantic_evidence.append("worsening/progression")
    if signals.persistent:
        semantic_evidence.append("persistent/recurrent")
    summary = "; ".join(semantic_evidence) or "clinical meaning inferred from symptom description"
    return ClinicalTriageResult(
        severity=severity,
        reason=reason,
        matched_trigger=summary,
        ai_summary=(
            f"Semantic clinical triage classified this as {severity}: {reason}. "
            f"Evidence: {summary}."
        ),
        kind="clinical",
    )


def classify_clinical_escalation(message: str) -> Optional[ClinicalTriageResult]:
    """Classify composed clinical meaning, with deterministic safety overrides."""
    normalised = _normalise(message)
    if not normalised:
        return None

    signals = _extract_semantic_signals(normalised)
    concepts = signals.concepts

    # Emergency meaning takes precedence. Negated symptoms were removed during
    # extraction, so "no breathing difficulty" cannot accidentally become urgent.
    if "airway_distress" in concepts:
        return _semantic_result(
            "critical", "Acute respiratory or airway symptoms", signals
        )

    if "face_or_airway_swelling" in concepts:
        return _semantic_result(
            "critical", "Facial, oral, or throat swelling", signals
        )

    if "allergic_reaction" in concepts and concepts.intersection({"hives", "swelling", "itching"}):
        return _semantic_result(
            "critical", "Possible acute allergic reaction", signals
        )

    if "hives" in concepts and (
        "widespread" in concepts or signals.intensity >= 3 or signals.worsening
    ):
        return _semantic_result(
            "critical", "Severe or spreading urticarial reaction", signals
        )

    skin_injury = concepts.intersection({"blistering", "burning", "peeling_or_raw"})
    if skin_injury and (
        "chemical_exposure" in concepts
        or "blistering" in concepts
        or signals.intensity >= 3
        or signals.worsening
    ):
        return _semantic_result(
            "critical", "Possible chemical burn or severe barrier injury", signals
        )

    infection_complications = concepts.intersection(
        {"systemic_illness", "bleeding", "swelling", "widespread"}
    )
    if "infection" in concepts and (
        infection_complications or signals.intensity >= 3 or signals.worsening
    ):
        return _semantic_result(
            "critical", "Severe inflammatory lesion or possible infection", signals
        )

    if {"tretinoin", "strong_exfoliant"}.issubset(concepts):
        return _semantic_result(
            "critical", "High-risk tretinoin and strong exfoliant combination", signals
        )

    # Multilingual and explicit emergency vocabulary remains as a final safety
    # net only when concept extraction found nothing. It is not the primary
    # classifier and still respects nearby negation.
    if not concepts:
        for reason, phrases in CRITICAL_TRIGGER_GROUPS:
            trigger = _first_non_negated_phrase(normalised, phrases)
            if trigger:
                return ClinicalTriageResult(
                    severity="critical",
                    reason=reason,
                    matched_trigger=f"emergency safety override: {trigger}",
                    ai_summary=(
                        f"Deterministic emergency safety override matched '{trigger}'. "
                        "Immediate human review is required."
                    ),
                    kind="clinical",
                )

        for reason, phrases in MODERATE_TRIGGER_GROUPS:
            trigger = _first_non_negated_phrase(normalised, phrases)
            if trigger:
                return ClinicalTriageResult(
                    severity="moderate",
                    reason=reason,
                    matched_trigger=f"prescription safety override: {trigger}",
                    ai_summary=(
                        f"Deterministic prescription safety override matched '{trigger}'. "
                        "Clinician review is required."
                    ),
                    kind="clinical",
                )

    # Prescription decisions always require individual clinician review.
    if "oral_retinoid" in concepts or (
        "tretinoin" in concepts and "dosage" in concepts
    ):
        return _semantic_result(
            "moderate", "Prescription retinoid or dosage review", signals
        )

    # Compose symptom meaning. A single mild symptom remains with the bot, while
    # severity, visible lesions, persistence, or progression creates a review.
    visible_skin_change = concepts.intersection(
        {"skin_lesion", "hives", "swelling", "blistering", "peeling_or_raw"}
    )
    uncomfortable_symptom = concepts.intersection({"itching", "burning", "pain"})
    if "itching" in concepts and (
        signals.intensity >= 3
        or (visible_skin_change and signals.intensity >= 2)
        or signals.worsening
        or signals.persistent
    ):
        return _semantic_result(
            "moderate", "Severe or persistent itching with visible skin changes", signals
        )

    if signals.personal_report and visible_skin_change and uncomfortable_symptom and (
        signals.intensity >= 2 or signals.worsening or signals.persistent
    ):
        return _semantic_result(
            "moderate", "Symptomatic skin eruption requiring clinical review", signals
        )

    if "infection" in concepts:
        return _semantic_result(
            "moderate", "Possible localized skin infection", signals
        )

    if skin_injury and signals.personal_report:
        return _semantic_result(
            "moderate", "Possible skin barrier injury", signals
        )

    trigger = _first_non_negated_phrase(normalised, HUMAN_REQUEST_TRIGGERS)
    if trigger:
        return ClinicalTriageResult(
            severity="routine",
            reason="Customer requested human assistance",
            matched_trigger=trigger,
            ai_summary=f"Customer explicitly requested a human agent using: '{trigger}'.",
            kind="human_request",
        )

    return None


def triage_response(result: ClinicalTriageResult, language: str = "en") -> str:
    """Return a complete, severity-appropriate response without LLM generation."""
    lang = language if language in {"en", "hi", "mr"} else "en"

    if result.severity == "critical":
        responses = {
            "en": (
                "I’m flagging this as Critical/Urgent for immediate clinical review. Stop using the suspected "
                "active or product now. If this followed a peel or chemical exposure, rinse the area with plenty "
                "of cool or lukewarm running water and do not apply another active. If you have difficulty breathing, "
                "face/lip/tongue/throat swelling, widespread hives, blistering, severe pain, or rapidly worsening "
                "symptoms, seek emergency medical care now—do not wait for a chat reply."
            ),
            "hi": (
                "मैं इसे तुरंत क्लिनिकल समीक्षा के लिए Critical/Urgent के रूप में दर्ज कर रहा हूँ। संदिग्ध एक्टिव "
                "या प्रोडक्ट का उपयोग अभी बंद करें। पील या केमिकल एक्सपोज़र के बाद समस्या हुई है तो त्वचा को ठंडे "
                "या हल्के गुनगुने बहते पानी से अच्छी तरह धोएँ और कोई दूसरा एक्टिव न लगाएँ। सांस लेने में कठिनाई, "
                "चेहरे/होंठ/जीभ/गले में सूजन, पूरे शरीर पर पित्ती, छाले, तेज दर्द या तेजी से बिगड़ते लक्षण हों तो "
                "चैट के उत्तर की प्रतीक्षा न करें और तुरंत आपातकालीन चिकित्सा सहायता लें।"
            ),
            "mr": (
                "मी हे तातडीच्या क्लिनिकल तपासणीसाठी Critical/Urgent म्हणून नोंदवत आहे. संशयित सक्रिय घटक किंवा "
                "उत्पादन त्वरित थांबवा. पील किंवा रासायनिक संपर्कानंतर त्रास झाला असल्यास त्वचा थंड किंवा कोमट "
                "वाहत्या पाण्याने नीट धुवा आणि दुसरा सक्रिय घटक लावू नका. श्वास घेण्यास त्रास, चेहरा/ओठ/जीभ/घसा "
                "सुजणे, अंगावर पित्त उठणे, फोड, तीव्र वेदना किंवा लक्षणे झपाट्याने वाढत असल्यास चॅटच्या उत्तराची "
                "वाट न पाहता तातडीची वैद्यकीय मदत घ्या."
            ),
        }
        return responses[lang]

    if result.severity == "moderate":
        if result.reason != "Prescription retinoid or dosage review":
            symptom_responses = {
                "en": (
                    "I’m flagging this for clinician review because the severity, progression, or visible skin "
                    "changes you described need an individual assessment. Avoid scratching and pause any newly "
                    "introduced active that seems linked to the reaction. If you develop breathing difficulty, "
                    "face/lip/tongue/throat swelling, rapidly spreading hives, blistering, fever, or severe pain, "
                    "seek urgent medical care rather than waiting for a chat reply."
                ),
                "hi": (
                    "आपके बताए लक्षणों की तीव्रता, बढ़ने की स्थिति या त्वचा में दिख रहे बदलाव के कारण मैं इसे "
                    "क्लिनिकल समीक्षा के लिए भेज रहा हूँ। खुजलाने से बचें और हाल में शुरू किया गया ऐसा एक्टिव रोक दें "
                    "जिससे यह प्रतिक्रिया जुड़ी लगती हो। सांस लेने में कठिनाई, चेहरे/होंठ/जीभ/गले में सूजन, तेजी से "
                    "फैलती पित्ती, छाले, बुखार या तेज दर्द हो तो चैट का इंतजार न करें और तुरंत चिकित्सा सहायता लें।"
                ),
                "mr": (
                    "तुम्ही सांगितलेल्या लक्षणांची तीव्रता, वाढ किंवा त्वचेवरील दिसणारे बदल यामुळे मी हे क्लिनिकल "
                    "तपासणीसाठी पाठवत आहे. खाजवणे टाळा आणि या प्रतिक्रियेशी संबंधित वाटणारा नवीन सक्रिय घटक थांबवा. "
                    "श्वास घेण्यास त्रास, चेहरा/ओठ/जीभ/घसा सुजणे, वेगाने पसरणारे पित्त, फोड, ताप किंवा तीव्र वेदना "
                    "झाल्यास चॅटची वाट न पाहता तातडीची वैद्यकीय मदत घ्या."
                ),
            }
            return symptom_responses[lang]

        responses = {
            "en": (
                "I’m flagging this for clinician review because prescription retinoid doses and combinations need "
                "individual medical guidance. Please do not start, stop, or change the prescribed dose based on chat "
                "advice. A Clinderma clinician should review your current medicines and routine."
            ),
            "hi": (
                "मैं इसे क्लिनिशियन समीक्षा के लिए दर्ज कर रहा हूँ क्योंकि प्रिस्क्रिप्शन रेटिनॉइड की खुराक और "
                "कॉम्बिनेशन के लिए व्यक्तिगत चिकित्सा सलाह आवश्यक है। चैट की सलाह के आधार पर निर्धारित खुराक शुरू, "
                "बंद या बदलें नहीं।"
            ),
            "mr": (
                "मी हे क्लिनिशियन तपासणीसाठी नोंदवत आहे कारण प्रिस्क्रिप्शन रेटिनॉइडचा डोस आणि संयोजनासाठी "
                "वैयक्तिक वैद्यकीय मार्गदर्शन आवश्यक आहे. चॅटच्या सल्ल्यावरून निर्धारित डोस सुरू, बंद किंवा बदलू नका."
            ),
        }
        return responses[lang]

    responses = {
        "en": "I’ve added this conversation to the human-support queue. A Clinderma Skin Coach can review the transcript and assist you directly.",
        "hi": "मैंने इस बातचीत को मानव सहायता कतार में जोड़ दिया है। क्लिंडरमा स्किन कोच ट्रांसक्रिप्ट देखकर आपकी सहायता कर सकते हैं।",
        "mr": "मी हे संभाषण मानवी सहाय्य रांगेत जोडले आहे. क्लिंडरमा स्किन कोच संभाषण पाहून तुम्हाला मदत करू शकतात.",
    }
    return responses[lang]
