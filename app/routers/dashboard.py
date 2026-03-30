from fastapi import APIRouter, Depends, Request
from app.templates_shared import templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_user
from app.models import Candidate, JobRole, RankingSession

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    # Stats
    job_role_count = (await db.execute(select(func.count(JobRole.id)))).scalar() or 0
    session_count = (await db.execute(select(func.count(RankingSession.id)))).scalar() or 0
    total_candidates = (
        await db.execute(
            select(func.sum(RankingSession.total_candidates))
        )
    ).scalar() or 0

    # Recent sessions with job role eagerly loaded
    from sqlalchemy.orm import selectinload

    stmt = (
        select(RankingSession)
        .options(selectinload(RankingSession.job_role))
        .order_by(RankingSession.created_at.desc())
        .limit(5)
    )
    recent_sessions = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "job_role_count": job_role_count,
            "session_count": session_count,
            "total_candidates": total_candidates,
            "recent_sessions": recent_sessions,
            "get_flashed_messages": lambda: [],
        },
    )
