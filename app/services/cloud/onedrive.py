from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.cloud.base import CloudFile, CloudFolder, CloudStorageProvider

RESUME_EXTENSIONS = {".pdf", ".docx"}


class OneDriveProvider(CloudStorageProvider):
    provider_name = "onedrive"
    display_name = "OneDrive"

    AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    SCOPES = "Files.Read.All offline_access User.Read"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.microsoft_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPES,
            "state": state,
            "response_mode": "query",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "code": code,
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": self.SCOPES,
            })
            resp.raise_for_status()
            data = resp.json()

            # Get user email
            email = None
            try:
                info = await client.get(
                    f"{self.GRAPH_BASE}/me",
                    headers={"Authorization": f"Bearer {data['access_token']}"},
                )
                email = info.json().get("mail") or info.json().get("userPrincipalName")
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
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "grant_type": "refresh_token",
                "scope": self.SCOPES,
            })
            resp.raise_for_status()
            data = resp.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
            }

    async def list_folders(self, access_token: str, parent_folder_id: str | None = None) -> list[CloudFolder]:
        if parent_folder_id:
            url = f"{self.GRAPH_BASE}/me/drive/items/{parent_folder_id}/children"
        else:
            url = f"{self.GRAPH_BASE}/me/drive/root/children"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                params={"$filter": "folder ne null", "$select": "id,name,folder", "$orderby": "name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return [
                CloudFolder(id=item["id"], name=item["name"], path=item["name"])
                for item in resp.json().get("value", [])
                if "folder" in item
            ]

    async def list_files(self, access_token: str, folder_id: str) -> list[CloudFile]:
        url = f"{self.GRAPH_BASE}/me/drive/items/{folder_id}/children"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                params={"$select": "id,name,size,file", "$orderby": "name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            files = []
            for item in resp.json().get("value", []):
                if "file" not in item:
                    continue
                ext = Path(item["name"]).suffix.lower()
                if ext in RESUME_EXTENSIONS:
                    files.append(CloudFile(
                        id=item["id"],
                        name=item["name"],
                        size=item.get("size", 0),
                        mime_type=item.get("file", {}).get("mimeType", ""),
                    ))
            return files

    async def download_file(self, access_token: str, file_id: str, dest_path: Path) -> Path:
        url = f"{self.GRAPH_BASE}/me/drive/items/{file_id}/content"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                follow_redirects=True,
            )
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
            return dest_path
