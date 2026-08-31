import unittest

from app.providers.llm_provider import compact_clinic_answer, compact_grounded_fallback, normalize_chat_answer


class ResponseFormattingTests(unittest.TestCase):
    def test_removes_bold_article_title(self):
        answer = "**Why Am I Getting Tiny Bumps? - Introduction & Overview**\n\nTiny bumps can have several causes."
        self.assertEqual(
            normalize_chat_answer(answer),
            "Tiny bumps can have several causes.",
        )

    def test_removes_markdown_heading(self):
        self.assertEqual(
            normalize_chat_answer("## Overview\n\nPlease speak with a Skin Coach."),
            "Please speak with a Skin Coach.",
        )

    def test_compacts_long_raw_kb_fallback(self):
        answer = (
            "This concern can be understood through the first detailed sentence, which gives the visitor useful, accurate, and very clear context. "
            "This second sentence adds relevant supporting detail while keeping the response focused, natural, reassuring, and easy to read in chat. "
            "This third sentence completes the practical guidance naturally without cutting an important recommendation or the final thought in the middle. "
            "This fourth sentence should be excluded because the earlier complete sentences already reach the target length."
        )
        result = compact_grounded_fallback(answer)
        self.assertNotIn("This fourth sentence", result)
        self.assertTrue(result.endswith("middle."))

    def test_skips_blog_lead_in_for_informative_fallback(self):
        answer = (
            "You wash your face regularly. You may not even have typical pimples. "
            "The skin feels rough and uneven. Tiny forehead bumps can have different causes. "
            "Sometimes they are clogged pores. Sometimes they are related to hair products or sweat."
        )
        self.assertEqual(
            compact_grounded_fallback(answer),
            "Tiny forehead bumps can have different causes. Sometimes they are clogged pores. "
            "Sometimes they are related to hair products or sweat.",
        )

    def test_decodes_html_spacing(self):
        self.assertEqual(normalize_chat_answer("A concern. &#x20;"), "A concern.")

    def test_generated_answer_preserves_complete_coherent_response(self):
        answer = (
            "Sweat can make follicular irritation more noticeable. "
            "Try a new home-care routine. "
            "A Clinderma Skin Coach can assess the exact cause."
        )
        self.assertEqual(
            compact_clinic_answer(answer),
            answer,
        )

    def test_incomplete_generated_answer_uses_complete_fallback(self):
        fallback = "A complete grounded explanation. A complete next step."
        self.assertEqual(
            compact_clinic_answer("This response was cut off before it could", fallback),
            fallback,
        )


if __name__ == "__main__":
    unittest.main()
