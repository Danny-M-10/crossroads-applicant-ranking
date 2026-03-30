from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.cloud.base import CloudFile, CloudFolder, CloudStorageProvider

RESUME_MIME_TYPES = (
    "mimeType='application/pdf' or "
    "mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
)


class GoogleDriveProvider(CloudStorageProvider):
    provider_name = "google_drive"
    display_name = "Google Drive"

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE = "https://www.googleapis.com/drive/v3"
    SCOPES = "https://www.googleapis.com/auth/drive.readonly"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            data = resp.json()

            # Get user email
            email = None
            try:
                info = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                )
                email = info.json().get("email")
            except Exception:
                pass

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
                "email": email,
            }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
            }

    async def list_folders(self, access_token: str, parent_folder_id: str | None = None) -> list[CloudFolder]:
        parent = parent_folder_id or "root"
        query = f"'{parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_BASE}/files",
                params={"q": query, "fields": "files(id,name)", "orderBy": "name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return [
                CloudFolder(id=f["id"], name=f["name"], path=f["name"])
                for f in resp.json().get("files", [])
            ]

    async def list_files(self, access_token: str, folder_id: str) -> list[CloudFile]:
        query = f"'{folder_id}' in parents and trashed=false and ({RESUME_MIME_TYPES})"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_BASE}/files",
                params={"q": query, "fields": "files(id,name,size,mimeType)"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return [
                CloudFile(id=f["id"], name=f["name"], size=int(f.get("size", 0)), mime_type=f["mimeType"])
                for f in resp.json().get("files", [])
            ]

    async def download_file(self, access_token: str, file_id: str, dest_path: Path) -> Path:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.API_BASE}/files/{file_id}",
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {access_token}"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
            return dest_path
