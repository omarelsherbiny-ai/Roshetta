# server/app/services/invite_roles.py
"""Turns a role name typed by the user into one invitable role (Session 124, task 9b command 8).

Pure functions: no database, no settings. The caller (`/ai/propose-invite`) builds the list
of the pharmacy's roles and says for each whether the member may hand it out. A role is
never guessed: only an exact name (letter case and extra spaces ignored) matches, because
an invitation is a credential for a role.
"""
from typing import Dict, List, Optional, Tuple

# Words for the three built-in invitable roles. The owner role is never invitable.
BUILT_IN_WORDS: Dict[str, Tuple[str, ...]] = {
    "pharmacist": ("pharmacist", "صيدلي", "صيدلانى", "صيدلاني"),
    "cashier": ("cashier", "كاشير", "أمين الصندوق", "امين الصندوق"),
    "viewer": ("viewer", "مشاهد", "قارئ"),
}


def _key(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def resolve_invite_role(typed: str, roles: List[dict]) -> Tuple[Optional[dict], List[dict]]:
    """Returns (role, matches).

    `roles` rows: {"name", "kind" ("built_in" or "custom"), "fixed_role", "custom_role_id",
    "grantable"}. A custom role's own name wins over a built-in word. `role` is the single
    match, or None when nothing or more than one role has that name (`matches` then holds
    every candidate so the caller can say which).
    """
    wanted = _key(typed)
    if not wanted:
        return None, []
    custom = [r for r in roles if r.get("kind") == "custom" and _key(r.get("name")) == wanted]
    if custom:
        return (custom[0], custom) if len(custom) == 1 else (None, custom)
    built_in = [
        r for r in roles
        if r.get("kind") == "built_in"
        and (wanted == _key(r.get("fixed_role")) or wanted in {_key(w) for w in BUILT_IN_WORDS.get(r.get("fixed_role"), ())})
    ]
    if len(built_in) == 1:
        return built_in[0], built_in
    return None, built_in


def invitable_names(roles: List[dict]) -> List[str]:
    """Names of the roles this member may hand out, for the 'which role?' answer."""
    return [r["name"] for r in roles if r.get("grantable")]