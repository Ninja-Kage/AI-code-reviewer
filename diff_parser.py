"""
diff_parser.py — Parses raw GitHub unified diffs into clean, reviewable chunks.

A unified diff looks like:
    @@ -10,7 +10,9 @@ def foo():
    -    old_line()
    +    new_line()
     unchanged_line()

We extract just the new/modified lines along with context so the LLM
can understand what changed without noise.
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Maximum characters to send to LLM per chunk (keeps token cost down)
MAX_CHUNK_CHARS = 3000


def parse_diff(files: List[Dict]) -> List[Dict]:
    """
    Turn a list of GitHub file dicts into clean review chunks.

    Each chunk contains:
        filename    : path to the file
        language    : detected language
        hunk_header : the @@ ... @@ line showing where in the file
        added_lines : list of (line_number, code) for new/changed lines
        context     : surrounding lines for context
        raw_patch   : the original patch string (truncated)
    """
    chunks = []

    for file_info in files:
        filename = file_info.get("filename", "")
        patch    = file_info.get("patch", "")

        if not patch:
            continue

        language = _detect_language(filename)
        hunks    = _split_into_hunks(patch)

        for hunk in hunks:
            added_lines, context = _extract_lines(hunk["lines"], hunk["start_line"])

            if not added_lines:
                continue  # Nothing new to review in this hunk

            chunk = {
                "filename":    filename,
                "language":    language,
                "hunk_header": hunk["header"],
                "start_line":  hunk["start_line"],
                "added_lines": added_lines,
                "context":     context,
                "raw_patch":   hunk["raw"][:MAX_CHUNK_CHARS],
            }
            chunks.append(chunk)

    logger.info("Parsed %d reviewable chunks from %d files", len(chunks), len(files))
    return chunks


def build_review_prompt_block(chunk: Dict) -> str:
    """
    Format a chunk into a clean text block for the LLM prompt.

    Produces something like:
        File: backend/utils.py (Python)
        Lines 42-55:
        42 | def process(data):
        43 |+    result = eval(data)   <- NEW
        44 |     return result
    """
    lines_block = ""
    for (lineno, code, is_new) in chunk["context"]:
        marker = "+" if is_new else " "
        lines_block += f"{lineno:4d} |{marker}  {code}\n"

    return (
        f"File: {chunk['filename']} ({chunk['language']})\n"
        f"Hunk: {chunk['hunk_header']}\n"
        f"\n{lines_block}"
    )


# ── Private helpers ────────────────────────────────────────────────────────────

def _split_into_hunks(patch: str) -> List[Dict]:
    """Split a patch string on @@ markers into individual hunks."""
    # Pattern: @@ -old_start,old_count +new_start,new_count @@ optional_context
    hunk_header_re = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@(.*)$")
    hunks = []
    current_hunk = None

    for raw_line in patch.splitlines():
        m = hunk_header_re.match(raw_line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {
                "header":     raw_line.strip(),
                "start_line": int(m.group(1)),
                "lines":      [],
                "raw":        raw_line + "\n",
            }
        elif current_hunk is not None:
            current_hunk["lines"].append(raw_line)
            current_hunk["raw"] += raw_line + "\n"

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def _extract_lines(lines: List[str], start_line: int):
    """
    Walk through hunk lines and separate added lines from context.

    Returns:
        added_lines : [(line_number, code_str)]  — only new lines
        context     : [(line_number, code_str, is_new)]  — all lines with marker
    """
    added_lines = []
    context     = []
    current_line = start_line

    for raw in lines:
        if raw.startswith("+"):
            code = raw[1:]  # strip the leading +
            added_lines.append((current_line, code))
            context.append((current_line, code, True))
            current_line += 1
        elif raw.startswith("-"):
            # Deleted line — doesn't advance new-file line counter
            pass
        elif raw.startswith("\\"):
            # "\ No newline at end of file" — skip
            pass
        else:
            # Context line (unchanged)
            code = raw[1:] if raw.startswith(" ") else raw
            context.append((current_line, code, False))
            current_line += 1

    return added_lines, context


def _detect_language(filename: str) -> str:
    """Return a human-readable language name from the file extension."""
    ext_map = {
        ".py":   "Python",
        ".js":   "JavaScript",
        ".ts":   "TypeScript",
        ".jsx":  "React JSX",
        ".tsx":  "React TSX",
        ".java": "Java",
        ".go":   "Go",
        ".cpp":  "C++",
        ".c":    "C",
        ".cs":   "C#",
        ".rb":   "Ruby",
        ".php":  "PHP",
        ".swift":"Swift",
        ".kt":   "Kotlin",
        ".rs":   "Rust",
        ".sh":   "Shell",
        ".yml":  "YAML",
        ".yaml": "YAML",
        ".json": "JSON",
        ".sql":  "SQL",
        ".html": "HTML",
        ".css":  "CSS",
    }
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext_map.get(ext, "Unknown")
