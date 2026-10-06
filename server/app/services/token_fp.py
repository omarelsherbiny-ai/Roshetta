# server/app/services/token_fp.py
"""Token fingerprint for diagnostics: FNV-1a 32 over the token's bytes, 8 hex characters.

Not a secret and not reversible in practice (32 bits of a long random token). It lets two
places that hold the same token show the same short value, so a mismatch is visible without
ever printing the token. Same algorithm as `fp()` in shared-schema/aimicromind_roshetta_tool.js.
"""


def token_fingerprint(token: str) -> str:
    h = 0x811C9DC5
    for b in str(token or "").encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"