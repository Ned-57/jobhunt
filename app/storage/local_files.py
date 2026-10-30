"""JSON-file storage.

One directory per concern, one file per user. Readable, greppable, and
trivially backed up by copying the folder - which is the point for a tool
you run on your own machine.

Writes go through a temp file and os.replace so an interrupted write cannot
leave a half-written profile behind.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .base import StorageError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LocalFileStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.users_file = self.root / "users.json"
        self.profiles_dir = self.root / "profiles"
        self.apps_dir = self.root / "applications"
        self._lock = threading.RLock()
        for directory in (self.root, self.profiles_dir, self.apps_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # ---- io helpers ------------------------------------------------------
    def _read(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StorageError(f"Could not read {path.name}: {exc}") from exc

    def _write(self, path: Path, payload: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp, path)
        except OSError as exc:
            raise StorageError(f"Could not write {path.name}: {exc}") from exc
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _users(self) -> dict[str, dict[str, Any]]:
        return self._read(self.users_file, {})

    # ---- users -----------------------------------------------------------
    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        email = email.strip().lower()
        for user in self._users().values():
            if user.get("email") == email:
                return dict(user)
        return None

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        user = self._users().get(user_id)
        return dict(user) if user else None

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        email = email.strip().lower()
        with self._lock:
            users = self._users()
            if any(u.get("email") == email for u in users.values()):
                raise StorageError("An account already exists for that email address.")
            user = {
                "id": str(uuid.uuid4()),
                "email": email,
                "password_hash": password_hash,
                "created_at": _now(),
            }
            users[user["id"]] = user
            self._write(self.users_file, users)
        return dict(user)

    # ---- profile ---------------------------------------------------------
    def get_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        return self._read(self.profiles_dir / f"{user_id}.json", None)

    def save_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        profile = dict(profile)
        profile["updated_at"] = _now()
        with self._lock:
            self._write(self.profiles_dir / f"{user_id}.json", profile)
        return profile

    # ---- applications ----------------------------------------------------
    def list_applications(self, user_id: str) -> list[dict[str, Any]]:
        return self._read(self.apps_dir / f"{user_id}.json", [])

    def save_applications(
        self, user_id: str, applications: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._write(self.apps_dir / f"{user_id}.json", applications)
        return applications

    # ---- housekeeping ----------------------------------------------------
    def describe(self) -> str:
        return f"local files ({self.root})"
