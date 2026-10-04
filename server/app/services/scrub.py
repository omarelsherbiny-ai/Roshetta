# server/app/services/scrub.py
"""
Removes personal identifiers from text before it leaves the system for MicroMind.

Used for the general-chat path only (the one place user text goes to an external
service). It is deliberately over-cautious: anything that looks like a phone
number, national ID or email address is replaced, even if it was something else.
Western and Arabic-Indic digits are both recognised.
"""
import re

_DIGIT = "0-9٠-٩۰-۹"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A run that starts and ends with a digit and may contain spaces, dashes, dots or
# brackets in between (for example +20 100 123 4567 or 010-1234-5678).
_NUMBER_RUN = re.compile(rf"\+?[{_DIGIT}](?:[{_DIGIT}\s\-.()]*[{_DIGIT}])?")
_DIGITS_ONLY = re.compile(rf"[{_DIGIT}]")

# Seven digits and up is treated as a phone or an ID; quantities and prices that
# people type in a pharmacy question are far shorter.
MIN_IDENTIFIER_DIGITS = 7
NATIONAL_ID_DIGITS = 14


def _replace_number(match: "re.Match[str]") -> str:
    digits = len(_DIGITS_ONLY.findall(match.group(0)))
    if digits < MIN_IDENTIFIER_DIGITS:
        return match.group(0)
    return "[id]" if digits == NATIONAL_ID_DIGITS else "[number]"


def scrub_for_external(text: str) -> str:
    """Return `text` with emails, phone-like and ID-like numbers replaced."""
    if not text:
        return text
    text = _EMAIL.sub("[email]", text)
    return _NUMBER_RUN.sub(_replace_number, text)