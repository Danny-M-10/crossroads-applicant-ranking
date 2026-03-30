from app.services.cloud.base import CloudFile, CloudFolder, CloudStorageProvider

_PROVIDERS: dict[str, CloudStorageProvider] = {}
_initialized = False


def _init_providers():
    global _initialized
    if _initialized:
        return
    _initialized = True

    from app.config import settings

    if settings.google_client_id and settings.google_client_secret:
        from app.services.cloud.google_drive import GoogleDriveProvider
        _PROVIDERS["google_drive"] = GoogleDriveProvider()

    if settings.dropbox_app_key and settings.dropbox_app_secret:
        from app.services.cloud.dropbox_provider import DropboxProvider
        _PROVIDERS["dropbox"] = DropboxProvider()

    if settings.microsoft_client_id and settings.microsoft_client_secret:
        from app.services.cloud.onedrive import OneDriveProvider
        _PROVIDERS["onedrive"] = OneDriveProvider()


def get_provider(name: str) -> CloudStorageProvider | None:
    _init_providers()
    return _PROVIDERS.get(name)


def get_available_providers() -> list[CloudStorageProvider]:
    _init_providers()
    return list(_PROVIDERS.values())
