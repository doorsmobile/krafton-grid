"""Krafton Grid DCIM — FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import AuthGateMiddleware
from app.config import (
    APP_HOST,
    APP_PORT,
    APP_VERSION,
    SESSION_HTTPS_ONLY,
    SESSION_SECRET,
    SITE_NAME,
)
from app.sim import engine
from app.web.deps import BASE_DIR
from app.web.routers import include_routers


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine.start()
    yield
    engine.stop()


app = FastAPI(title=f"{SITE_NAME} DCIM Simulation", version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
include_routers(app)

# Auth gate runs after SessionMiddleware (Starlette: last added = outermost)
app.add_middleware(AuthGateMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="kg_session",
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
    max_age=60 * 60 * 12,
)


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=False)


if __name__ == "__main__":
    run()
