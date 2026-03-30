from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CloudFolder:
    id: str
    name: str
    path: str  # Human-readable breadcrumb path
    has_children: bool = True


@dataclass
class CloudFile:
    id: str
    name: str
    size: int
    mime_type: str


class CloudStorageProvider(ABC):
    provider_name: str  # e.g. "google_drive"
    display_name: str  # e.g. "Google Drive"

    @abstractmethod
    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Generate OAuth2 authorization URL."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange auth code for tokens. Returns {access_token, refresh_token, expires_at}."""
        ...

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh an expired access token."""
        ...

    @abstractmethod
    async def list_folders(self, access_token: str, parent_folder_id: str | None = None) -> list[CloudFolder]:
        """List child folders under a parent (None = root)."""
        ...

    @abstractmethod
    async def list_files(self, access_token: str, folder_id: str) -> list[CloudFile]:
        """List resume files (PDF, DOCX) in a folder."""
        ...

    @abstractmethod
    async def download_file(self, access_token: str, file_id: str, dest_path: Path) -> Path:
        """Download a file to a local path."""
        ...
