"""
file_map.py — Generates a structure-only outline of every file in the repository
into scripts/file_map.txt.

For each file it reports:
- Number of lines
- Approximate number of tokens

Never prints file bodies or secrets.

Usage:
    python scripts/file_map.py
    python scripts/file_map.py --out scripts/file_map.txt
"""

import os
import sys

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "file_map.txt")

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "uploads",
    ".vscode",
    "dist",
    "build",
}

EXCLUDE_EXTS = {
    ".pyc",
    ".db",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".zip",
    ".log",
    ".ico",
    ".svg",
}

EXCLUDE_FILES = {
    ".env",
    "roshetta.db",
    "package-lock.json",
}

# Rough approximation:
# ~4 characters per token works reasonably well for English/code.
CHARS_PER_TOKEN = 4


def estimate_tokens(text):
    """
    Estimate token count without requiring a model-specific tokenizer.

    This is intentionally an approximation.
    For exact token counts, use the tokenizer belonging to
    the LLM you are sending the files to.
    """
    if not text:
        return 0

    return max(1, round(len(text) / CHARS_PER_TOKEN))


def analyze_file(file_path):
    """
    Return:
        line_count,
        token_count
    """
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as file_obj:
            content = file_obj.read()

        line_count = content.count("\n")

        # If the file doesn't end with \n but contains content,
        # count the final line as well.
        if content and not content.endswith("\n"):
            line_count += 1

        token_count = estimate_tokens(content)

        return line_count, token_count

    except Exception:
        return 0, 0


def generate_map(out_path=DEFAULT_OUT):
    lines = []

    lines.append("# Structure-Only File Map — Roshetta Pharmacy System")
    lines.append("")
    lines.append(
        "> Token counts are approximate (~4 characters per token)."
    )
    lines.append("")

    root_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    total_files = 0
    total_lines = 0
    total_tokens = 0

    for root, dirs, files in os.walk(root_dir, topdown=True):

        # Remove excluded directories in-place so os.walk
        # does not enter them.
        dirs[:] = [
            d
            for d in dirs
            if d not in EXCLUDE_DIRS
            and not d.startswith(".")
        ]

        for f in sorted(files):

            if f in EXCLUDE_FILES:
                continue

            if any(f.endswith(ext) for ext in EXCLUDE_EXTS):
                continue

            full_path = os.path.join(root, f)

            rel_path = os.path.relpath(
                full_path,
                root_dir,
            ).replace("\\", "/")

            line_count, token_count = analyze_file(full_path)

            total_files += 1
            total_lines += line_count
            total_tokens += token_count

            lines.append(
                f"- `{rel_path}` "
                f"({line_count:,} lines, "
                f"~{token_count:,} tokens)"
            )

    lines.append("")
    lines.append("## Repository Totals")
    lines.append("")
    lines.append(f"- **Files:** {total_files:,}")
    lines.append(f"- **Lines:** {total_lines:,}")
    lines.append(f"- **Approx. tokens:** ~{total_tokens:,}")

    with open(out_path, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")

    print(
        f"File map written to {out_path} "
        f"({total_files:,} files, "
        f"{total_lines:,} lines, "
        f"~{total_tokens:,} tokens)."
    )


if __name__ == "__main__":
    out_file = DEFAULT_OUT

    if len(sys.argv) > 2 and sys.argv[1] == "--out":
        out_file = sys.argv[2]

    generate_map(out_file)
