"""Application settings loaded from environment variables (SPECS.md §5).

Production requires the mandatory variables; in dev mode (CLIPROOM_DEV=1, set
only by the local docker-compose file) safe bootstrap defaults kick in so the
stack starts with a single command (AC13) without committing real credentials.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Deny-by-default allowlist (FR-13). Line between allowed/rejected:
# anything that could execute on the server (php/jsp/asp/exe/…) or
# auto-execute in a browser (html/svg/js-as-page) stays OUT; scripts and
# docs that only run when the recipient deliberately opens them are IN.
DEFAULT_ALLOWED_EXTENSIONS = (
    "png,jpg,jpeg,gif,webp,pdf,txt,md,csv,"  # images & text
    "zip,7z,rar,"  # archives
    "py,ipynb,yaml,yml,json,toml,ini,xml,sql,"  # data & config
    "js,mjs,cjs,ts,tsx,jsx,css,scss,less,vue,svelte,"  # frontend source
    "java,c,h,hpp,cc,cpp,cs,go,rs,rb,kt,swift,sh,bash,"  # source & scripts
    "doc,docx,xls,xlsx,ppt,pptx"  # MS Office (macro-free handling: docm/xlsm/pptm excluded)
)

# argon2id hashes of the documented dev-only bootstrap credentials
# ("cliproom-dev-admin" / "cliproom-dev-guest"). Used ONLY when
# CLIPROOM_DEV=1 (local docker-compose); production must set real
# ADMIN_PASSWORD_HASH / GUEST_PASSWORD_HASH env vars (FR-3).
DEV_ADMIN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "WhqDhLVDxegI6tI02EL98A$"
    "jaXj5uuEyaoPPtI1jtCX9hz2nSjQcA99IkJq9O8VZKU"
)
DEV_GUEST_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "msIiF9O08asleb6KFP5Xew$"
    "NgfdeOZH/A4GwbQrYSTEpXY7L09/kQGcZekIi1dAUFo"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # --- operator accounts (FR-3) -------------------------------------------
    admin_username: str = ""
    admin_password_hash: str = ""
    guest_username: str = ""
    guest_password_hash: str = ""
    guest_enabled: bool = False

    # --- secrets --------------------------------------------------------------
    session_secret: str = ""
    agent_token: str = ""

    # --- URLs / limits ---------------------------------------------------------
    base_url: str = "http://localhost:8080"
    max_file_mb: int = 10
    allowed_extensions: str = DEFAULT_ALLOWED_EXTENSIONS
    data_dir: str = os.path.join("data", "files")
    db_path: str = os.path.join("data", "cliproom.db")
    sweeper_interval_min: int = 60

    # --- rate limits (SR-3) ----------------------------------------------------
    rate_limit_login_per_15min: int = 5
    rate_limit_create_per_hour: int = 5
    rate_limit_upload_per_hour: int = 30
    rate_limit_delete_per_hour: int = 60
    rate_limit_ws_per_ip: int = 10

    # --- SMTP (alerts; Mailpit in dev) -----------------------------------------
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "cliproom-alerts@localhost"
    smtp_to: str = "operator@localhost"

    # --- telemetry ----------------------------------------------------------------
    otel_exporter_otlp_endpoint: str = ""
    loki_url: str = "http://loki:3100"

    # --- dev bootstrap ----------------------------------------------------------
    cliproom_dev: bool = False
    log_level: str = "INFO"

    @property
    def allowed_ext_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    def apply_dev_defaults(self) -> None:
        """Fill in bootstrap credentials for local dev only (never prod)."""
        if not self.cliproom_dev:
            return
        if not self.admin_username:
            self.admin_username = "admin"
        if not self.admin_password_hash:
            self.admin_password_hash = DEV_ADMIN_HASH
        if not self.guest_username:
            self.guest_username = "guest"
        if not self.guest_password_hash:
            self.guest_password_hash = DEV_GUEST_HASH
            self.guest_enabled = True
        if not self.session_secret:
            self.session_secret = secrets.token_hex(32)
        if not self.agent_token:
            # fixed dev token so the local Alertmanager config can reach the
            # agent endpoint (prod must set a real AGENT_TOKEN everywhere)
            self.agent_token = "cliproom-dev-agent-token"

    def validate_required(self) -> None:
        missing = [
            name
            for name in (
                "admin_username",
                "admin_password_hash",
                "session_secret",
                "agent_token",
                "base_url",
            )
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                f"missing required environment variables: {', '.join(missing.upper())} "
                "(set them, or use CLIPROOM_DEV=1 for local bootstrap defaults)"
            )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.apply_dev_defaults()
    s.validate_required()
    return s
