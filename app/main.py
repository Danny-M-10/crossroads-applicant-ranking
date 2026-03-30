import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.branding import FASTAPI_TITLE
from app.config import settings
from app.database import init_db
from app.routers import cloud, dashboard, jobs, rankings, reports
from app.routers.auth import router as auth_router
from app.routers.jobs import seed_default_roles
from app.database import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session_maker() as db:
        await seed_default_roles(db)
    yield


app = FastAPI(title=FASTAPI_TITLE, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    https_only=not settings.debug,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(rankings.router)
app.include_router(reports.router)
app.include_router(cloud.router)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.exception_handler(401)
async def auth_redirect(request: Request, exc):
    return RedirectResponse(url="/login", status_code=302)
