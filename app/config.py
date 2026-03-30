from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    gemini_api_key: str = ""
    resume_folder_path: Path = Path("./resumes")
    database_url: str = "sqlite+aiosqlite:///./data/ranker.db"
    gemini_model: str = "gemini-2.0-flash"
    max_concurrent_scores: int = 10
    app_secret_key: str = "change-me"
    debug: bool = False

    # Cloud Storage OAuth (optional — providers are disabled if credentials are empty)
    google_client_id: str = ""
    google_client_secret: str = ""
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
