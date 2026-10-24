"""FastAPI application factory (SPECS.md §5, §6).

Wires: security headers (SR-6), CORS lock (SR-6), rate limiters (SR-3),
routers (admin, rooms, agent), the sweeper scheduler (FR-20) and the presence
idle-drop task (FR-18). Telemetry hooks land in the observability phase (§7).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import get_engine, init_engine
from .models import Base
from .ratelimit import RateLimiter
from .routers.admin import router as admin_router
from .routers.rooms import router as rooms_router
from .wshub import hub

_state_app: FastAPI | None = None


def app_state() -> FastAPI:
    """Accessor for the on-call agent (internal restarts)."""
    if _state_app is None:
        raise RuntimeError("app not created yet")
    return _state_app


async def _presence_sweeper_loop():
    """FR-18: drop members idle >5 min from presence; notify their rooms."""
    while True:
        await asyncio.sleep(30)
        try:
            dropped = await hub.drop_idle()
            for room_id, member in dropped:
                await hub.broadcast(room_id, {"type": "member_left", "member_id": member.member_id})
                present = [
                    {"member_id": m.member_id, "name": m.name, "color": m.color}
                    for m in await hub.members_of(room_id)
                ]
                await hub.broadcast(room_id, {"type": "presence", "members": present})
        except Exception:  # noqa: BLE001 — background loop must never die
            pass


def create_app() -> FastAPI:
    global _state_app
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, _ = init_engine(settings.db_path)
        Base.metadata.create_all(engine)

        # SR-3 rate limiters (clock injectable in tests via monkeypatch)
        app.state.login_limiter = RateLimiter(
            settings.rate_limit_login_per_15min, 15 * 60
        )
        app.state.create_limiter = RateLimiter(settings.rate_limit_create_per_hour, 3600)
        app.state.upload_limiter = RateLimiter(settings.rate_limit_upload_per_hour, 3600)
        app.state.delete_limiter = RateLimiter(settings.rate_limit_delete_per_hour, 3600)
        app.state.ws_conn_counts = {}

        from .sweeper import start_scheduler

        scheduler = start_scheduler(settings)
        idle_task = asyncio.create_task(_presence_sweeper_loop())
        yield
        idle_task.cancel()
        scheduler.shutdown(wait=False)

    app = FastAPI(title="ClipRoom API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.base_url, "http://localhost:8080", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "ok", "db": "ok"}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "degraded", "db": "error"})

    app.include_router(admin_router)
    app.include_router(rooms_router)

    from .agent import router as agent_router

    app.include_router(agent_router)

    _state_app = app
    return app
