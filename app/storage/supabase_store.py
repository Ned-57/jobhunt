"""Supabase storage.

Not wired up by default. Set these and restart:

    JOBHUNT_STORAGE=supabase
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_SERVICE_KEY=<service role key>

Apply supabase/schema.sql first - it creates the three tables this expects
and the row-level security policies that go with them.

The service key bypasses RLS, so this module scopes every query by user_id
itself. Keep that key server-side only; it must never reach the browser.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .base import StorageError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SupabaseStore:
    def __init__(self, url: str, key: str):
        try:
            from supabase import create_client  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise StorageError(
                "The supabase package is not installed. Run: pip install supabase"
            ) from exc
        self.client = create_client(url, key)
        self.url = url

    # ---- users -----------------------------------------------------------
    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        result = (
            self.client.table("users")
            .select("*")
            .eq("email", email.strip().lower())
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        result = self.client.table("users").select("*").eq("id", user_id).limit(1).execute()
        rows = result.data or []
        return rows[0] if rows else None

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        email = email.strip().lower()
        if self.get_user_by_email(email):
            raise StorageError("An account already exists for that email address.")
        row = {
            "id": str(uuid.uuid4()),
            "email": email,
            "password_hash": password_hash,
            "created_at": _now(),
        }
        result = self.client.table("users").insert(row).execute()
        return (result.data or [row])[0]

    # ---- profile ---------------------------------------------------------
    def get_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        result = (
            self.client.table("profiles")
            .select("data")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0]["data"] if rows else None

    def save_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        profile = dict(profile)
        profile["updated_at"] = _now()
        self.client.table("profiles").upsert(
            {"user_id": user_id, "data": profile, "updated_at": profile["updated_at"]},
            on_conflict="user_id",
        ).execute()
        return profile

    # ---- applications ----------------------------------------------------
    def list_applications(self, user_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("applications")
            .select("data")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return [row["data"] for row in (result.data or [])]

    def save_applications(
        self, user_id: str, applications: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        # The client owns the whole list, so replace it wholesale. Fine at the
        # scale of one person's job search; revisit if this ever grows.
        self.client.table("applications").delete().eq("user_id", user_id).execute()
        if applications:
            self.client.table("applications").insert(
                [
                    {
                        "id": app.get("id") or str(uuid.uuid4()),
                        "user_id": user_id,
                        "data": app,
                        "created_at": app.get("created_at") or _now(),
                    }
                    for app in applications
                ]
            ).execute()
        return applications

    # ---- housekeeping ----------------------------------------------------
    def describe(self) -> str:
        return f"supabase ({self.url})"
