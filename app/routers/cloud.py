import secrets

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_shared import templates
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.branding import template_globals
from app.config import settings
from app.dependencies import get_db, require_user
from app.models import CloudConnection
from app.services.cloud import get_available_providers, get_provider

router = APIRouter(prefix="/cloud", tags=["cloud"], dependencies=[Depends(require_user)])
_jinja_env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
_jinja_env.globals.update(template_globals())

@router.get("/connect/{provider_name}")
async def start_oauth(provider_name: str, request: Request):
    """Initiate OAuth flow — redirect to provider consent screen."""
    provider = get_provider(provider_name)
    if not provider:
        return RedirectResponse(url="/rankings/new", status_code=303)

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    redirect_uri = f"{settings.base_url}/cloud/callback/{provider_name}"
    auth_url = provider.get_auth_url(redirect_uri, state)
    return RedirectResponse(url=auth_url)


@router.get("/callback/{provider_name}")
async def oauth_callback(
    request: Request,
    provider_name: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback — exchange code for tokens and store."""
    if request.session.pop("oauth_state", None) != state:
        return RedirectResponse(url="/rankings/new?error=invalid_state", status_code=303)

    provider = get_provider(provider_name)
    if not provider:
        return RedirectResponse(url="/rankings/new", status_code=303)

    redirect_uri = f"{settings.base_url}/cloud/callback/{provider_name}"
    tokens = await provider.exchange_code(code, redirect_uri)

    # Upsert CloudConnection
    stmt = select(CloudConnection).where(CloudConnection.provider == provider_name)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.access_token = tokens["access_token"]
        existing.refresh_token = tokens.get("refresh_token", existing.refresh_token)
        existing.token_expires_at = tokens.get("expires_at")
        existing.account_email = tokens.get("email", existing.account_email)
    else:
        conn = CloudConnection(
            provider=provider_name,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            token_expires_at=tokens.get("expires_at"),
            account_email=tokens.get("email"),
        )
        db.add(conn)
    await db.commit()
    return RedirectResponse(url=f"/rankings/new?connected={provider_name}", status_code=303)


@router.delete("/disconnect/{provider_name}")
async def disconnect(provider_name: str, db: AsyncSession = Depends(get_db)):
    """Remove stored cloud connection."""
    stmt = select(CloudConnection).where(CloudConnection.provider == provider_name)
    conn = (await db.execute(stmt)).scalar_one_or_none()
    if conn:
        await db.delete(conn)
        await db.commit()
    return HTMLResponse("")


@router.get("/browse/{provider_name}")
async def browse_folders(
    provider_name: str,
    folder_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """HTMX endpoint: returns folder browser HTML fragment."""
    provider = get_provider(provider_name)
    if not provider:
        return HTMLResponse('<span class="text-red-600 text-sm">Provider not found</span>')

    conn = (await db.execute(
        select(CloudConnection).where(CloudConnection.provider == provider_name)
    )).scalar_one_or_none()
    if not conn:
        return HTMLResponse('<span class="text-red-600 text-sm">Not connected</span>')

    access_token = await _ensure_valid_token(conn, provider, db)

    try:
        folders = await provider.list_folders(access_token, folder_id)
        # Also get file count for current folder if one is selected
        files_count = None
        if folder_id:
            files = await provider.list_files(access_token, folder_id)
            files_count = len(files)
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-600 text-sm">Error: {e}</span>')

    template = _jinja_env.get_template("cloud/folder_browser.html")
    return HTMLResponse(template.render(
        provider_name=provider_name,
        folders=folders,
        parent_id=folder_id,
        files_count=files_count,
    ))


async def _ensure_valid_token(conn: CloudConnection, provider, db: AsyncSession) -> str:
    """Refresh token if expired, return valid access token."""
    import datetime
    if conn.token_expires_at and conn.token_expires_at < datetime.datetime.utcnow():
        if conn.refresh_token:
            tokens = await provider.refresh_access_token(conn.refresh_token)
            conn.access_token = tokens["access_token"]
            conn.token_expires_at = tokens.get("expires_at")
            if tokens.get("refresh_token"):
                conn.refresh_token = tokens["refresh_token"]
            await db.commit()
    return conn.access_token
