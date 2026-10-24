"""Member + room routes (FR-1, FR-2, FR-8…FR-17) and the room WebSocket.

Error semantics (docs/api.md): unknown/expired room → generic 404; wrong or
missing member token on a known room → 403; upload too large → 413;
disallowed type → 415; validation → 422; rate limit → 429.
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..colors import color_for
from ..config import get_settings
from ..db import session_factory
from ..deps import (
    client_ip,
    get_db,
    get_room_or_404,
    get_session_or_401,
    require_csrf_header,
    require_member,
)
from ..ids import new_uuid
from ..models import Item, Member, Room, iso_utc
from ..rooms import (
    effective_max_file_mb,
    parse_ttl,
    create_room as create_room_row,
    get_active_room,
    guest_active_room,
    room_dir,
    terminate_room,
    touch_room,
)
from ..serializers import item_public, items_public, member_public
from ..security import hash_member_token
from ..wshub import ConnectedMember, hub
from ..wstickets import tickets

router = APIRouter(prefix="/api")

UPLOAD_CHUNK = 1024 * 1024
MAX_TEXT_CHARS = 10_000


async def _presence(room_id: str) -> list[dict]:
    return [
        {"member_id": m.member_id, "name": m.name, "color": m.color}
        for m in await hub.members_of(room_id)
    ]


# --- operator room management ---------------------------------------------------

class CreateRoomBody(BaseModel):
    ttl: str
    max_file_mb: int | None = None

    @field_validator("ttl")
    @classmethod
    def ttl_valid(cls, v: str) -> str:
        try:
            parse_ttl(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        return v

    @field_validator("max_file_mb")
    @classmethod
    def cap_valid(cls, v: int | None) -> int | None:
        if v is None:
            return v
        from ..config import get_settings

        global_cap = get_settings().max_file_mb
        if not (1 <= v <= global_cap):
            raise ValueError(f"max_file_mb must be 1–{global_cap} (the global cap)")
        return v


@router.post("/rooms", dependencies=[Depends(require_csrf_header)])
def create_room_route(
    body: CreateRoomBody,
    request: Request,
    session: dict = Depends(get_session_or_401),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not request.app.state.create_limiter.hit("create_room", client_ip(request)):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    if session["role"] == "guest" and guest_active_room(db) is not None:
        return JSONResponse(
            status_code=409,
            content={"detail": "Guest already has an active room — delete it first"},
        )
    room = create_room_row(
        db, created_by=session["role"], ttl_label=body.ttl, max_file_mb=body.max_file_mb
    )
    return {
        "room_id": room.room_id,
        "share_url": f"{settings.base_url}/r/{room.room_id}",
        "expires_at": iso_utc(room.expires_at),  # null for forever rooms
    }


@router.delete("/rooms/{room_uuid}", dependencies=[Depends(require_csrf_header)])
def delete_room_route(
    room_uuid: str,
    request: Request,
    session: dict = Depends(get_session_or_401),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.room_uuid == room_uuid).first()
    if room is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if session["role"] != "admin" and not (
        session["role"] == "guest" and room.created_by == "guest"
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    terminate_room(db, get_settings(), room)
    return {"ok": True}


# --- room meta & join --------------------------------------------------------------

@router.get("/rooms/{room_id}")
def room_meta(room_id: str, db: Session = Depends(get_db)):
    room = get_room_or_404(room_id, db)
    return {
        "expires_at": iso_utc(room.expires_at),
        "item_count": db.query(Item).filter(Item.room_id == room.room_id).count(),
    }


class JoinBody(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 20):
            raise ValueError("name must be 1-20 characters (trimmed)")
        return v


@router.post("/rooms/{room_id}/join")
def join_room(
    room_id: str,
    body: JoinBody,
    x_member_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    room = get_room_or_404(room_id, db)
    if not x_member_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    token_hash = hash_member_token(x_member_token)
    existing = db.query(Member).filter(Member.token_hash == token_hash).first()
    if existing is not None:
        if existing.room_id != room.room_id:
            # tokens are per-room by contract (FR-9); cross-room reuse → reject
            raise HTTPException(status_code=403, detail="Forbidden")
        return member_public(existing)  # returning member keeps name + color (FR-10)
    member = Member(
        member_id=new_uuid(),
        room_id=room.room_id,
        name=body.name,
        token_hash=token_hash,
    )
    member.color = color_for(member.member_id)
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=403, detail="Forbidden")
    return member_public(member)


# --- items --------------------------------------------------------------------------

@router.get("/rooms/{room_id}/items")
def list_items(room_id: str, db: Session = Depends(get_db)):
    room = get_room_or_404(room_id, db)
    items = (
        db.query(Item).filter(Item.room_id == room.room_id).order_by(Item.created_at.desc()).all()
    )
    author_ids = {i.author_member_id for i in items}
    authors = {m.member_id: m for m in db.query(Member).filter(Member.member_id.in_(author_ids))}
    present = hub.members_snapshot(room.room_id)
    return {
        "items": items_public(items, authors),
        "members_present": [
            {"member_id": m.member_id, "name": m.name, "color": m.color} for m in present
        ],
    }


class TextBody(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_valid(cls, v: str) -> str:
        if not (1 <= len(v) <= MAX_TEXT_CHARS):
            raise ValueError(f"content must be 1-{MAX_TEXT_CHARS} characters")
        return v


@router.post("/rooms/{room_id}/items/text")
async def add_text(
    room_id: str,
    body: TextBody,
    x_member_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    room = get_room_or_404(room_id, db)
    member = require_member(room, x_member_token, db)
    from ..telemetry import items_total

    item = Item(
        item_id=new_uuid(),
        room_id=room.room_id,
        author_member_id=member.member_id,
        kind="text",
        content=body.content,
    )
    db.add(item)
    items_total.labels(kind="text").inc()
    touch_room(db, room)  # FR-19: activity extends TTL
    await hub.broadcast(room.room_id, {"type": "item_added", "item": item_public(item, member)})
    return item_public(item, member)


@router.post("/rooms/{room_id}/items/file")
async def upload_file(
    room_id: str,
    request: Request,
    file: UploadFile,
    x_member_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    from ..telemetry import tracer, upload_duration, uploads_total

    room = get_room_or_404(room_id, db)
    settings = get_settings()
    if not request.app.state.upload_limiter.hit("upload", client_ip(request)):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    member = require_member(room, x_member_token, db)

    # §7 key journey: upload → validate → store → broadcast (traced, no
    # sensitive attributes — SR-4: filenames never enter telemetry)
    span = tracer()
    started = time.perf_counter()
    result = "ok"
    try:
        with span("http.upload"):
            with span("validate_file"):
                original_name = os.path.basename(file.filename or "")
                ext = os.path.splitext(original_name)[1][1:].lower()
                if not ext or ext not in settings.allowed_ext_set:
                    result = "disallowed"
                    return JSONResponse(
                        status_code=415,
                        content={"detail": f"file type .{ext or '?'} not allowed"},
                    )

            max_bytes = effective_max_file_mb(settings, room) * 1024 * 1024  # FR-13a
            file_id = new_uuid()
            with span("persist_file"):
                dest_dir = room_dir(settings, room.room_id)
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, file_id)
                size = 0
                too_large = False
                try:
                    with open(dest_path, "wb") as out:
                        while chunk := await file.read(UPLOAD_CHUNK):
                            size += len(chunk)
                            if size > max_bytes:
                                too_large = True
                                break
                            out.write(chunk)
                finally:
                    await file.close()
            if too_large:
                result = "too_large"
                os.remove(dest_path)
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"file exceeds this room's {effective_max_file_mb(settings, room)} MB limit"},
                )

            item = Item(
                item_id=new_uuid(),
                room_id=room.room_id,
                author_member_id=member.member_id,
                kind="file",
                file_name=original_name,
                file_id=file_id,
                file_path=dest_path,
                file_size=size,
                mime=file.content_type or "application/octet-stream",
            )
            db.add(item)
            from ..telemetry import items_total

            items_total.labels(kind="file").inc()
            touch_room(db, room)
            logging.getLogger("cliproom.upload").info("upload journey: file accepted")
            with span("ws.broadcast"):
                await hub.broadcast(
                    room.room_id, {"type": "item_added", "item": item_public(item, member)}
                )
            return item_public(item, member)
    except Exception:
        result = "error"
        raise
    finally:
        uploads_total.labels(result=result).inc()
        upload_duration.observe(time.perf_counter() - started)


@router.delete("/rooms/{room_id}/items/{item_id}")
async def delete_item(
    room_id: str,
    item_id: str,
    request: Request,
    x_member_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    room = get_room_or_404(room_id, db)
    if not request.app.state.delete_limiter.hit("delete", client_ip(request)):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    member = require_member(room, x_member_token, db)
    item = db.get(Item, item_id)
    if item is None or item.room_id != room.room_id:
        raise HTTPException(status_code=404, detail="Not Found")
    if item.author_member_id != member.member_id:
        # requester knows the room exists → 403 is correct (FR-15); no broadcast
        raise HTTPException(status_code=403, detail="Forbidden")
    if item.file_path and os.path.exists(item.file_path):
        os.remove(item.file_path)
    db.delete(item)
    touch_room(db, room)
    await hub.broadcast(room.room_id, {"type": "item_deleted", "item_id": item.item_id})
    return {"ok": True}


@router.get("/rooms/{room_id}/files/{file_id}")
def download_file(room_id: str, file_id: str, db: Session = Depends(get_db)):
    room = get_room_or_404(room_id, db)  # capability access: the link is the credential
    item = (
        db.query(Item)
        .filter(Item.room_id == room.room_id, Item.file_id == file_id, Item.kind == "file")
        .first()
    )
    if item is None or not item.file_path or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Not Found")
    safe_name = re.sub(r'[\r\n"\';\\]', "_", item.file_name or "download")
    ascii_name = safe_name.encode("ascii", "replace").decode()
    quoted = quote(safe_name)
    return FileResponse(
        item.file_path,
        media_type=item.mime or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
            ),
        },
    )


# --- WS ticket + WebSocket -----------------------------------------------------------

@router.post("/rooms/{room_id}/ws-ticket")
def ws_ticket(
    room_id: str,
    x_member_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    room = get_room_or_404(room_id, db)
    member = require_member(room, x_member_token, db)
    return {"ticket": tickets.issue(room.room_id, member.member_id)}


@router.websocket("/rooms/{room_id}/ws")
async def room_ws(websocket: WebSocket, room_id: str):
    settings = get_settings()

    ip = websocket.client.host if websocket.client else "unknown"
    counts = websocket.app.state.ws_conn_counts
    if counts.get(ip, 0) >= settings.rate_limit_ws_per_ip:
        await websocket.close(code=4429)
        return

    ticket = websocket.query_params.get("ticket")
    redeemed = tickets.redeem(ticket) if ticket else None
    if redeemed is None or redeemed[0] != room_id:
        await websocket.close(code=4401)
        return

    db = session_factory()()
    try:
        room = get_active_room(db, room_id)
        member = db.get(Member, redeemed[1]) if room else None
    finally:
        db.close()
    if room is None or member is None:
        await websocket.close(code=4404)
        return

    counts[ip] = counts.get(ip, 0) + 1
    await websocket.accept()
    from ..telemetry import ws_clients

    ws_clients.inc()
    connected = ConnectedMember(
        member_id=member.member_id, name=member.name, color=member.color, room_id=room.room_id
    )
    await hub.connect(room.room_id, connected, websocket)

    # full current state on (re)connect (FR-17)
    db = session_factory()()
    try:
        items = (
            db.query(Item)
            .filter(Item.room_id == room.room_id)
            .order_by(Item.created_at.desc())
            .all()
        )
        author_ids = {i.author_member_id for i in items}
        authors = {
            m.member_id: m for m in db.query(Member).filter(Member.member_id.in_(author_ids))
        }
        state_items = items_public(items, authors)
    finally:
        db.close()
    await websocket.send_json(
        {"type": "state", "items": state_items, "members": await _presence(room.room_id)}
    )
    await hub.broadcast(
        room.room_id,
        {"type": "member_joined", "member": member_public(member)},
        exclude=member.member_id,
    )
    await hub.broadcast(room.room_id, {"type": "presence", "members": await _presence(room.room_id)})

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "heartbeat":
                await hub.heartbeat(room.room_id, member.member_id)
    except WebSocketDisconnect:
        pass
    finally:
        counts[ip] = max(0, counts.get(ip, 1) - 1)
        ws_clients.dec()
        await hub.disconnect(room.room_id, member.member_id)
        await hub.broadcast(room.room_id, {"type": "member_left", "member_id": member.member_id})
        await hub.broadcast(room.room_id, {"type": "presence", "members": await _presence(room.room_id)})
