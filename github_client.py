"""
github_client.py — All GitHub API interactions
Handles fetching PR diffs and posting review comments back.
"""

import os
import logging
from typing import List, Dict, Tuple
from github import Github, GithubException
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Initialise the GitHub client once at import time
_github = Github(os.getenv("GITHUB_TOKEN"))

# File extensions we know how to review
REVIEWABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".cpp", ".c", ".cs",
    ".rb", ".php", ".swift", ".kt", ".rs"
}

# Skip generated / vendor files
SKIP_PATTERNS = [
    "package-lock.json", "yarn.lock", "poetry.lock",
    "node_modules/", "__pycache__/", ".min.js",
    "migrations/", "dist/", "build/"
]


def get_pr_details(repo_name: str, pr_number: int) -> Dict:
    """Return basic metadata about the PR."""
    try:
        repo = _github.get_repo(repo_name)
        pr   = repo.get_pull(pr_number)
        return {
            "title":  pr.title,
            "author": pr.user.login,
            "url":    pr.html_url,
            "base":   pr.base.ref,
            "head":   pr.head.ref,
        }
    except GithubException as e:
        logger.error("Failed to fetch PR details: %s", e)
        return {}


def get_pr_diff(repo_name: str, pr_number: int) -> Tuple[str, List[Dict]]:
    """
    Fetch the diff and file contents for a PR.

    Returns:
        diff_text: Raw unified diff string
        files:     List of dicts with filename + full file content
    """
    try:
        repo  = _github.get_repo(repo_name)
        pr    = repo.get_pull(pr_number)
        files = []
        diff_text = ""

        for f in pr.get_files():
            # Skip files we can't review
            if _should_skip(f.filename):
                continue
            if not f.patch:
                continue  # Binary file or too large

            diff_text += f"\n\n=== {f.filename} ===\n{f.patch}"

            # Also fetch the full file for richer context
            content = _get_file_content(repo, f.filename, pr.head.sha)
            files.append({
                "filename": f.filename,
                "patch":    f.patch,
                "content":  content,
                "additions": f.additions,
                "deletions": f.deletions,
                "status":    f.status,   # "added", "modified", "removed"
            })

        logger.info("Fetched diff for PR #%d: %d files", pr_number, len(files))
        return diff_text, files

    except GithubException as e:
        logger.error("GitHub API error fetching diff: %s", e)
        raise


def post_review_comments(
    repo_name:    str,
    pr_number:    int,
    comments:     List[Dict],
    summary:      str,
    overall_score: float
) -> None:
    """
    Post the review back to GitHub as:
    - A top-level summary comment with the score
    - Inline comments on specific lines
    """
    try:
        repo   = _github.get_repo(repo_name)
        pr     = repo.get_pull(pr_number)
        commit = list(pr.get_commits())[-1]  # Latest commit

        # Build the summary comment with emoji indicators
        score_emoji = "✅" if overall_score >= 80 else "⚠️" if overall_score >= 60 else "❌"
        summary_body = (
            f"## {score_emoji} AI Code Review — Score: {overall_score:.0f}/100\n\n"
            f"{summary}\n\n"
            f"---\n*Reviewed by [AI Code Reviewer](https://github.com) • "
            f"{len(comments)} issue(s) found*"
        )
        pr.create_issue_comment(summary_body)

        # Post inline comments (GitHub requires line to exist in diff)
        inline = []
        for c in comments:
            if c.get("line_number") and c.get("filename"):
                severity_icon = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}.get(
                    c["severity"], "💬"
                )
                body = (
                    f"{severity_icon} **{c['severity'].upper()} — {c.get('category', 'review')}**\n\n"
                    f"{c['message']}"
                )
                if c.get("suggestion"):
                    body += f"\n\n**Suggested fix:**\n```\n{c['suggestion']}\n```"

                inline.append({
                    "path": c["filename"],
                    "line": c["line_number"],
                    "body": body
                })

        if inline:
            pr.create_review(
                commit=commit,
                body="",
                event="COMMENT",
                comments=inline
            )

        logger.info("Posted review to PR #%d (%d inline comments)", pr_number, len(inline))

    except GithubException as e:
        logger.error("Failed to post review comments: %s", e)
        raise


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_file_content(repo, filename: str, sha: str) -> str:
    """Safely fetch a file's full content at a given commit SHA."""
    try:
        return repo.get_contents(filename, ref=sha).decoded_content.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _should_skip(filename: str) -> bool:
    """Return True if we should skip this file."""
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext not in REVIEWABLE_EXTENSIONS:
        return True
    return any(pattern in filename for pattern in SKIP_PATTERNS)
