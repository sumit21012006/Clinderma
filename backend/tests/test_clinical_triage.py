import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.clinical_triage import classify_clinical_escalation, triage_response


class ClinicalTriageTests(unittest.TestCase):
    def test_critical_reaction_wins_even_when_product_words_are_present(self):
        result = classify_clinical_escalation("This serum caused an allergic reaction and facial swelling")
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "critical")
        self.assertEqual(result.kind, "clinical")

    def test_dangerous_active_combination_is_critical(self):
        result = classify_clinical_escalation("Can I use AHA 30% with tretinoin?")
        self.assertEqual(result.severity, "critical")
        self.assertIn("combination", result.reason.lower())

    def test_prescription_dosage_is_moderate(self):
        result = classify_clinical_escalation("What isotretinoin dose should I take?")
        self.assertEqual(result.severity, "moderate")

    def test_human_request_is_routine(self):
        result = classify_clinical_escalation("I want to talk to doctor")
        self.assertEqual(result.severity, "routine")
        self.assertEqual(result.kind, "human_request")

    def test_non_escalation_returns_none(self):
        self.assertIsNone(classify_clinical_escalation("How long do dark spots take to fade?"))

    def test_severe_itching_with_visible_bumps_is_moderate(self):
        result = classify_clinical_escalation(
            "I have very strong itching on my hands and tiny bumps are visible"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "moderate")
        self.assertIn("itching", result.reason.lower())

    def test_semantic_paraphrase_is_understood(self):
        result = classify_clinical_escalation(
            "My palms won't stop itching and little raised spots appeared"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "moderate")
        self.assertIn("persistent/recurrent", result.matched_trigger)

    def test_negated_emergency_signs_do_not_make_case_critical(self):
        result = classify_clinical_escalation(
            "I have strong itchy bumps but no trouble breathing or facial swelling"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "moderate")

    def test_isolated_negated_emergency_sign_does_not_escalate(self):
        self.assertIsNone(classify_clinical_escalation(
            "I do not have difficulty breathing"
        ))

    def test_mild_isolated_itch_does_not_escalate(self):
        self.assertIsNone(classify_clinical_escalation(
            "My hand is only slightly itchy, with no bumps, swelling, or rash"
        ))

    def test_paraphrased_airway_emergency_is_critical(self):
        result = classify_clinical_escalation(
            "My throat feels tight and I can't catch my breath"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, "critical")

    def test_generic_itch_question_is_not_a_case(self):
        self.assertIsNone(classify_clinical_escalation("Does acne usually itch?"))

    def test_negated_human_request_does_not_escalate(self):
        self.assertIsNone(classify_clinical_escalation(
            "I do not want to speak to an agent"
        ))

    def test_critical_response_contains_immediate_safety_direction(self):
        result = classify_clinical_escalation("I have difficulty breathing and hives")
        response = triage_response(result, "en")
        self.assertIn("Critical/Urgent", response)
        self.assertIn("emergency medical care", response)

    def test_moderate_symptom_response_is_not_prescription_specific(self):
        result = classify_clinical_escalation(
            "I have very strong itching and tiny bumps are visible"
        )
        response = triage_response(result, "en")
        self.assertIn("clinician review", response)
        self.assertNotIn("prescription retinoid", response)


if __name__ == "__main__":
    unittest.main()
