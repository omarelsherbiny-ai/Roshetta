# scripts/patch_unknown_cost_tests.py
# The sale in test_sale_with_unknown_purchase_cost_does_not_report_zero_cost_profit used to be
# priced with a made-up 35 EGP default; it is now priced from the catalog (the product is created
# with sell price 50). This changes the expected 35 to 50 inside that one test, in both files.
# Run from the project root: python scripts/patch_unknown_cost_tests.py
import re
from pathlib import Path

NAME = "def test_sale_with_unknown_purchase_cost_does_not_report_zero_cost_profit"
for path in (Path("tests/test_ai_api.py"), Path("tests/test_api_security.py")):
    text = path.read_text(encoding="utf-8")
    start = text.find(NAME)
    if start < 0:
        print(f"{path}: test not found, nothing changed")
        continue
    end = text.find("\n    def ", start + 10)
    end = len(text) if end < 0 else end
    body = text[start:end]
    new_body, count = re.subn(r"(?<![\w.])35(?![\w.])", "50", body)
    path.write_text(text[:start] + new_body + text[end:], encoding="utf-8")
    print(f"{path}: {count} change(s)")
    for line in new_body.splitlines():
        if "50" in line and "unit_sell_price" not in line:
            print("   ", line.strip())