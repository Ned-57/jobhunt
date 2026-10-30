"""Storage factory."""
from __future__ import annotations

import logging

from ..config import DATA_DIR, settings
from .base import Store, StorageError
from .local_files import LocalFileStore

log = logging.getLogger("jobhunt.storage")

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is not None:
        return _store

    if settings.storage_backend == "supabase":
        if not settings.supabase_configured:
            raise StorageError(
                "JOBHUNT_STORAGE=supabase but SUPABASE_URL / SUPABASE_SERVICE_KEY are not set."
            )
        from .supabase_store import SupabaseStore

        _store = SupabaseStore(settings.supabase_url, settings.supabase_key)
    else:
        _store = LocalFileStore(DATA_DIR)

    log.info("Storage backend: %s", _store.describe())
    return _store


__all__ = ["get_store", "Store", "StorageError"]
