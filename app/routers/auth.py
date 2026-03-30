import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from app.templates_shared import templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models import CloudConnection

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Combined scopes: user identity + Drive read access
GOOGLE_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
])

@router.get("/login")
async def login(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "google_configured": bool(settings.google_client_id)},
    )


@router.get("/login/google")
async def login_google(request: Request):
    if not settings.google_client_id:
        return RedirectResponse(url="/login", status_code=302)
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    redirect_uri = f"{settings.base_url}/auth/callback"
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/auth/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if request.session.pop("oauth_state", None) != state:
        return RedirectResponse(url="/login", status_code=302)

    redirect_uri = f"{settings.base_url}/auth/callback"
    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        token_data = resp.json()

        # Get user profile
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        info_resp.raise_for_status()
        user_info = info_resp.json()

    # Store login in session
    request.session["user_email"] = user_info.get("email", "")
    request.session["user_name"] = user_info.get("name", "")

    # Store Drive tokens so cloud browsing works immediately
    expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
    stmt = select(CloudConnection).where(CloudConnection.provider == "google_drive")
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.access_token = token_data["access_token"]
        if token_data.get("refresh_token"):
            existing.refresh_token = token_data["refresh_token"]
        existing.token_expires_at = expires_at
        existing.account_email = user_info.get("email")
    else:
        conn = CloudConnection(
            provider="google_drive",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            account_email=user_info.get("email"),
        )
        db.add(conn)
    await db.commit()

    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
