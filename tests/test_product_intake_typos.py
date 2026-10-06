# tests/test_product_intake_typos.py
import unittest

from agents.agents.product_intake import looks_like_add_product, parse_product_request


class ProductIntakeTypoTests(unittest.TestCase):
    def test_typo_in_product_word_still_parses(self):
        draft = parse_product_request("can you add new prodcut called panadol price 10 sell 15")
        self.assertIsNotNone(draft)
        self.assertEqual(draft["name"], "panadol")
        self.assertEqual(draft["unit_buy_price"], 10.0)
        self.assertEqual(draft["unit_sell_price"], 15.0)

    def test_other_one_letter_typos(self):
        for text in ("add new prodact pandol sell 15", "create new produt pandol sell 15", "add new proudct pandol"):
            self.assertTrue(looks_like_add_product(text), text)

    def test_correct_spelling_unchanged(self):
        draft = parse_product_request("create new product called pandol price 10 sell 15")
        self.assertEqual(draft["name"], "pandol")

    def test_plain_questions_and_other_messages_are_not_add_requests(self):
        for text in ("how many products do I have", "show low stock products", "sold 3 panadol today", "i wanna know what products we have now"):
            self.assertFalse(looks_like_add_product(text), text)


if __name__ == "__main__":
    unittest.main()