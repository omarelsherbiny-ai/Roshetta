# tests/test_category_card.py
import unittest

from agents.agents.verification import build_category_proposal, clean_category_name


class CategoryCard(unittest.TestCase):
    def test_card_shape(self):
        card = build_category_proposal("  Vitamins   and  Minerals ", "en")
        self.assertEqual(card["action_type"], "create_category")
        self.assertEqual(card["category_name"], "Vitamins and Minerals")
        self.assertEqual(card["items"], [])
        self.assertEqual(card["total_amount"], 0.0)
        self.assertEqual(card["status"], "pending_confirmation")
        self.assertTrue(card["id"].startswith("prop-"))
        self.assertEqual(card["summary_en"], "Create category Vitamins and Minerals")

    def test_arabic_card(self):
        card = build_category_proposal("فيتامينات", "ar")
        self.assertEqual(card["title"], "إضافة قسم جديد")
        self.assertEqual(card["category_name"], "فيتامينات")

    def test_blank_name_gives_no_card(self):
        for blank in ("", "   ", None):
            self.assertIsNone(build_category_proposal(blank, "en"))

    def test_name_is_cut_at_40_characters(self):
        self.assertEqual(len(clean_category_name("x" * 90)), 40)

    def test_each_card_has_its_own_id(self):
        self.assertNotEqual(build_category_proposal("A")["id"], build_category_proposal("A")["id"])


if __name__ == "__main__":
    unittest.main()