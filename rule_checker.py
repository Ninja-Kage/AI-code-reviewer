"""
rule_checker.py — Static analysis layer using Pylint (Python) and basic JS checks.

This runs deterministic linters on changed files and converts their output
into the same comment format as the LLM, so the aggregator can merge both.
"""

import os
import re
import json
import logging
import tempfile
import subprocess
from typing import List, Dict

logger = logging.getLogger(__name__)

# Map Pylint message IDs to our severity levels
PYLINT_SEVERITY_MAP = {
    "E": "critical",    # Errors
    "W": "warning",     # Warnings
    "R": "suggestion",  # Refactor suggestions
    "C": "suggestion",  # Convention
    "F": "critical",    # Fatal
}

# Map Pylint message IDs to categories
PYLINT_CATEGORY_MAP = {
    "E0001": "bug",          # SyntaxError
    "E0102": "bug",          # Redefinition
    "E0401": "bug",          # Import error
    "E1101": "bug",          # Module has no member
    "W0611": "style",        # Unused import
    "W0612": "style",        # Unused variable
    "W0613": "style",        # Unused argument
    "W0102": "bug",          # Dangerous default mutable
    "W0703": "bug",          # Broad except clause
    "C0114": "style",        # Missing module docstring
    "C0115": "style",        # Missing class docstring
    "C0116": "style",        # Missing function docstring
    "C0103": "style",        # Invalid name
    "R0201": "suggestion",   # Method could be a function
    "R0902": "suggestion",   # Too many instance attributes
    "R0912": "suggestion",   # Too many branches
    "R0914": "suggestion",   # Too many local variables
    "R0915": "suggestion",   # Too many statements
}


def run_static_analysis(files: List[Dict]) -> List[Dict]:
    """
    Run linters on all changed files and return a unified list of comments.
    """
    all_comments = []

    for file_info in files:
        filename = file_info.get("filename", "")
        content  = file_info.get("content", "")

        if not content:
            continue

        ext = os.path.splitext(filename)[1].lower()

        if ext == ".py":
            comments = _run_pylint(filename, content)
            all_comments.extend(comments)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            comments = _run_basic_js_checks(filename, content)
            all_comments.extend(comments)

    logger.info("Static analysis found %d issues", len(all_comments))
    return all_comments


# ── Python — Pylint ────────────────────────────────────────────────────────────

def _run_pylint(filename: str, content: str) -> List[Dict]:
    """Write content to a temp file, run Pylint, parse JSON output."""
    comments = []

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "pylint",
                tmp_path,
                "--output-format=json",
                "--disable=C0301",   # line-too-long (LLM handles style)
                "--disable=C0303",   # trailing-whitespace
                "--disable=W0105",   # pointless-string-statement
                "--score=no",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if not result.stdout.strip():
            return []

        issues = json.loads(result.stdout)

        for issue in issues:
            msg_id    = issue.get("message-id", "")
            type_char = msg_id[0] if msg_id else "C"
            severity  = PYLINT_SEVERITY_MAP.get(type_char, "suggestion")
            category  = PYLINT_CATEGORY_MAP.get(msg_id, "style")

            comments.append({
                "filename":    filename,
                "line_number": issue.get("line"),
                "severity":    severity,
                "category":    category,
                "source":      "linter",
                "message":     f"[{msg_id}] {issue.get('message', '')}",
                "suggestion":  None,
            })

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning("Pylint failed for %s: %s", filename, e)

    finally:
        os.unlink(tmp_path)

    return comments


# ── JavaScript / TypeScript — basic pattern checks ────────────────────────────

# Patterns that almost always indicate a bug or bad practice
JS_RULES = [
    (r"\beval\s*\(", "critical", "security",
     "Avoid eval() — it executes arbitrary code and is a security risk."),
    (r"\bconsole\.log\b", "suggestion", "style",
     "Remove console.log() before merging to production."),
    (r"\bvar\b", "warning", "style",
     "Use 'const' or 'let' instead of 'var' to avoid hoisting bugs."),
    (r"==(?!=)", "warning", "bug",
     "Use '===' instead of '==' to avoid type coercion surprises."),
    (r"!=(?!=)", "warning", "bug",
     "Use '!==' instead of '!=' for strict inequality."),
    (r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{4,}['\"]", "critical", "security",
     "Hardcoded credential detected. Move secrets to environment variables."),
    (r"\bTODO\b|\bFIXME\b|\bHACK\b", "suggestion", "style",
     "Unresolved TODO/FIXME comment — address before merging."),
    (r"catch\s*\(\s*\)\s*\{?\s*\}", "warning", "bug",
     "Empty catch block swallows errors silently."),
    (r"setTimeout\s*\([^,]+,\s*0\s*\)", "suggestion", "performance",
     "setTimeout with 0ms is a code smell — consider a proper async pattern."),
]


def _run_basic_js_checks(filename: str, content: str) -> List[Dict]:
    """Apply regex-based rules to JavaScript/TypeScript files."""
    comments = []
    lines    = content.splitlines()

    for lineno, line in enumerate(lines, start=1):
        for pattern, severity, category, message in JS_RULES:
            if re.search(pattern, line):
                comments.append({
                    "filename":    filename,
                    "line_number": lineno,
                    "severity":    severity,
                    "category":    category,
                    "source":      "linter",
                    "message":     message,
                    "suggestion":  None,
                })

    return comments
