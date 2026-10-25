"""Demo/guest account configuration (FR-3): DEMO_* env vars are the preferred
names; GUEST_* still works; the role enables whenever credentials exist
(including production — regression for the silent prod disable)."""

from __future__ import annotations

from app.config import DEV_GUEST_HASH, Settings

REQUIRED = dict(
    admin_username="admin",
    admin_password_hash="x",
    session_secret="s",
    agent_token="t",
    base_url="http://t",
)


def _settings(**kw) -> Settings:
    s = Settings(**{**REQUIRED, **kw})
    s.apply_dev_defaults()
    return s


def test_demo_env_names_enable_the_role():
    s = _settings(demo_username="demo", demo_password_hash=DEV_GUEST_HASH)
    assert s.guest_username == "demo"
    assert s.guest_password_hash == DEV_GUEST_HASH
    assert s.guest_enabled is True


def test_guest_env_names_still_accepted():
    s = _settings(guest_username="demo", guest_password_hash=DEV_GUEST_HASH)
    assert s.guest_username == "demo"
    assert s.guest_enabled is True


def test_demo_takes_precedence_over_guest():
    s = _settings(
        demo_username="demo",
        demo_password_hash=DEV_GUEST_HASH,
        guest_username="old",
    )
    assert s.guest_username == "demo"


def test_role_disabled_when_credentials_absent():
    s = _settings()
    assert s.guest_enabled is False


def test_prod_credentials_enable_role_without_cliproom_dev():
    """Regression: in production (no CLIPROOM_DEV), providing the demo/guest
    env vars must enable the account — previously it stayed silently off."""
    s = Settings(**{**REQUIRED, "demo_username": "demo", "demo_password_hash": DEV_GUEST_HASH})
    s.apply_dev_defaults()  # must NOT be a no-op for the alias/enabled logic
    s.validate_required()
    assert s.guest_enabled is True
    assert s.cliproom_dev is False
