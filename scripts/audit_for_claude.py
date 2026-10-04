# scripts/audit_for_claude.py (read-only project audit: writes scripts/audit_report.txt for Claude)
"""Run from the project root:  python scripts/audit_for_claude.py

Changes nothing. It scans the repo and writes scripts/audit_report.txt with:
  1. api.ts functions that nothing else imports (unused client code)
  2. backend api modules that main.py never mentions (possibly unregistered)
  3. web route files, and files over 600 lines
  4. risky patterns in web/src: alert(, confirm(, console.log, 'as any', TODO/FIXME, localhost, zoom-lock tags
  5. output of optional tools if they are installed: tsc (type check), vulture (unused Python), ruff F401/F841
Nothing is sent anywhere; upload the report file to the chat.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "audit_report.txt"
SKIP_DIRS = {"node_modules", ".next", ".venv", "venv", "__pycache__", ".git", "dist", "build", "mobile-later"}
MAX_TOOL_LINES = 120

lines_out = []


def say(text=""):
    lines_out.append(text)


def skipped(path):
    """True for anything inside a virtual environment or other generated folder (.venv, .venv-verify, venv*, site-packages)."""
    return any(
        part in SKIP_DIRS or part == "site-packages" or part.startswith(".venv") or part.startswith("venv")
        for part in path.parts
    )


def walk(base, suffixes):
    base = ROOT / base
    if not base.exists():
        return
    for path in base.rglob("*"):
        if path.is_file() and path.suffix in suffixes and not skipped(path.relative_to(ROOT)):
            yield path


def read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def rel(path):
    return path.relative_to(ROOT).as_posix()


def run_tool(title, command, cwd=None, shell=False):
    say(f"--- {title} ---")
    try:
        result = subprocess.run(
            command, cwd=cwd or ROOT, shell=shell, capture_output=True, text=True, timeout=600,
        )
        text = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
        if not text:
            say("(no output; the tool found nothing to report)")
        for line in text[:MAX_TOOL_LINES]:
            say(line)
        if len(text) > MAX_TOOL_LINES:
            say(f"... {len(text) - MAX_TOOL_LINES} more lines cut")
    except FileNotFoundError:
        say("(tool not found, skipped)")
    except subprocess.TimeoutExpired:
        say("(timed out after 10 minutes, skipped)")
    except Exception as error:  # report, never crash the audit
        say(f"(could not run: {error})")
    say()


def main():
    say("ROSHETTA AUDIT REPORT (read-only scan)")
    say(f"root: {ROOT}")
    say()

    web_files = list(walk("web/src", {".ts", ".tsx"}))
    web_text = {path: read(path) for path in web_files}

    # 1. api.ts exports nothing else uses
    say("=== 1. web/src/lib/api.ts: exported functions no other file uses ===")
    api_path = ROOT / "web/src/lib/api.ts"
    if api_path.exists():
        api_text = read(api_path)
        names = re.findall(r"export\s+(?:async\s+)?function\s+(\w+)", api_text)
        unused = []
        for name in names:
            pattern = re.compile(rf"\b{name}\b")
            used = any(pattern.search(text) for path, text in web_text.items() if path != api_path)
            if not used:
                unused.append(name)
        say(f"{len(names)} exported functions, {len(unused)} not used anywhere else")
        for name in unused:
            say(f"  unused: {name}")
    else:
        say("web/src/lib/api.ts not found")
    say()

    # 2. backend modules main.py never mentions
    say("=== 2. server/app/api modules that main.py never mentions ===")
    main_py = ROOT / "server/app/main.py"
    api_dir = ROOT / "server/app/api"
    if main_py.exists() and api_dir.exists():
        main_text = read(main_py)
        for path in sorted(api_dir.glob("*.py")):
            if path.stem == "__init__":
                continue
            if not re.search(rf"\b{path.stem}\b", main_text):
                say(f"  not mentioned in main.py: {rel(path)}")
        say("(a module listed here is either registered another way or never served)")
    else:
        say("main.py or the api folder not found")
    say()

    # 3. routes and big files
    say("=== 3. Routes and big files ===")
    routes = sorted(rel(p) for p in walk("web/src/app", {".tsx"}) if p.name == "page.tsx")
    say(f"{len(routes)} page.tsx route files:")
    for route in routes:
        say(f"  {route}")
    say("Files over 600 lines (web/src, server, agents, tests):")
    big = []
    for base, suffixes in (("web/src", {".ts", ".tsx"}), ("server", {".py"}), ("agents", {".py"}), ("tests", {".py"})):
        for path in walk(base, suffixes):
            count = len(read(path).splitlines())
            if count > 600:
                big.append((count, rel(path)))
    for count, path in sorted(big, reverse=True):
        say(f"  {count:5d}  {path}")
    if not big:
        say("  none")
    say()

    # 4. risky patterns in the web client
    say("=== 4. Risky patterns in web/src ===")
    patterns = {
        "alert(": r"(?<![\w.])alert\(",
        "confirm(": r"window\.confirm\(|(?<![\w.])confirm\(",
        "console.log": r"console\.log\(",
        "as any": r"\bas any\b",
        "TODO/FIXME": r"\b(TODO|FIXME)\b",
        "localhost": r"localhost",
        "zoom lock (user-scalable=no / maximum-scale)": r"user-scalable=no|maximum-scale",
        "hardcoded currency text in JSX": r">\s*ج\.م\s*<",
    }
    for label, pattern in patterns.items():
        hits = []
        regex = re.compile(pattern)
        for path, text in web_text.items():
            for number, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel(path)}:{number}")
        say(f"{label}: {len(hits)}")
        for hit in hits[:25]:
            say(f"  {hit}")
        if len(hits) > 25:
            say(f"  ... {len(hits) - 25} more")
    say()

    # 5. optional tools
    say("=== 5. Tool output ===")
    web_dir = ROOT / "web"
    if (web_dir / "node_modules").exists():
        run_tool("tsc --noEmit (type check of the web client)", "npx tsc --noEmit", cwd=web_dir, shell=True)
    else:
        say("--- tsc skipped: web/node_modules not found (run npm install in web/) ---")
        say()
    run_tool("vulture (unused Python code, confidence 80+)",
             [sys.executable, "-m", "vulture", "server/app", "agents", "scripts", "--min-confidence", "80"])
    run_tool("ruff F401 F841 (unused imports and variables)",
             [sys.executable, "-m", "ruff", "check", "server", "agents", "tests", "--select", "F401,F841",
              "--output-format", "concise", "--no-cache"])

    OUT.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines_out)} lines). Upload it to the chat.")


if __name__ == "__main__":
    main()