# tests/test_scrub.py
import unittest

from server.app.services.scrub import scrub_for_external


class ScrubForExternalTests(unittest.TestCase):
    def test_egyptian_mobile_numbers_are_replaced(self):
        for raw in ("01001234567", "010-0123-4567", "+20 100 123 4567", "٠١٠٠١٢٣٤٥٦٧"):
            out = scrub_for_external(f"call {raw} now")
            self.assertEqual(out, "call [number] now", raw)

    def test_national_id_is_replaced_with_id_marker(self):
        self.assertEqual(scrub_for_external("id 29001011234567 ok"), "id [id] ok")

    def test_email_is_replaced(self):
        self.assertEqual(scrub_for_external("mail a.b+c@example.co.uk please"), "mail [email] please")

    def test_short_numbers_stay(self):
        text = "كام بانادول 500 مجم عندي 2 علبة بسعر 35.5"
        self.assertEqual(scrub_for_external(text), text)

    def test_text_without_digits_is_unchanged(self):
        text = "What is the maximum daily dose of paracetamol?"
        self.assertEqual(scrub_for_external(text), text)

    def test_empty_text_is_returned_as_is(self):
        self.assertEqual(scrub_for_external(""), "")


if __name__ == "__main__":
    unittest.main()