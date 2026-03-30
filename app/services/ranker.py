import asyncio
import datetime
import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session_maker
from app.models import Candidate, CriterionScore, JobRole, RankingSession, SessionStatus
from app.services.resume_parser import ResumeParser
from app.services.scorer import compute_weighted_total, score_candidate_sync, validate_scores

logger = logging.getLogger(__name__)


class RankingService:
    def __init__(self):
        self.parser = ResumeParser()

    async def run_ranking_session(self, session_id: int, folder_path_override: str | None = None):
        """Main orchestration method. Runs the full pipeline using its own DB sessions."""
        async with async_session_maker() as db:
            # Load the ranking session and job role
            stmt = (
                select(RankingSession)
                .options(selectinload(RankingSession.job_role))
                .where(RankingSession.id == session_id)
            )
            result = await db.execute(stmt)
            ranking_session = result.scalar_one()
            job_role = ranking_session.job_role

            # Update status to RUNNING
            ranking_session.status = SessionStatus.RUNNING
            await db.commit()

        try:
            # Parse all resumes in a thread pool (sync I/O)
            folder_path = Path(folder_path_override or ranking_session.folder_path)
            parsed_resumes = await asyncio.to_thread(self.parser.parse_folder, folder_path)

            # Create Candidate records
            async with async_session_maker() as db:
                candidate_ids = []
                for parsed in parsed_resumes:
                    candidate = Candidate(
                        ranking_session_id=session_id,
                        filename=parsed.filename,
                        resume_text=(parsed.text or "(empty)").replace('\x00', ''),
                        scoring_error=parsed.error,
                    )
                    db.add(candidate)
                    await db.flush()
                    candidate_ids.append((candidate.id, parsed))

                # Update total count
                stmt = select(RankingSession).where(RankingSession.id == session_id)
                result = await db.execute(stmt)
                rs = result.scalar_one()
                rs.total_candidates = len(candidate_ids)
                await db.commit()

            # Score candidates with concurrency control
            semaphore = asyncio.Semaphore(settings.max_concurrent_scores)
            tasks = []
            for cand_id, parsed in candidate_ids:
                if parsed.error:
                    # Increment scored count for skipped candidates
                    async with async_session_maker() as db:
                        stmt = select(RankingSession).where(RankingSession.id == session_id)
                        result = await db.execute(stmt)
                        rs = result.scalar_one()
                        rs.scored_candidates = (rs.scored_candidates or 0) + 1
                        await db.commit()
                    continue
                tasks.append(
                    self._score_single_candidate(
                        semaphore, cand_id, job_role.title, job_role.description,
                        job_role.criteria, parsed.text, session_id,
                    )
                )

            await asyncio.gather(*tasks)

            # Compute ranks
            async with async_session_maker() as db:
                stmt = (
                    select(Candidate)
                    .where(Candidate.ranking_session_id == session_id)
                    .where(Candidate.weighted_total.isnot(None))
                    .order_by(Candidate.weighted_total.desc())
                )
                result = await db.execute(stmt)
                ranked = result.scalars().all()
                for rank_num, candidate in enumerate(ranked, start=1):
                    candidate.rank = rank_num

                # Finalize session
                stmt2 = select(RankingSession).where(RankingSession.id == session_id)
                result2 = await db.execute(stmt2)
                rs = result2.scalar_one()
                rs.status = SessionStatus.COMPLETED
                rs.completed_at = datetime.datetime.utcnow()
                await db.commit()

        except Exception as e:
            logger.exception("Ranking session %d failed", session_id)
            async with async_session_maker() as db:
                stmt = select(RankingSession).where(RankingSession.id == session_id)
                result = await db.execute(stmt)
                rs = result.scalar_one()
                rs.status = SessionStatus.FAILED
                rs.error_log = str(e)
                await db.commit()

        finally:
            # Clean up temp directories from cloud downloads
            if folder_path_override:
                override_path = Path(folder_path_override)
                if override_path.exists() and str(override_path).startswith(tempfile.gettempdir()):
                    try:
                        shutil.rmtree(override_path)
                        logger.info("Cleaned up temp cloud folder: %s", override_path)
                    except OSError:
                        logger.warning("Failed to clean up temp folder: %s", override_path, exc_info=True)

    async def _score_single_candidate(
        self,
        semaphore: asyncio.Semaphore,
        candidate_id: int,
        job_title: str,
        job_description: str,
        criteria: list[dict],
        resume_text: str,
        session_id: int,
    ):
        """Score one candidate with semaphore-controlled concurrency."""
        async with semaphore:
            try:
                scores_data = await asyncio.to_thread(
                    score_candidate_sync,
                    job_title, job_description, criteria, resume_text,
                )

                warnings = validate_scores(scores_data, criteria)

                async with async_session_maker() as db:
                    stmt = select(Candidate).where(Candidate.id == candidate_id)
                    result = await db.execute(stmt)
                    candidate = result.scalar_one()

                    if warnings:
                        candidate.scoring_error = "; ".join(warnings)

                    # Persist criterion scores
                    criteria_weights = {c["name"]: c["weight"] for c in criteria}
                    for cs in scores_data.get("scores", []):
                        weight = criteria_weights.get(cs["criterion_name"], 0)
                        criterion_score = CriterionScore(
                            candidate_id=candidate_id,
                            criterion_name=cs["criterion_name"],
                            score=cs["score"],
                            weight=weight,
                            weighted_score=cs["score"] * (weight / 100) * 10,
                            justification=cs.get("justification", ""),
                        )
                        db.add(criterion_score)

                    candidate.candidate_name = scores_data.get("candidate_name", "Unknown")
                    candidate.weighted_total = compute_weighted_total(scores_data, criteria)
                    candidate.ai_summary = scores_data.get("summary", "")
                    candidate.raw_scores = scores_data
                    await db.commit()

            except Exception as e:
                logger.exception("Failed to score candidate %d", candidate_id)
                async with async_session_maker() as db:
                    stmt = select(Candidate).where(Candidate.id == candidate_id)
                    result = await db.execute(stmt)
                    candidate = result.scalar_one()
                    candidate.scoring_error = f"API error: {e}"
                    await db.commit()

            finally:
                async with async_session_maker() as db:
                    stmt = select(RankingSession).where(RankingSession.id == session_id)
                    result = await db.execute(stmt)
                    rs = result.scalar_one()
                    rs.scored_candidates = (rs.scored_candidates or 0) + 1
                    await db.commit()
