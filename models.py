"""
models.py — SQLAlchemy database models
Stores every review, comment, and repo config for the dashboard.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Boolean, Enum as SAEnum, Float
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Repository(Base):
    """A GitHub repo that has the bot installed."""
    __tablename__ = "repositories"

    id           = Column(Integer, primary_key=True)
    full_name    = Column(String(255), unique=True, nullable=False)  # e.g. "user/repo"
    owner        = Column(String(100), nullable=False)
    name         = Column(String(100), nullable=False)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    reviews      = relationship("Review", back_populates="repository", cascade="all, delete")


class Review(Base):
    """One full review of a pull request."""
    __tablename__ = "reviews"

    id            = Column(Integer, primary_key=True)
    repo_id       = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    pr_number     = Column(Integer, nullable=False)
    pr_title      = Column(String(500))
    pr_author     = Column(String(100))
    pr_url        = Column(String(500))
    overall_score = Column(Float)                    # 0–100
    total_issues  = Column(Integer, default=0)
    critical      = Column(Integer, default=0)
    warnings      = Column(Integer, default=0)
    suggestions   = Column(Integer, default=0)
    summary       = Column(Text)
    status        = Column(
        SAEnum("pending", "in_progress", "completed", "failed", name="review_status"),
        default="pending"
    )
    created_at    = Column(DateTime, default=datetime.utcnow)
    completed_at  = Column(DateTime)

    repository    = relationship("Repository", back_populates="reviews")
    comments      = relationship("ReviewComment", back_populates="review", cascade="all, delete")


class ReviewComment(Base):
    """A single inline comment on a specific line of code."""
    __tablename__ = "review_comments"

    id          = Column(Integer, primary_key=True)
    review_id   = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    filename    = Column(String(500), nullable=False)
    line_number = Column(Integer)
    severity    = Column(
        SAEnum("critical", "warning", "suggestion", name="severity_level"),
        nullable=False
    )
    category    = Column(String(50))       # "bug", "security", "performance", "style"
    source      = Column(String(20))       # "llm" or "linter"
    message     = Column(Text, nullable=False)
    suggestion  = Column(Text)             # The fix suggestion
    created_at  = Column(DateTime, default=datetime.utcnow)

    review      = relationship("Review", back_populates="comments")
