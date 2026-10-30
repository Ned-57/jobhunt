"""Storage interface.

Both backends speak this. Nothing above this layer knows whether the data
lives in a JSON file or a Postgres row, which is what makes the Supabase
switch a config change rather than a rewrite.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol


class UserRecord(dict):
    """{id, email, password_hash, created_at}"""


class Store(Protocol):
    # ---- users -----------------------------------------------------------
    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]: ...

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]: ...

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]: ...

    # ---- profile ---------------------------------------------------------
    def get_profile(self, user_id: str) -> Optional[dict[str, Any]]: ...

    def save_profile(self, user_id: str, profile: dict[str, Any]) -> dict[str, Any]: ...

    # ---- applications ----------------------------------------------------
    def list_applications(self, user_id: str) -> list[dict[str, Any]]: ...

    def save_applications(
        self, user_id: str, applications: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...

    # ---- housekeeping ----------------------------------------------------
    def describe(self) -> str: ...


class StorageError(RuntimeError):
    """Raised when the backend cannot complete an operation."""
