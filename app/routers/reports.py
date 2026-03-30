from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, require_user
from app.models import Candidate, RankingSession
from app.services.report_generator import ReportGenerator

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_user)])


async def _load_session(session_id: int, db: AsyncSession) -> RankingSession | None:
    stmt = (
        select(RankingSession)
        .options(
            selectinload(RankingSession.job_role),
            selectinload(RankingSession.candidates).selectinload(Candidate.criterion_scores),
        )
        .where(RankingSession.id == session_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.get("/{session_id}/pdf")
async def download_pdf(
    session_id: int,
    top_n: int = Query(default=15, ge=1, le=150),
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, db)
    if not session:
        return Response(status_code=404)

    generator = ReportGenerator()
    pdf_bytes = generator.render_pdf_report(session, top_n=top_n)
    filename = f"ranking-report-{session.job_role.title.replace(' ', '-')}-top{top_n}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/html")
async def download_html(
    session_id: int,
    top_n: int = Query(default=15, ge=1, le=150),
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, db)
    if not session:
        return Response(status_code=404)

    generator = ReportGenerator()
    html_content = generator.render_html_report(session, top_n=top_n)
    filename = f"ranking-report-{session.job_role.title.replace(' ', '-')}-top{top_n}.html"
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/docx")
async def download_docx(
    session_id: int,
    top_n: int = Query(default=15, ge=1, le=150),
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, db)
    if not session:
        return Response(status_code=404)

    generator = ReportGenerator()
    docx_bytes = generator.render_docx_report(session, top_n=top_n)
    filename = f"ranking-report-{session.job_role.title.replace(' ', '-')}-top{top_n}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
