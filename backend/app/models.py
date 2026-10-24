"""SQLAlchemy models — SPECS.md §6 data model (SQLite, WAL)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC now — SQLite round-trips datetimes without tzinfo, so the
    whole app consistently uses naive UTC internally."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    """API-facing ISO-8601 with explicit UTC marker."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class Base(DeclarativeBase):
    pass


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    room_uuid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_by: Mapped[str] = mapped_column(
        String(8), CheckConstraint("created_by IN ('admin','guest')")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # ttl_seconds / expires_at are NULL for 'forever' rooms (FR-19)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    max_file_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # FR-13a
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.room_id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.room_id", ondelete="CASCADE"), index=True)
    author_member_id: Mapped[str] = mapped_column(
        ForeignKey("members.member_id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(4), CheckConstraint("kind IN ('text','file')"))
    content: Mapped[Text | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(127), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SweeperRun(Base):
    __tablename__ = "sweeper_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rooms_deleted: Mapped[int] = mapped_column(Integer, default=0)
    files_deleted: Mapped[int] = mapped_column(Integer, default=0)
    orphans_deleted: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_name: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    diagnosis: Mapped[Text | None] = mapped_column(Text, nullable=True)
    actions: Mapped[Text | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="pending")
