# tests/test_invite_roles.py
"""Role-name resolution and the invitation card builder (task 9b, step 5d): pure, no database."""
import unittest

from agents.agents.verification import build_invite_proposal
from server.app.services.invite_roles import invitable_names, resolve_invite_role

ROLES = [
    {"name": "pharmacist", "kind": "built_in", "fixed_role": "pharmacist", "custom_role_id": None, "grantable": True, "scopes": []},
    {"name": "cashier", "kind": "built_in", "fixed_role": "cashier", "custom_role_id": None, "grantable": True, "scopes": []},
    {"name": "viewer", "kind": "built_in", "fixed_role": "viewer", "custom_role_id": None, "grantable": False, "scopes": []},
    {"name": "Night Shift", "kind": "custom", "fixed_role": None, "custom_role_id": 4, "grantable": True, "scopes": ["log_sale"]},
    {"name": "Managers", "kind": "custom", "fixed_role": None, "custom_role_id": 5, "grantable": True, "scopes": ["manage_staff"]},
]


class ResolveInviteRoleTests(unittest.TestCase):
    def test_built_in_by_name_case_and_spaces(self):
        for typed in ("cashier", "CASHIER", "  Cashier "):
            role, _ = resolve_invite_role(typed, ROLES)
            self.assertEqual(role["fixed_role"], "cashier", typed)

    def test_built_in_by_arabic_word(self):
        self.assertEqual(resolve_invite_role("كاشير", ROLES)[0]["fixed_role"], "cashier")
        self.assertEqual(resolve_invite_role("صيدلي", ROLES)[0]["fixed_role"], "pharmacist")

    def test_custom_role_by_exact_name_ignoring_case_and_inner_spaces(self):
        role, _ = resolve_invite_role("night   SHIFT", ROLES)
        self.assertEqual(role["custom_role_id"], 4)

    def test_a_custom_role_named_like_a_built_in_wins(self):
        roles = ROLES + [{"name": "Cashier", "kind": "custom", "fixed_role": None, "custom_role_id": 9, "grantable": True, "scopes": []}]
        self.assertEqual(resolve_invite_role("cashier", roles)[0]["custom_role_id"], 9)

    def test_no_guessing(self):
        for typed in ("cashie", "night", "owner", "admin", "", "   "):
            self.assertIsNone(resolve_invite_role(typed, ROLES)[0], typed)

    def test_two_custom_roles_with_the_same_name_are_ambiguous(self):
        roles = ROLES + [{"name": "night shift", "kind": "custom", "fixed_role": None, "custom_role_id": 8, "grantable": True, "scopes": []}]
        role, matches = resolve_invite_role("Night Shift", roles)
        self.assertIsNone(role)
        self.assertEqual({m["custom_role_id"] for m in matches}, {4, 8})

    def test_invitable_names_only_lists_grantable_roles(self):
        self.assertEqual(invitable_names(ROLES), ["pharmacist", "cashier", "Night Shift", "Managers"])


class InviteCardTests(unittest.TestCase):
    def test_card_holds_role_and_settings_but_no_link(self):
        card = build_invite_proposal(ROLES[1], 7, 1, "en")
        self.assertEqual(card["action_type"], "create_invite")
        self.assertEqual(card["invite"], {
            "role_name": "cashier", "kind": "built_in", "fixed_role": "cashier",
            "custom_role_id": None, "expires_in_days": 7, "max_uses": 1,
        })
        self.assertEqual(card["items"], [])
        self.assertNotIn("token", str(card).lower())
        self.assertNotIn("join_path", card)
        self.assertEqual(card["warnings"], [])
        self.assertIn("7 days", card["summary_en"])

    def test_custom_role_card(self):
        card = build_invite_proposal(ROLES[3], 3, 1, "en")
        self.assertEqual(card["invite"]["custom_role_id"], 4)
        self.assertIsNone(card["invite"]["fixed_role"])

    def test_warnings_for_many_uses_and_for_a_role_that_manages_staff(self):
        card = build_invite_proposal(ROLES[4], 7, 5, "en")
        self.assertEqual(len(card["warnings"]), 2)
        self.assertTrue(any("5 people" in w for w in card["warnings"]))
        self.assertTrue(any("invite and manage" in w for w in card["warnings"]))

    def test_invalid_numbers_or_roles_give_no_card(self):
        for days, uses in ((0, 1), (31, 1), (7, 0), (7, 51), ("x", 1)):
            self.assertIsNone(build_invite_proposal(ROLES[1], days, uses, "en"), (days, uses))
        self.assertIsNone(build_invite_proposal({"name": "", "fixed_role": "cashier"}, 7, 1, "en"))
        self.assertIsNone(build_invite_proposal({"name": "x", "fixed_role": "cashier", "custom_role_id": 3}, 7, 1, "en"))
        self.assertIsNone(build_invite_proposal({"name": "x"}, 7, 1, "en"))

    def test_arabic_card(self):
        card = build_invite_proposal(ROLES[1], 7, 1, "ar")
        self.assertEqual(card["title"], "دعوة عضو جديد")
        self.assertIn("cashier", card["summary_ar"])


if __name__ == "__main__":
    unittest.main()