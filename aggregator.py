"""
aggregator.py — Merges LLM and linter feedback into a clean, scored review.

Responsibilities:
- Deduplicate comments that flag the same line from both sources
- Assign final severity scores
- Build the PR summary text
- Calculate the overall quality score
"""

import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Score deductions per severity level
SCORE_DEDUCTIONS = {
    "critical":   15,
    "warning":     5,
    "suggestion":  1,
}

# Maximum deduction so score never goes below 0
MAX_DEDUCTION = 100


def aggregate_feedback(
    llm_comments:    List[Dict],
    linter_comments: List[Dict],
    llm_meta:        Dict = None,
) -> Tuple[List[Dict], str, float]:
    """
    Merge all feedback sources into a final comment list.

    Returns:
        final_comments : Deduplicated, sorted list of comments
        summary        : Human-readable summary string for the PR
        overall_score  : Float 0–100
    """
    llm_meta = llm_meta or {}

    # Tag each comment with its source
    for c in llm_comments:
        c.setdefault("source", "llm")
    for c in linter_comments:
        c.setdefault("source", "linter")

    all_comments = llm_comments + linter_comments

    # Deduplicate: if LLM and linter flag the same (file, line), keep LLM's richer message
    deduped = _deduplicate(all_comments)

    # Sort: critical first, then warning, then suggestion; within each group by file+line
    severity_order = {"critical": 0, "warning": 1, "suggestion": 2}
    deduped.sort(key=lambda c: (
        severity_order.get(c.get("severity", "suggestion"), 2),
        c.get("filename", ""),
        c.get("line_number") or 0,
    ))

    # Count by severity
    counts = {"critical": 0, "warning": 0, "suggestion": 0}
    for c in deduped:
        counts[c.get("severity", "suggestion")] += 1

    # Calculate score
    score = _calculate_score(counts, llm_meta.get("overall_score"))

    # Build summary text
    summary = _build_summary(counts, score, deduped, llm_meta.get("summary", ""))

    logger.info(
        "Aggregated: %d critical, %d warnings, %d suggestions → score %.0f",
        counts["critical"], counts["warning"], counts["suggestion"], score
    )

    return deduped, summary, score


# ── Private helpers ────────────────────────────────────────────────────────────

def _deduplicate(comments: List[Dict]) -> List[Dict]:
    """
    Remove duplicate comments on the same (file, line).
    LLM comments take priority over linter comments because they're richer.
    """
    seen   = {}   # key: (filename, line_number) → index in result list
    result = []

    # Process LLM comments first so they win deduplication
    llm_first = sorted(comments, key=lambda c: 0 if c.get("source") == "llm" else 1)

    for c in llm_first:
        key = (c.get("filename", ""), c.get("line_number"))
        if key not in seen:
            seen[key] = len(result)
            result.append(c)
        else:
            # Keep the higher-severity one
            existing   = result[seen[key]]
            sev_order  = {"critical": 0, "warning": 1, "suggestion": 2}
            if sev_order.get(c["severity"], 2) < sev_order.get(existing["severity"], 2):
                result[seen[key]] = c

    return result


def _calculate_score(counts: Dict, llm_score: float = None) -> float:
    """
    Compute a 0–100 quality score.
    Blends our deduction model with the LLM's holistic score if available.
    """
    deduction = (
        counts["critical"]   * SCORE_DEDUCTIONS["critical"]  +
        counts["warning"]    * SCORE_DEDUCTIONS["warning"]   +
        counts["suggestion"] * SCORE_DEDUCTIONS["suggestion"]
    )
    rule_score = max(0.0, 100.0 - deduction)

    if llm_score is not None:
        # Weight: 60% LLM holistic, 40% rule-based
        return round(0.6 * float(llm_score) + 0.4 * rule_score, 1)

    return round(rule_score, 1)


def _build_summary(
    counts:   Dict,
    score:    float,
    comments: List[Dict],
    llm_summary: str,
) -> str:
    """Build the markdown summary posted at the top of the PR."""
    total = sum(counts.values())

    if total == 0:
        return (
            "**No issues found.** This PR looks clean — great work!\n\n"
            f"{llm_summary}"
        ).strip()

    lines = []

    # Issue count table
    lines.append("### Issues found\n")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    if counts["critical"]:
        lines.append(f"| 🔴 Critical | {counts['critical']} |")
    if counts["warning"]:
        lines.append(f"| 🟡 Warning | {counts['warning']} |")
    if counts["suggestion"]:
        lines.append(f"| 🔵 Suggestion | {counts['suggestion']} |")
    lines.append(f"| **Total** | **{total}** |")

    # LLM's narrative summary
    if llm_summary:
        lines.append(f"\n### Assessment\n{llm_summary}")

    # Top critical issues callout
    criticals = [c for c in comments if c.get("severity") == "critical"][:3]
    if criticals:
        lines.append("\n### Critical issues to fix before merging")
        for c in criticals:
            lines.append(f"- **{c['filename']}** line {c.get('line_number', '?')}: {c['message']}")

    return "\n".join(lines)
