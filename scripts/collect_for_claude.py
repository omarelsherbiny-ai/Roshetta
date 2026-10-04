"""
collect_for_claude.py — Collects named files into scripts/needed_files.txt for assistant review.
Usage:
    python scripts/collect_for_claude.py file1 file2 ...
"""

import sys
import os

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "needed_files.txt")

def collect(files):
    output_lines = []
    missing = []
    for filepath in files:
        if not os.path.exists(filepath):
            missing.append(filepath)
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            ext = os.path.splitext(filepath)[1].lstrip(".") or "text"
            output_lines.append(f"=== File: {filepath} ===")
            output_lines.append(f"```{ext}")
            output_lines.append(content)
            output_lines.append("```\n")
        except Exception as e:
            output_lines.append(f"=== Error reading {filepath}: {e} ===\n")

    if missing:
        output_lines.insert(0, f"=== Missing files ({len(missing)}): {', '.join(missing)} ===\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("\n".join(output_lines))

    print(f"Collected {len(files) - len(missing)} file(s) into {OUTPUT_FILE}")
    if missing:
        print(f"Warning: {len(missing)} file(s) not found: {missing}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/collect_for_claude.py <file1> <file2> ...")
        sys.exit(1)
    collect(sys.argv[1:])
