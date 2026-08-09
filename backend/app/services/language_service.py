import re
from typing import Tuple

class LanguageService:
    @staticmethod
    def detect_language(text: str) -> str:
        if not text:
            return "en"

        # Check for Devanagari script (Hindi / Marathi)
        devanagari_chars = len(re.findall(r'[\u0900-\u097F]', text))
        if devanagari_chars > 2:
            # Check Marathi specific words
            marathi_words = ["काय", "आहे", "कसे", "मला", "नाही", "करावे", "होईल"]
            text_lower = text.lower()
            if any(w in text_lower for w in marathi_words):
                return "mr"
            return "hi"

        text_lower = text.lower()
        if "kya" in text_lower or "kaise" in text_lower or "kab" in text_lower or "hai" in text_lower:
            return "hi"
        if "kasa" in text_lower or "aahe" in text_lower or "kay" in text_lower:
            return "mr"

        return "en"

    @staticmethod
    def translate_or_normalize(text: str, target_lang: str = "en") -> str:
        # Standardize Hinglish / Marathi query for KB search if needed
        return text
