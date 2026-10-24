"""Shared FastAPI dependencies: DB session, operator sessions, member auth,
capability-404 room lookup (FR-2)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .db import session_factory
from .models import Member, Room, utcnow
from .security import sessions

SESSION_COOKIE = "cliproom_session"


def get_db():
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    # single-container deploy: no proxy chain expected; use direct client IP
    return request.client.host if request.client else "unknown"


def get_session_or_401(request: Request) -> dict:
    sid = request.cookies.get(SESSION_COOKIE)
    session = sessions.get(sid) if sid else None
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    request.state.session_id = sid
    return session


def require_csrf_header(request: Request, x_requested_with: str | None = Header(default=None)) -> None:
    """SR-7: mutating authenticated operator calls must carry a custom header."""
    if x_requested_with != "fetch":
        raise HTTPException(status_code=403, detail="Forbidden")


def require_admin(session: dict = Depends(get_session_or_401)) -> dict:
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return session


def set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=12 * 3600,
        path="/",
    )


def get_room_or_404(room_id: str, db: Session) -> Room:
    """FR-2: unknown/expired/deleted room → generic 404, never 403.
    Forever rooms (expires_at NULL) never expire."""
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if room.expires_at is not None and room.expires_at <= utcnow():
        raise HTTPException(status_code=404, detail="Not Found")
    return room


def require_member(
    room: Room,
    x_member_token: str | None,
    db: Session,
) -> Member:
    """Resolve the X-Member-Token to a Member of this room (403 on failure)."""
    from .security import hash_member_token

    if not x_member_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    member = db.query(Member).filter(Member.token_hash == hash_member_token(x_member_token)).first()
    if member is None or member.room_id != room.room_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return member
