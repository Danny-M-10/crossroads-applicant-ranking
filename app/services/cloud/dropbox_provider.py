import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.cloud.base import CloudFile, CloudFolder, CloudStorageProvider

RESUME_EXTENSIONS = {".pdf", ".docx"}


class DropboxProvider(CloudStorageProvider):
    provider_name = "dropbox"
    display_name = "Dropbox"

    AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
    TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
    API_BASE = "https://api.dropboxapi.com/2"
    CONTENT_BASE = "https://content.dropboxapi.com/2"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.dropbox_app_key,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "token_access_type": "offline",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": settings.dropbox_app_key,
                "client_secret": settings.dropbox_app_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            resp.raise_for_status()
            data = resp.json()

            # Get account email
            email = None
            try:
                info = await client.post(
                    f"{self.API_BASE}/users/get_current_account",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                )
                email = info.json().get("email")
            except Exception:
                pass

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 14400)),
                "email": email,
            }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "refresh_token": refresh_token,
                "client_id": settings.dropbox_app_key,
                "client_secret": settings.dropbox_app_secret,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 14400)),
            }

    async def list_folders(self, access_token: str, parent_folder_id: str | None = None) -> list[CloudFolder]:
        # Dropbox uses paths, not IDs. Root is ""
        path = parent_folder_id or ""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.API_BASE}/files/list_folder",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"path": path, "include_non_downloadable_files": False},
            )
            resp.raise_for_status()
            entries = resp.json().get("entries", [])
            return [
                CloudFolder(
                    id=e["path_lower"],
                    name=e["name"],
                    path=e["path_display"],
                )
                for e in entries
                if e[".tag"] == "folder"
            ]

    async def list_files(self, access_token: str, folder_id: str) -> list[CloudFile]:
        path = folder_id or ""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.API_BASE}/files/list_folder",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"path": path, "include_non_downloadable_files": False},
            )
            resp.raise_for_status()
            entries = resp.json().get("entries", [])
            files = []
            for e in entries:
                if e[".tag"] != "file":
                    continue
                ext = Path(e["name"]).suffix.lower()
                if ext in RESUME_EXTENSIONS:
                    files.append(CloudFile(
                        id=e["path_lower"],
                        name=e["name"],
                        size=e.get("size", 0),
                        mime_type="application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ))
            return files

    async def download_file(self, access_token: str, file_id: str, dest_path: Path) -> Path:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.CONTENT_BASE}/files/download",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Dropbox-API-Arg": json.dumps({"path": file_id}),
                },
            )
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
            return dest_path
