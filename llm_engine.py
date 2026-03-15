"""
llm_engine.py — Groq API integration for AI code reviews.
Groq runs Llama3-70b — free, fast, excellent code understanding.
"""

import os
import json
import logging
from typing import List, Dict
from groq import Groq
from dotenv import load_dotenv
from diff_parser import build_review_prompt_block

load_dotenv()
logger = logging.getLogger(__name__)

# Initialise Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = os.getenv("GROQ_MODEL", "llama3-70b-8192")

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a principal software engineer at Microsoft with 15 years \
of experience conducting code reviews. You are meticulous, constructive, and \
prioritise correctness, security, and maintainability.

When reviewing code you will:
1. Identify BUGS — logic errors, null pointer risks, off-by-one errors, race conditions
2. Flag SECURITY issues — SQL injection, XSS, hardcoded credentials, insecure deserialization
3. Spot PERFORMANCE problems — N+1 queries, unnecessary loops, memory leaks
4. Note STYLE violations — naming conventions, dead code, over-complexity
5. Give SUGGESTIONS — cleaner patterns, better library usage, missing tests

CRITICAL: You must respond ONLY with valid JSON. No markdown, no backticks, no prose.
Return exactly this structure:
{
  "comments": [
    {
      "filename": "path/to/file.py",
      "line_number": 42,
      "severity": "critical",
      "category": "security",
      "message": "Clear explanation of the issue",
      "suggestion": "Concrete fix or improved code"
    }
  ],
  "summary": "2-3 sentence overall assessment",
  "overall_score": 75
}

severity must be one of: critical, warning, suggestion
category must be one of: bug, security, performance, style, suggestion
overall_score is 0-100 (100 = perfect, 0 = do not merge)
If code is clean, return empty comments array with high score.
Do NOT wrap your response in markdown code blocks.
"""


def review_with_llm(chunks: List[Dict]) -> List[Dict]:
    """
    Send code chunks to Groq Llama3 and return flat list of comments.
    """
    if not chunks:
        return []

    all_comments = []
    batch_size = 4  # Slightly smaller batches — Llama context management

    for i in range(0, len(chunks), batch_size):
        batch  = chunks[i: i + batch_size]
        result = _review_batch(batch)
        all_comments.extend(result.get("comments", []))

    logger.info("Groq LLM produced %d comments", len(all_comments))
    return all_comments


def get_llm_summary(chunks: List[Dict]) -> Dict:
    """Get overall PR summary + score from Groq."""
    if not chunks:
        return {"summary": "No reviewable changes found.", "overall_score": 100}

    result = _review_batch(chunks[:3])
    return {
        "summary":       result.get("summary", "Review completed."),
        "overall_score": result.get("overall_score", 75),
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _review_batch(chunks: List[Dict]) -> Dict:
    """Send one batch to Groq and parse response."""

    user_message = "Review the following code changes and return JSON only:\n\n"
    for chunk in chunks:
        user_message += "---\n"
        user_message += build_review_prompt_block(chunk)
        user_message += "\n"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        raw = response.choices[0].message.content.strip()

        # Groq sometimes wraps in markdown — strip it just in case
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)

        # Validate and fill defaults
        result.setdefault("comments", [])
        result.setdefault("summary", "")
        result.setdefault("overall_score", 75)

        # Sanitise each comment
        valid_severities  = {"critical", "warning", "suggestion"}
        valid_categories  = {"bug", "security", "performance", "style", "suggestion"}
        clean_comments = []
        for c in result["comments"]:
            c["severity"] = c.get("severity", "suggestion").lower()
            c["category"] = c.get("category", "style").lower()
            if c["severity"] not in valid_severities:
                c["severity"] = "suggestion"
            if c["category"] not in valid_categories:
                c["category"] = "style"
            clean_comments.append(c)
        result["comments"] = clean_comments

        return result

    except json.JSONDecodeError as e:
        logger.error("Groq returned invalid JSON: %s\nRaw: %s", e, raw[:300])
        return {
            "comments": [],
            "summary": "Review failed — model returned invalid JSON.",
            "overall_score": 50
        }

    except Exception as e:
        logger.error("Groq API error: %s", e)
        return {
            "comments": [],
            "summary": "Review failed — API error.",
            "overall_score": 50
        }