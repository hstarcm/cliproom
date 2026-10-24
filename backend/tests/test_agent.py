"""§7 / AC19: on-call agent — webhook auth, diagnosis, remediation,
agent_actions recording."""

from __future__ import annotations

import json

from app.config import get_settings
from app.db import init_engine, session_factory
from app.models import AgentAction


def _payload(name: str) -> dict:
    return {"alerts": [{"labels": {"alertname": name}, "status": "firing"}]}


def _auth_headers() -> dict:
    return {"X-Agent-Token": get_settings().agent_token}


def test_on_alert_requires_token(client, env):
    r = client.post("/api/agent/on-alert", json=_payload("SweeperStalled"))
    assert r.status_code == 403
    r = client.post(
        "/api/agent/on-alert", json=_payload("SweeperStalled"), headers={"X-Agent-Token": "wrong"}
    )
    assert r.status_code == 403


def test_on_alert_accepts_bearer_token(client, env):
    settings = get_settings()
    r = client.post(
        "/api/agent/on-alert",
        json=_payload("SweeperStalled"),
        headers={"Authorization": f"Bearer {settings.agent_token}"},
    )
    assert r.status_code == 200
    assert r.json()["handled"][0]["alert"] == "SweeperStalled"


def test_sweeper_stalled_remediation_records_action(client, env):
    settings = get_settings()
    r = client.post(
        "/api/agent/on-alert", json=_payload("SweeperStalled"), headers=_auth_headers()
    )
    assert r.status_code == 200
    outcome = r.json()["handled"][0]["outcome"]

    engine, _ = init_engine(settings.db_path)
    db = session_factory()()
    actions = db.query(AgentAction).order_by(AgentAction.id.desc()).all()
    assert actions, "agent_actions row must be recorded"
    latest = actions[-1]
    assert latest.alert_name == "SweeperStalled"
    assert latest.outcome in {"resolved", "escalated"}
    assert latest.outcome == outcome
    steps = json.loads(latest.actions)
    assert any("sweep" in s.lower() for s in steps)
    db.close()


def test_unknown_alert_escalates(client, env):
    r = client.post(
        "/api/agent/on-alert", json=_payload("SomethingElse"), headers=_auth_headers()
    )
    assert r.status_code == 200
    assert r.json()["handled"][0]["outcome"] == "escalated"
