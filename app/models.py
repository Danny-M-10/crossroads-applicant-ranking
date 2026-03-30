import datetime
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime,
    ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRole(Base):
    __tablename__ = "job_roles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    criteria = Column(JSON, nullable=False)
    # criteria format: [{"name": "CDL License", "weight": 25, "description": "Valid CDL Class B or higher"}, ...]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    ranking_sessions = relationship("RankingSession", back_populates="job_role")


class RankingSession(Base):
    __tablename__ = "ranking_sessions"

    id = Column(Integer, primary_key=True, index=True)
    job_role_id = Column(Integer, ForeignKey("job_roles.id"), nullable=False)
    folder_path = Column(String(500), nullable=False)
    status = Column(SAEnum(SessionStatus), default=SessionStatus.PENDING)
    total_candidates = Column(Integer, default=0)
    scored_candidates = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)

    job_role = relationship("JobRole", back_populates="ranking_sessions")
    candidates = relationship(
        "Candidate",
        back_populates="ranking_session",
        order_by="Candidate.rank",
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    ranking_session_id = Column(Integer, ForeignKey("ranking_sessions.id"), nullable=False)
    filename = Column(String(300), nullable=False)
    candidate_name = Column(String(200), nullable=True)
    resume_text = Column(Text, nullable=False)
    weighted_total = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    ai_summary = Column(Text, nullable=True)
    raw_scores = Column(JSON, nullable=True)
    scoring_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    ranking_session = relationship("RankingSession", back_populates="candidates")
    criterion_scores = relationship("CriterionScore", back_populates="candidate")


class CriterionScore(Base):
    __tablename__ = "criterion_scores"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    criterion_name = Column(String(200), nullable=False)
    score = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    weighted_score = Column(Float, nullable=False)
    justification = Column(Text, nullable=True)

    candidate = relationship("Candidate", back_populates="criterion_scores")


class CloudConnection(Base):
    __tablename__ = "cloud_connections"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, unique=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    account_email = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
