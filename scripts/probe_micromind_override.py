# scripts/probe_micromind_override.py
"""One-time check: does the MicroMind flow accept a per-request ROSHETTA_TOKEN?

Run from the project root:   python scripts/probe_micromind_override.py
It reads MICROMIND_API_URL from server/.env, sends the harmless text
"override-probe" as the variable, and prints the flow's reply (the URL and the
probe text are the only things used; no real token is involved).

Read the result: if the tool output in the reply says "tokenFrom": "variable",
the flow accepts overrides. If it says "test constant", it does not (see the
chat for what to switch on).
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

ENV_FILE = pathlib.Path(__file__).resolve().parent.parent / "server" / ".env"


def read_url() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("MICROMIND_API_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> int:
    url = read_url()
    if not url:
        print("MICROMIND_API_URL not found in server/.env")
        return 1
    body = {
        "question": "Call the search_inventory tool once with no arguments and copy its raw output exactly.",
        "overrideConfig": {"vars": {"ROSHETTA_TOKEN": "override-probe"}},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8", "replace")
            print("HTTP", response.status)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        print("HTTP", exc.code)
    except Exception as exc:  # network or timeout
        print("Request failed:", type(exc).__name__)
        return 1
    print(text[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())