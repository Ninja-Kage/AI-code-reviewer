"""
main.py — FastAPI application: webhook receiver + REST API for the dashboard.
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime
from typing import List

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import get_db, init_db
from models import Review, ReviewComment, Repository
from github_client import get_pr_diff, get_pr_details, post_review_comments
from diff_parser import parse_diff
from llm_engine import review_with_llm, get_llm_summary
from rule_checker import run_static_analysis
from aggregator import aggregate_feedback

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

app = FastAPI(
    title="AI Code Reviewer",
    description="Automated AI-powered pull request reviewer",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://your-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialised ✓")


# ── Webhook endpoint ───────────────────────────────────────────────────────────

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives GitHub webhook events.
    Verifies the HMAC signature, then fires the review pipeline in the background.
    """
    body      = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event     = request.headers.get("X-GitHub-Event", "")

    _verify_webhook_signature(body, signature)

    data = await request.json()

    if event == "pull_request" and data.get("action") in ("opened", "synchronize", "reopened"):
        repo_name = data["repository"]["full_name"]
        pr_number = data["pull_request"]["number"]
        logger.info("PR #%d opened on %s — scheduling review", pr_number, repo_name)
        background_tasks.add_task(_run_review_pipeline, repo_name, pr_number)

    return {"status": "received", "event": event}


# ── Dashboard REST API ─────────────────────────────────────────────────────────

@app.get("/api/reviews")
def list_reviews(limit: int = 20, db: Session = Depends(get_db)):
    """Return the most recent reviews for the dashboard."""
    reviews = (
        db.query(Review)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_review(r) for r in reviews]


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int, db: Session = Depends(get_db)):
    """Return a single review with all its inline comments."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    result = _serialize_review(review)
    result["comments"] = [_serialize_comment(c) for c in review.comments]
    return result


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Aggregate stats for the dashboard overview cards."""
    reviews = db.query(Review).filter(Review.status == "completed").all()
    if not reviews:
        return {"total_reviews": 0, "avg_score": 0, "total_issues": 0}

    avg_score    = sum(r.overall_score or 0 for r in reviews) / len(reviews)
    total_issues = sum((r.critical or 0) + (r.warnings or 0) for r in reviews)

    return {
        "total_reviews": len(reviews),
        "avg_score":     round(avg_score, 1),
        "total_issues":  total_issues,
        "criticals":     sum(r.critical or 0 for r in reviews),
        "warnings":      sum(r.warnings or 0 for r in reviews),
        "suggestions":   sum(r.suggestions or 0 for r in reviews),
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}


# ── Background review pipeline ─────────────────────────────────────────────────

async def _run_review_pipeline(repo_name: str, pr_number: int):
    """
    Full review pipeline — runs in the background after webhook fires.
    Steps: fetch → parse → analyse → aggregate → post → save to DB
    """
    db = next(get_db())

    try:
        # Ensure repo record exists
        repo_record = db.query(Repository).filter_by(full_name=repo_name).first()
        if not repo_record:
            owner, name = repo_name.split("/", 1)
            repo_record = Repository(full_name=repo_name, owner=owner, name=name)
            db.add(repo_record)
            db.commit()
            db.refresh(repo_record)

        # Create pending review record
        pr_details = get_pr_details(repo_name, pr_number)
        review = Review(
            repo_id   = repo_record.id,
            pr_number = pr_number,
            pr_title  = pr_details.get("title"),
            pr_author = pr_details.get("author"),
            pr_url    = pr_details.get("url"),
            status    = "in_progress",
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        # Step 1 — Fetch diff
        logger.info("[Review %d] Fetching diff …", review.id)
        diff_text, files = get_pr_diff(repo_name, pr_number)

        # Step 2 — Parse into chunks
        chunks = parse_diff(files)
        logger.info("[Review %d] Parsed %d chunks", review.id, len(chunks))

        # Step 3 — Run both analysis tracks
        logger.info("[Review %d] Running LLM review …", review.id)
        llm_comments = review_with_llm(chunks)
        llm_meta     = get_llm_summary(chunks)

        logger.info("[Review %d] Running static analysis …", review.id)
        lint_comments = run_static_analysis(files)

        # Step 4 — Aggregate
        final_comments, summary, score = aggregate_feedback(
            llm_comments, lint_comments, llm_meta
        )

        # Step 5 — Post to GitHub
        logger.info("[Review %d] Posting %d comments to GitHub …", review.id, len(final_comments))
        post_review_comments(repo_name, pr_number, final_comments, summary, score)

        # Step 6 — Save results to DB
        counts = {"critical": 0, "warning": 0, "suggestion": 0}
        for c in final_comments:
            sev = c.get("severity", "suggestion")
            counts[sev] = counts.get(sev, 0) + 1

            db.add(ReviewComment(
                review_id   = review.id,
                filename    = c.get("filename", ""),
                line_number = c.get("line_number"),
                severity    = sev,
                category    = c.get("category", "style"),
                source      = c.get("source", "llm"),
                message     = c.get("message", ""),
                suggestion  = c.get("suggestion"),
            ))

        review.status        = "completed"
        review.overall_score = score
        review.summary       = summary
        review.total_issues  = len(final_comments)
        review.critical      = counts["critical"]
        review.warnings      = counts["warning"]
        review.suggestions   = counts["suggestion"]
        review.completed_at  = datetime.utcnow()
        db.commit()

        logger.info("[Review %d] Complete — score: %.0f", review.id, score)

    except Exception as e:
        logger.error("Review pipeline failed for %s PR#%d: %s", repo_name, pr_number, e)
        if "review" in dir():
            review.status = "failed"
            db.commit()
    finally:
        db.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _verify_webhook_signature(body: bytes, signature: str):
    if not WEBHOOK_SECRET:
        return  # Skip in dev if secret not set
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _serialize_review(r: Review) -> dict:
    return {
        "id":            r.id,
        "pr_number":     r.pr_number,
        "pr_title":      r.pr_title,
        "pr_author":     r.pr_author,
        "pr_url":        r.pr_url,
        "overall_score": r.overall_score,
        "total_issues":  r.total_issues,
        "critical":      r.critical,
        "warnings":      r.warnings,
        "suggestions":   r.suggestions,
        "summary":       r.summary,
        "status":        r.status,
        "created_at":    r.created_at.isoformat() if r.created_at else None,
        "completed_at":  r.completed_at.isoformat() if r.completed_at else None,
    }


def _serialize_comment(c: ReviewComment) -> dict:
    return {
        "id":          c.id,
        "filename":    c.filename,
        "line_number": c.line_number,
        "severity":    c.severity,
        "category":    c.category,
        "source":      c.source,
        "message":     c.message,
        "suggestion":  c.suggestion,
    }
