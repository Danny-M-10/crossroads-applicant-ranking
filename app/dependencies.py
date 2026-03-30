from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session_maker() as session:
        yield session


async def require_user(request: Request) -> str:
    email = request.session.get("user_email")
    if not email:
        raise HTTPException(status_code=401)
    return email
