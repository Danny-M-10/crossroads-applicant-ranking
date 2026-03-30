import html as html_module
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_shared import templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_user
from app.models import JobRole
from app.services.resume_parser import ResumeParser

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_user)])
_parser = ResumeParser()

# Example roles for coaching / consulting & client engagements (empty DB only)
DEFAULT_ROLES = [
    {
        "title": "Client Success Coordinator",
        "description": "Serves as the primary point of contact for coaching and consulting clients. Coordinates scheduling, prepares session materials, tracks follow-ups, and ensures a high-quality client experience.",
        "criteria": [
            {"name": "Client Service Experience", "weight": 30, "description": "Prior roles supporting executives, business owners, or professional services clients"},
            {"name": "Organization & Follow-through", "weight": 25, "description": "Reliable scheduling, documentation, and task management"},
            {"name": "Communication", "weight": 20, "description": "Clear, professional written and verbal communication"},
            {"name": "Discretion & Trust", "weight": 15, "description": "Handling confidential business and HR matters appropriately"},
            {"name": "Business Acumen", "weight": 10, "description": "Understanding of small-business operations and professional services"},
        ],
    },
    {
        "title": "Marketing Coordinator",
        "description": "Supports marketing delivery for the firm and its clients: content coordination, campaign execution, reporting, and collaboration with consultants on go-to-market initiatives.",
        "criteria": [
            {"name": "Marketing Execution", "weight": 30, "description": "Hands-on experience with campaigns, content, or digital marketing"},
            {"name": "Writing & Editing", "weight": 20, "description": "Strong business writing for emails, web, and client-facing copy"},
            {"name": "Tools & Analytics", "weight": 20, "description": "Familiarity with CRM, email tools, social platforms, or basic analytics"},
            {"name": "Project Collaboration", "weight": 15, "description": "Works effectively with consultants and external vendors"},
            {"name": "Brand Awareness", "weight": 15, "description": "Understanding of brand voice and consistent client-ready output"},
        ],
    },
    {
        "title": "Operations / Project Coordinator",
        "description": "Keeps internal projects and firm operations on track: process documentation, resource scheduling, light financial tracking, and supporting recruiting or HR-related workflows when needed.",
        "criteria": [
            {"name": "Process & Documentation", "weight": 25, "description": "Building checklists, SOPs, and repeatable workflows"},
            {"name": "Project Management", "weight": 25, "description": "Tracking milestones, dependencies, and stakeholder updates"},
            {"name": "Systems & Tools", "weight": 20, "description": "Comfort with spreadsheets, shared drives, and business software"},
            {"name": "Problem Solving", "weight": 15, "description": "Anticipating bottlenecks and proposing practical fixes"},
            {"name": "HR / Recruiting Exposure", "weight": 15, "description": "Experience supporting hiring, onboarding, or contractor coordination"},
        ],
    },
    {
        "title": "Analyst / Associate Consultant",
        "description": "Conducts research, summarizes findings, and prepares materials to support senior coaches and consultants. May assist with data gathering for recruiting and talent assessments.",
        "criteria": [
            {"name": "Research & Analysis", "weight": 30, "description": "Structured research, synthesis, and clear recommendations"},
            {"name": "Presentation Skills", "weight": 20, "description": "Slides, memos, and executive-ready summaries"},
            {"name": "Quantitative Comfort", "weight": 15, "description": "Working with metrics, benchmarks, or light modeling"},
            {"name": "Stakeholder Interaction", "weight": 20, "description": "Professional communication with clients and team members"},
            {"name": "Adaptability", "weight": 15, "description": "Comfort switching across industries and ambiguous assignments"},
        ],
    },
]


async def seed_default_roles(db: AsyncSession):
    """Seed default example job roles if none exist."""
    count = (await db.execute(select(JobRole.id).limit(1))).scalar()
    if count is not None:
        return

    for role_data in DEFAULT_ROLES:
        role = JobRole(**role_data)
        db.add(role)
    await db.commit()


@router.post("/parse-description-file")
async def parse_description_file(file: UploadFile = File(...)):
    """HTMX endpoint: parse uploaded file and return extracted text for the textarea."""
    if not file.filename:
        return HTMLResponse('<span class="text-red-600 text-sm">No file selected</span>')

    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".pdf", ".docx", ".txt"}
    if ext not in allowed:
        return HTMLResponse(
            f'<span class="text-red-600 text-sm">Unsupported file type: {ext}. Use PDF, DOCX, or TXT.</span>'
        )

    content = await file.read()

    if ext == ".txt":
        text = content.decode("utf-8", errors="replace").strip()
        error = None
    else:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            result = _parser.parse_file(tmp_path)
            text = result.text
            error = result.error
        finally:
            tmp_path.unlink(missing_ok=True)

    escaped_text = html_module.escape(text)
    escaped_name = html_module.escape(file.filename)

    if error:
        status = f'<span class="text-yellow-600 text-sm">Warning: {html_module.escape(error)}</span>'
    else:
        status = f'<span class="text-crossroads-accent text-sm">Extracted {len(text):,} characters from {escaped_name}</span>'

    return HTMLResponse(
        f'{status}'
        f'<template id="extracted-text">{escaped_text}</template>'
        f'<script>document.getElementById("description").value = '
        f'document.getElementById("extracted-text").content.textContent;</script>'
    )


@router.get("")
async def list_jobs(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = select(JobRole).order_by(JobRole.title)
    job_roles = (await db.execute(stmt)).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="jobs/list.html",
        context={"request": request, "job_roles": job_roles, "get_flashed_messages": lambda: []},
    )


@router.get("/new")
async def new_job_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="jobs/form.html",
        context={"request": request, "role": None, "get_flashed_messages": lambda: []},
    )


@router.post("")
async def create_job(
    request: Request,
    db: AsyncSession = Depends(get_db),
    title: str = Form(...),
    description: str = Form(...),
):
    form_data = await request.form()
    criteria = _parse_criteria_from_form(form_data)

    role = JobRole(title=title, description=description, criteria=criteria)
    db.add(role)
    await db.commit()
    return RedirectResponse(url="/jobs", status_code=303)


@router.get("/{role_id}/edit")
async def edit_job_form(
    request: Request, role_id: int, db: AsyncSession = Depends(get_db)
):
    role = await db.get(JobRole, role_id)
    if not role:
        return RedirectResponse(url="/jobs", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="jobs/form.html",
        context={"request": request, "role": role, "get_flashed_messages": lambda: []},
    )


@router.post("/{role_id}")
async def update_job(
    request: Request,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    title: str = Form(...),
    description: str = Form(...),
):
    role = await db.get(JobRole, role_id)
    if not role:
        return RedirectResponse(url="/jobs", status_code=303)

    form_data = await request.form()
    criteria = _parse_criteria_from_form(form_data)

    role.title = title
    role.description = description
    role.criteria = criteria
    await db.commit()
    return RedirectResponse(url="/jobs", status_code=303)


@router.delete("/{role_id}")
async def delete_job(role_id: int, db: AsyncSession = Depends(get_db)):
    role = await db.get(JobRole, role_id)
    if role:
        await db.delete(role)
        await db.commit()
    return HTMLResponse("")


def _parse_criteria_from_form(form_data) -> list[dict]:
    """Parse dynamic criteria rows from the form submission."""
    names = form_data.getlist("criteria_name")
    weights = form_data.getlist("criteria_weight")
    descriptions = form_data.getlist("criteria_description")

    criteria = []
    for i in range(len(names)):
        name = names[i].strip() if i < len(names) else ""
        if not name:
            continue
        weight = int(weights[i]) if i < len(weights) and weights[i] else 0
        desc = descriptions[i].strip() if i < len(descriptions) else ""
        criteria.append({"name": name, "weight": weight, "description": desc})
    return criteria
