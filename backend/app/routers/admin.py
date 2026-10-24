"""Operator routes: admin/guest login & logout (FR-4), dashboard (FR-5),
guest constraints (FR-7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import (
    client_ip,
    get_db,
    get_session_or_401,
    require_admin,
    require_csrf_header,
    set_session_cookie,
)
from ..models import Item, Room, iso_utc, utcnow
from ..rooms import room_disk_usage, terminate_room
from ..security import sessions, verify_password

router = APIRouter(prefix="/api/admin")


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()

    limiter = request.app.state.login_limiter
    if not limiter.hit("login", client_ip(request)):
        return JSONResponse(status_code=429, content={"detail": "Too many login attempts"})

    role = _resolve_role(settings, body.username, body.password)
    if role is None:
        # generic error — no username enumeration (FR-4)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    sid = sessions.create(body.username, role)
    set_session_cookie(response, sid)
    return {"role": role}


def _resolve_role(settings, username: str, password: str) -> str | None:
    """Constant-time role resolution; indistinguishable for wrong user/pass."""
    import hmac

    admin_user_ok = hmac.compare_digest(username, settings.admin_username)
    admin_pass_ok = verify_password(password, settings.admin_password_hash) if settings.admin_password_hash else False
    guest_user_ok = (
        hmac.compare_digest(username, settings.guest_username) if settings.guest_enabled else False
    )
    guest_pass_ok = (
        verify_password(password, settings.guest_password_hash)
        if settings.guest_enabled and settings.guest_password_hash
        else False
    )
    if admin_user_ok and admin_pass_ok:
        return "admin"
    if guest_user_ok and guest_pass_ok:
        return "guest"
    return None


@router.post("/logout", dependencies=[Depends(get_session_or_401), Depends(require_csrf_header)])
def logout(request: Request):
    sessions.destroy(request.state.session_id)
    response = JSONResponse({"ok": True})
    response.delete_cookie("cliproom_session", path="/")
    return response


@router.get("/rooms", dependencies=[Depends(require_admin)])
def list_rooms(db: Session = Depends(get_db)):
    rooms = (
        db.query(Room)
        .filter(or_(Room.expires_at.is_(None), Room.expires_at > utcnow()))
        .order_by(Room.created_at.desc())
        .all()
    )
    out = []
    for r in rooms:
        item_count = db.query(Item).filter(Item.room_id == r.room_id).count()
        out.append(
            {
                "room_uuid": r.room_uuid,
                "item_count": item_count,
                "disk_usage": room_disk_usage(db, r.room_id),
                "expires_at": iso_utc(r.expires_at),
                "created_by": r.created_by,
            }
        )
    return out


@router.delete(
    "/rooms/{room_uuid}",
    dependencies=[Depends(require_admin), Depends(require_csrf_header)],
)
def force_terminate(room_uuid: str, db: Session = Depends(get_db)):
    settings = get_settings()
    room = db.query(Room).filter(Room.room_uuid == room_uuid).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Not Found")
    terminate_room(db, settings, room)
    return {"ok": True}
