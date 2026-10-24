"""Item/room serialization — SPECS.md §6 shapes. WS events carry no room IDs
beyond the connection scope itself (SR-4)."""

from __future__ import annotations

from .models import Item, Member, iso_utc


def member_public(m: Member) -> dict:
    return {"member_id": m.member_id, "name": m.name, "color": m.color}


def item_public(item: Item, author: Member) -> dict:
    out = {
        "item_id": item.item_id,
        "kind": item.kind,
        "author": member_public(author),
        "created_at": iso_utc(item.created_at),
    }
    if item.kind == "text":
        out["content"] = item.content
    else:
        out["file"] = {
            "file_id": item.file_id,
            "name": item.file_name,
            "size": item.file_size,
            "mime": item.mime,
        }
    return out


def items_public(items: list[Item], authors: dict[str, Member]) -> list[dict]:
    return [item_public(i, authors.get(i.author_member_id)) for i in items]
