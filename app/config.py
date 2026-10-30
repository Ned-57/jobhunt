"""Runtime configuration.

Everything is environment-driven with local-friendly defaults, so the app
runs with no setup at all and switches to Supabase by setting three vars.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = Path(os.environ.get("JOBHUNT_DATA_DIR", BASE_DIR / "data"))


def _load_dotenv() -> None:
    """Minimal .env loader so there is no python-dotenv dependency."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _secret_key() -> str:
    """Stable signing key.

    A generated key is persisted to disk so sessions survive a restart in
    local development. Set JOBHUNT_SECRET_KEY for anything real.
    """
    from_env = os.environ.get("JOBHUNT_SECRET_KEY")
    if from_env:
        return from_env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_file = DATA_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass  # Windows filesystems may not support it; not worth failing over
    return key


class Settings:
    app_name: str = "JobHunt"

    # "local" writes JSON files under data/. "supabase" uses the hosted DB.
    storage_backend: str = os.environ.get("JOBHUNT_STORAGE", "local").lower()

    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_key: str = os.environ.get("SUPABASE_SERVICE_KEY", "") or os.environ.get(
        "SUPABASE_ANON_KEY", ""
    )

    secret_key: str = _secret_key()
    session_cookie: str = "jobhunt_session"
    session_days: int = int(os.environ.get("JOBHUNT_SESSION_DAYS", "30"))

    host: str = os.environ.get("JOBHUNT_HOST", "127.0.0.1")
    port: int = int(os.environ.get("JOBHUNT_PORT", "8121"))

    # Only relevant behind HTTPS; leaving it off keeps localhost working.
    cookie_secure: bool = os.environ.get("JOBHUNT_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


settings = Settings()
