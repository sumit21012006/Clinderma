import unittest

from app.services.rag_engine import (
    applicable_active_offers,
    format_active_offers,
    has_offer_intent,
    offer_product_names_from_message,
)


ACTIVE_OFFERS = [
    {
        "name": "Epifade Festival Offer",
        "discount_code": "GLOW20",
        "discount_type": "percentage",
        "discount_value": 20,
        "applicable_products": ["Epifade Cream"],
        "conditions": {"notes": "Minimum order ₹499"},
        "end_date": "2026-12-31",
    },
    {
        "name": "All Shop Offer",
        "discount_code": "CARE10",
        "discount_type": "percentage",
        "discount_value": 10,
        "applicable_products": [],
        "conditions": {},
        "end_date": "2026-12-31",
    },
]


class OfferContextTests(unittest.TestCase):
    def test_detects_explicit_offer_questions(self):
        self.assertTrue(has_offer_intent("Do you have a discount coupon today?"))
        self.assertTrue(has_offer_intent("क्या कोई ऑफर है?"))
        self.assertFalse(has_offer_intent("What can help with acne marks?"))

    def test_product_reply_only_uses_matching_or_global_offers(self):
        offers = applicable_active_offers(ACTIVE_OFFERS, ["Epifade Cream"])
        self.assertEqual([offer["discount_code"] for offer in offers], ["GLOW20", "CARE10"])

    def test_offer_response_never_invents_when_none_are_active(self):
        answer = format_active_offers([], "en")
        self.assertIn("don’t see any valid active offers", answer)
        self.assertIn("won’t invent", answer)

    def test_product_offer_response_includes_authoritative_details(self):
        answer = format_active_offers(ACTIVE_OFFERS, "en", ["Epifade Cream"])
        self.assertIn("GLOW20", answer)
        self.assertIn("CARE10", answer)
        self.assertIn("2026-12-31", answer)

    def test_offer_question_can_target_a_named_product(self):
        products = offer_product_names_from_message("Is there an offer on Epifade?")
        self.assertEqual(products, ["Epifade Cream"])


if __name__ == "__main__":
    unittest.main()
