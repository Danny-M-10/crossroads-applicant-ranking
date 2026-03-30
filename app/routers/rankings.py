import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from app.templates_shared import templates
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.branding import ORG_CONTEXT_FOR_AI
from app.config import settings
from app.dependencies import get_db, require_user
from app.models import Candidate, CloudConnection, CriterionScore, JobRole, RankingSession, SessionStatus
from app.services.cloud import get_available_providers, get_provider
from app.services.ranker import RankingService
from app.services.resume_parser import ResumeParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rankings", tags=["rankings"], dependencies=[Depends(require_user)])
ranking_service = RankingService()
parser = ResumeParser()


@router.get("")
async def list_rankings(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(RankingSession)
        .options(selectinload(RankingSession.job_role))
        .order_by(RankingSession.created_at.desc())
    )
    sessions = (await db.execute(stmt)).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="rankings/list.html",
        context={"request": request, "sessions": sessions, "get_flashed_messages": lambda: []},
    )


@router.get("/new")
async def new_ranking_form(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(JobRole).order_by(JobRole.title)
    job_roles = (await db.execute(stmt)).scalars().all()

    # Load cloud providers and connections
    available_providers = get_available_providers()
    connections = {}
    if available_providers:
        stmt2 = select(CloudConnection)
        result = await db.execute(stmt2)
        for conn in result.scalars().all():
            connections[conn.provider] = conn

    return templates.TemplateResponse(
        request=request,
        name="rankings/new.html",
        context={
            "request": request,
            "job_roles": job_roles,
            "default_folder": str(settings.resume_folder_path),
            "cloud_providers": available_providers,
            "cloud_connections": connections,
            "get_flashed_messages": lambda: [],
        },
    )


@router.post("/validate-folder")
async def validate_folder(request: Request, folder_path: str = Form(...)):
    """HTMX endpoint: validate folder and show resume count."""
    path = Path(folder_path)
    if not path.is_dir():
        return HTMLResponse(
            '<span class="text-red-600">Folder not found</span>'
        )
    try:
        files = parser.discover_files(path)
        pdf_count = sum(1 for f in files if f.suffix.lower() == ".pdf")
        docx_count = sum(1 for f in files if f.suffix.lower() == ".docx")
        return HTMLResponse(
            f'<span class="text-crossroads-accent">Found {len(files)} resumes ({pdf_count} PDF, {docx_count} DOCX)</span>'
        )
    except Exception as e:
        return HTMLResponse(
            f'<span class="text-red-600">Error: {e}</span>'
        )


@router.post("/validate-uploads")
async def validate_uploads(files: list[UploadFile] = File(...)):
    """HTMX endpoint: validate uploaded resume files and show count."""
    allowed = {".pdf", ".docx", ".txt"}
    valid = []
    invalid = []
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in allowed:
            valid.append(f.filename)
        else:
            invalid.append(f.filename)

    parts = []
    if valid:
        parts.append(f'<span class="text-crossroads-accent">{len(valid)} valid resume(s) selected</span>')
    if invalid:
        names = ", ".join(invalid)
        parts.append(f'<span class="text-yellow-600">Skipped unsupported: {names}</span>')
    if not valid and not invalid:
        parts.append('<span class="text-red-600">No files selected</span>')

    return HTMLResponse("<br>".join(parts))


@router.post("")
async def create_ranking(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    job_role_id: int = Form(...),
    folder_path: str = Form(""),
    cloud_provider: str = Form(""),
    cloud_folder_id: str = Form(""),
    cloud_folder_name: str = Form(""),
    resume_files: list[UploadFile] | None = File(default=None),
):
    folder_path_override = None

    # Check for uploaded files first
    allowed_exts = {".pdf", ".docx", ".txt"}
    uploaded = [
        f for f in (resume_files or [])
        if f.filename and os.path.splitext(f.filename)[1].lower() in allowed_exts and f.size
    ]

    if uploaded:
        # Save uploaded files to a temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="upload_"))
        for uf in uploaded:
            dest = temp_dir / uf.filename
            content = await uf.read()
            dest.write_bytes(content)
        folder_path_override = str(temp_dir)
        folder_path = f"upload://{len(uploaded)} files"
    elif cloud_provider and cloud_folder_id:
        # Download cloud files to a temp directory
        try:
            temp_dir = await _download_cloud_folder(db, cloud_provider, cloud_folder_id)
            folder_path_override = str(temp_dir)
            folder_path = f"cloud://{cloud_provider}/{cloud_folder_name or cloud_folder_id}"
        except Exception as e:
            logger.exception("Failed to download cloud folder")
            return HTMLResponse(
                f'<div class="text-red-600">Cloud download failed: {e}</div>',
                status_code=400,
            )
    elif not folder_path:
        return HTMLResponse(
            '<div class="text-red-600">Please provide a local folder, upload files, or select a cloud folder.</div>',
            status_code=400,
        )

    # Create the session
    session = RankingSession(
        job_role_id=job_role_id,
        folder_path=folder_path,
        status=SessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Launch ranking as a FastAPI background task (keeps request alive on Cloud Run)
    background_tasks.add_task(
        ranking_service.run_ranking_session, session.id, folder_path_override=folder_path_override
    )

    return RedirectResponse(url=f"/rankings/{session.id}/live", status_code=303)


async def _download_cloud_folder(db: AsyncSession, provider_name: str, folder_id: str) -> Path:
    """Download all resume files from a cloud folder to a temp directory."""
    provider = get_provider(provider_name)
    if not provider:
        raise ValueError(f"Unknown cloud provider: {provider_name}")

    # Load connection
    stmt = select(CloudConnection).where(CloudConnection.provider == provider_name)
    result = await db.execute(stmt)
    connection = result.scalar_one_or_none()
    if not connection:
        raise ValueError(f"No {provider_name} connection found. Please connect first.")

    # Refresh token if expired
    from datetime import datetime
    if connection.token_expires_at and connection.token_expires_at < datetime.utcnow():
        if not connection.refresh_token:
            raise ValueError(f"{provider_name} token expired and no refresh token available.")
        new_tokens = await provider.refresh_access_token(connection.refresh_token)
        connection.access_token = new_tokens["access_token"]
        connection.token_expires_at = new_tokens.get("expires_at")
        await db.commit()

    # List files in the folder
    files = await provider.list_files(connection.access_token, folder_id)
    if not files:
        raise ValueError("No resume files (PDF/DOCX) found in the selected folder.")

    # Download to temp dir
    temp_dir = Path(tempfile.mkdtemp(prefix="cloud_"))
    for cloud_file in files:
        dest = temp_dir / cloud_file.name
        await provider.download_file(connection.access_token, cloud_file.id, dest)

    return temp_dir


@router.get("/{session_id}/live")
async def ranking_progress_page(
    request: Request, session_id: int, db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(RankingSession)
        .options(selectinload(RankingSession.job_role))
        .where(RankingSession.id == session_id)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return RedirectResponse(url="/rankings", status_code=303)

    # If already completed, redirect to results
    if session.status == SessionStatus.COMPLETED:
        return RedirectResponse(url=f"/rankings/{session_id}", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="rankings/progress.html",
        context={
            "request": request,
            "session": session,
            "scored": session.scored_candidates or 0,
            "total": session.total_candidates or 1,
            "status": session.status.value,
            "session_id": session_id,
            "error_log": session.error_log,
            "get_flashed_messages": lambda: [],
        },
    )


@router.get("/{session_id}/progress")
async def ranking_progress_partial(
    session_id: int, db: AsyncSession = Depends(get_db)
):
    """HTMX endpoint: returns progress bar fragment."""
    stmt = select(RankingSession).where(RankingSession.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return HTMLResponse("")

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
    template = env.get_template("partials/_progress_bar.html")
    html = template.render(
        scored=session.scored_candidates or 0,
        total=session.total_candidates or 1,
        status=session.status.value,
        session_id=session_id,
        error_log=session.error_log,
    )
    return HTMLResponse(html)


@router.get("/{session_id}")
async def ranking_results(
    request: Request, session_id: int, db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(RankingSession)
        .options(
            selectinload(RankingSession.job_role),
            selectinload(RankingSession.candidates).selectinload(Candidate.criterion_scores),
        )
        .where(RankingSession.id == session_id)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return RedirectResponse(url="/rankings", status_code=303)

    # If still running, redirect to progress page
    if session.status in (SessionStatus.PENDING, SessionStatus.RUNNING):
        return RedirectResponse(url=f"/rankings/{session_id}/live", status_code=303)

    # Split candidates into scored and errored
    scored = sorted(
        [c for c in session.candidates if c.weighted_total is not None],
        key=lambda c: c.weighted_total,
        reverse=True,
    )
    errored = [c for c in session.candidates if c.scoring_error and c.weighted_total is None]

    return templates.TemplateResponse(
        request=request,
        name="rankings/results.html",
        context={
            "request": request,
            "session": session,
            "candidates": scored,
            "error_candidates": errored,
            "criteria": session.job_role.criteria,
            "get_flashed_messages": lambda: [],
        },
    )


def _build_chat_system_prompt(session) -> str:
    """Build a rich system prompt giving Gemini full context of the ranking."""
    job = session.job_role
    scored = sorted(
        [c for c in session.candidates if c.weighted_total is not None],
        key=lambda c: c.weighted_total,
        reverse=True,
    )

    criteria_list = "\n".join(
        f"- {c['name']} ({c['weight']}%): {c.get('description', '')}"
        for c in (job.criteria or [])
    )

    candidate_blocks = []
    for i, c in enumerate(scored[:30], 1):
        score_lines = "\n".join(
            f"    • {cs.criterion_name}: {cs.score}/10 — {cs.justification or 'No justification'}"
            for cs in sorted(c.criterion_scores, key=lambda x: x.criterion_name)
        )
        red_flags = ""
        if c.raw_scores and c.raw_scores.get("red_flags"):
            red_flags = "\n  Concerns: " + "; ".join(c.raw_scores["red_flags"])
        candidate_blocks.append(
            f"#{i}. {c.candidate_name or 'Unknown'} — Score: {c.weighted_total:.1f}/100\n"
            f"  File: {c.filename}\n"
            f"  Summary: {c.ai_summary or 'N/A'}\n"
            f"  Criterion Scores:\n{score_lines}"
            f"{red_flags}"
        )

    return f"""You are a helpful HR assistant for {ORG_CONTEXT_FOR_AI} You are analyzing applicant ranking results and helping the hiring manager or consultant make informed decisions.

You have complete access to the ranking data below. Answer questions about candidates, their scores, strengths, weaknesses, and comparisons. Be concise and specific — always reference candidate names and actual scores.

== JOB ROLE ==
Title: {job.title}
Description: {job.description or 'N/A'}

== SCORING CRITERIA ==
{criteria_list}

== RANKED CANDIDATES ({len(scored)} scored) ==
{chr(10).join(candidate_blocks) if candidate_blocks else 'No scored candidates.'}

When asked to recommend or compare, be direct and cite specific scores and evidence from the data above."""


@router.post("/{session_id}/chat")
async def chat_about_ranking(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Context-aware chatbot endpoint for asking questions about a ranking."""
    body = await request.json()
    user_message = body.get("message", "").strip()
    history = body.get("history", [])  # list of {"role": "user"|"model", "text": "..."}

    if not user_message:
        return JSONResponse({"response": "Please type a question."})

    # Load full session with candidates and scores
    stmt = (
        select(RankingSession)
        .options(
            selectinload(RankingSession.job_role),
            selectinload(RankingSession.candidates).selectinload(Candidate.criterion_scores),
        )
        .where(RankingSession.id == session_id)
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return JSONResponse({"response": "Ranking session not found."}, status_code=404)

    system_prompt = _build_chat_system_prompt(session)

    # Build conversation history for Gemini (last 10 turns to stay within limits)
    contents = []
    for msg in history[-10:]:
        role = msg.get("role", "user")
        contents.append({"role": role, "parts": [{"text": msg.get("text", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1024,
                temperature=0.7,
            ),
        )
        answer = response.text.strip()
    except Exception as e:
        logger.exception("Chat Gemini call failed")
        answer = f"Sorry, I ran into an error: {e}"

    return JSONResponse({"response": answer})


@router.delete("/{session_id}")
async def delete_ranking(session_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a ranking session and all its associated candidates and scores."""
    stmt = select(RankingSession).where(RankingSession.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        return HTMLResponse("", status_code=404)

    # Delete criterion scores → candidates → session (no DB cascade configured)
    cand_stmt = select(Candidate).where(Candidate.ranking_session_id == session_id)
    candidates = (await db.execute(cand_stmt)).scalars().all()
    for candidate in candidates:
        score_stmt = select(CriterionScore).where(CriterionScore.candidate_id == candidate.id)
        scores = (await db.execute(score_stmt)).scalars().all()
        for score in scores:
            await db.delete(score)
        await db.delete(candidate)

    await db.delete(session)
    await db.commit()

    # HTMX: redirect to rankings list after delete
    return HTMLResponse(
        "", status_code=200,
        headers={"HX-Redirect": "/rankings"}
    )
