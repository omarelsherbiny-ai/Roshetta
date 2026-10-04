"""
file_map.py — Generates a structure-only outline of every file in the repository into scripts/file_map.txt.
Never prints file bodies or secrets.
Usage:
    python scripts/file_map.py [--out scripts/file_map.txt]
"""

import os
import sys

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "file_map.txt")
EXCLUDE_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__", ".pytest_cache", "uploads", ".vscode", "dist", "build"}
EXCLUDE_EXTS = {".pyc", ".db", ".png", ".jpg", ".jpeg", ".webp", ".zip", ".log", ".ico", ".svg"}
EXCLUDE_FILES = {".env", "roshetta.db", "package-lock.json"}

def generate_map(out_path=DEFAULT_OUT):
    lines = []
    lines.append("# Structure-Only File Map — Roshetta Pharmacy System\n")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    for root, dirs, files in os.walk(root_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        
        for f in sorted(files):
            if f in EXCLUDE_FILES or any(f.endswith(ext) for ext in EXCLUDE_EXTS):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                    line_count = sum(1 for _ in file_obj)
            except Exception:
                line_count = 0

            lines.append(f"- `{rel_path}` ({line_count} lines)")

    with open(out_path, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")

    print(f"File map written to {out_path} ({len(lines)-1} files indexed).")

if __name__ == "__main__":
    out_file = DEFAULT_OUT
    if len(sys.argv) > 2 and sys.argv[1] == "--out":
        out_file = sys.argv[2]
    generate_map(out_file)
