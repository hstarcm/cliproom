"""On-call responder agent (SPECS.md §7, FR-6, AC19).

Receives Alertmanager webhooks on /api/agent/on-alert (AGENT_TOKEN auth),
diagnoses (deterministic checks + Loki error-log lookup; LLM optional and not
required), remediates, records everything in agent_actions, and escalates by
email if remediation fails.
"""

from __future__ import annotations

import json
import logging
import shutil
import smtplib
import time
from email.message import EmailMessage

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .config import get_settings
from .db import session_factory
from .models import AgentAction, SweeperRun, utcnow
from .sweeper import run_sweep
from .security import agent_tokens_match

logger = logging.getLogger("cliproom.agent")

router = APIRouter(prefix="/api/agent")


class AlertPayload(BaseModel):
    # Alertmanager webhook body; we only rely on alerts[].labels.alertname
    alerts: list[dict] = []


def _verify_agent_token(token: str | None) -> None:
    settings = get_settings()
    if not token or not agent_tokens_match(token, settings.agent_token):
        raise HTTPException(status_code=403, detail="Forbidden")


def _loki_recent_errors(settings) -> str:
    """Deterministic diagnosis aid: recent error lines from Loki (if reachable)."""
    url = (
        f"{settings.loki_url}/loki/api/v1/query_range"
        "?query=" + "%7Blevel%3D%22error%22%7D" +
        f"&start={int(time.time() - 3600) * 1_000_000_000}"
        f"&end={int(time.time()) * 1_000_000_000}&limit=20"
    )
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        lines = [
            r[1]
            for r in resp.json().get("data", {}).get("result", [])
            for r in [r.get("values", [])]
            for r in r
        ]
        return "\n".join(lines[:20]) or "(no recent error lines)"
    except Exception:  # noqa: BLE001 — Loki may be down; diagnosis continues
        return "(Loki unreachable — skipped)"


def _disk_ok(settings) -> tuple[bool, str]:
    try:
        usage = shutil.disk_usage(settings.data_dir)
        free_mb = usage.free // (1024 * 1024)
        return free_mb > 100, f"free disk: {free_mb} MB"
    except OSError as exc:
        return False, f"disk check failed: {exc}"


def _db_writable() -> tuple[bool, str]:
    try:
        db = session_factory()()
        try:
            probe = SweeperRun(started_at=utcnow(), status="probe", finished_at=utcnow())
            db.add(probe)
            db.commit()
            db.delete(probe)
            db.commit()
            return True, "db write probe ok"
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"db write probe failed: {exc}"


def _synthetic_upload_ok(settings) -> tuple[bool, str]:
    """Write + delete a probe file through the upload storage path."""
    import os
    import tempfile

    try:
        os.makedirs(settings.data_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=settings.data_dir, suffix=".txt")
        with os.fdopen(fd, "wb") as f:
            f.write(b"cliproom upload probe")
        os.remove(path)
        return True, "synthetic upload ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"synthetic upload failed: {exc}"


def _escalate(settings, subject: str, body: str) -> bool:
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = settings.smtp_to
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_user:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("escalation email failed: %s", type(exc).__name__)
        return False


@router.post("/on-alert")
def on_alert(payload: AlertPayload, x_agent_token: str | None = Header(default=None, alias="X-Agent-Token")):
    settings = get_settings()
    _verify_agent_token(x_agent_token)

    results = []
    for alert in payload.alerts:
        name = alert.get("labels", {}).get("alertname", "Unknown")
        results.append(_handle_alert(settings, name, alert))
    return {"handled": results}


def _handle_alert(settings, alert_name: str, alert: dict) -> dict:
    db = session_factory()()
    action = AgentAction(alert_name=alert_name, diagnosis="", actions="", outcome="pending")
    db.add(action)
    db.commit()

    steps: list[str] = []

    if alert_name == "UploadErrorSpike":
        disk_ok, disk_info = _disk_ok(settings)
        db_ok, db_info = _db_writable()
        steps += [disk_info, db_info]
        if disk_ok and db_ok:
            steps.append("restart upload subsystem (clear limiter state)")
            from .main import app_state  # local import avoids a cycle

            app_state().upload_limiter.reset()
            up_ok, up_info = _synthetic_upload_ok(settings)
            steps.append(up_info)
            outcome = "resolved" if up_ok else "escalated"
        else:
            up_ok, up_info = _synthetic_upload_ok(settings)
            steps.append(up_info)
            outcome = "resolved" if (disk_ok and db_ok and up_ok) else "escalated"
    elif alert_name == "SweeperStalled":
        steps.append("manual sweep triggered")
        try:
            summary = run_sweep(settings)
            steps.append(
                f"sweep done: rooms={summary['rooms_deleted']} "
                f"files={summary['files_deleted']} orphans={summary['orphans_deleted']}"
            )
            last = (
                db.query(SweeperRun)
                .filter(SweeperRun.status == "ok")
                .order_by(SweeperRun.started_at.desc())
                .first()
            )
            outcome = "resolved" if last is not None else "escalated"
            steps.append(f"last successful run: {last.started_at.isoformat() if last else 'none'}")
        except Exception as exc:  # noqa: BLE001
            steps.append(f"sweep failed: {exc}")
            outcome = "escalated"
    else:
        steps.append("unknown alert — no automated remediation")
        outcome = "escalated"

    diagnosis = {
        "status": alert.get("status"),
        "deterministic_checks": steps[:2],
        "loki_errors": _loki_recent_errors(settings),
    }
    action.diagnosis = json.dumps(diagnosis)
    action.actions = json.dumps(steps)
    action.outcome = outcome
    db.commit()
    db.close()

    if outcome == "escalated":
        _escalate(
            settings,
            f"[ClipRoom] {alert_name} — remediation failed",
            f"Alert: {json.dumps(alert, indent=2)}\n\nDiagnosis: {action.diagnosis}\nActions: {action.actions}",
        )
    return {"alert": alert_name, "outcome": outcome, "steps": steps}
