"""
In-memory geometry reference store.

Spatial tool results (GeoJSON) are cached here by session so the LLM
only needs to pass short reference IDs (e.g. ``"geo_a1b2c3"``) instead
of generating hundreds of kilobytes of raw coordinate arrays token-by-token.

Usage
-----
    from geometry_store import geometry_store

    ref = geometry_store.store(session_id, geojson_dict)
    # -> "geo_a1b2c3"

    geojson = geometry_store.retrieve(session_id, ref)
    # -> { "type": "Feature", ... }
"""

import logging
import secrets
import time
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Default time-to-live for cached geometries (seconds).
_DEFAULT_TTL_SECONDS = 30 * 60  # 30 minutes


class _GeometryEntry:
    __slots__ = ("geojson", "expires_at")

    def __init__(self, geojson: dict, ttl: int):
        self.geojson = geojson
        self.expires_at = time.monotonic() + ttl


class GeometryStore:
    """Thread-safe, per-session geometry cache with TTL-based eviction."""

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        self._ttl = ttl_seconds
        # session_id -> { ref_id -> _GeometryEntry }
        self._store: dict[str, dict[str, _GeometryEntry]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, session_id: str, geojson: Any) -> str:
        """
        Store a GeoJSON object and return a short reference ID.

        The reference can be passed to map tools (e.g. ``draw_shape``)
        so the LLM never needs to generate raw coordinate data.
        """
        ref_id = f"geo_{secrets.token_hex(4)}"
        entry = _GeometryEntry(geojson, self._ttl)
        with self._lock:
            bucket = self._store.setdefault(session_id, {})
            bucket[ref_id] = entry
        return ref_id

    def store_batch(self, session_id: str, items: list[dict]) -> list[str]:
        """
        Store multiple GeoJSON objects at once.

        *items* is a list of dicts, each containing at least a ``"geojson"`` key.
        Returns a list of reference IDs in the same order.
        """
        refs: list[str] = []
        now = time.monotonic()
        with self._lock:
            bucket = self._store.setdefault(session_id, {})
            for item in items:
                geojson = item if not isinstance(item, dict) or "geojson" not in item else item["geojson"]
                ref_id = f"geo_{secrets.token_hex(4)}"
                bucket[ref_id] = _GeometryEntry(geojson, self._ttl)
                refs.append(ref_id)
        return refs

    def retrieve(self, session_id: str, ref_id: str) -> dict | None:
        """
        Retrieve a cached GeoJSON object by reference ID.

        Returns ``None`` if the reference is expired or unknown.
        """
        with self._lock:
            bucket = self._store.get(session_id)
            if not bucket:
                return None
            entry = bucket.get(ref_id)
            if not entry:
                return None
            if time.monotonic() > entry.expires_at:
                del bucket[ref_id]
                return None
            return entry.geojson

    def clear(self, session_id: str) -> None:
        """Remove all cached geometries for a session."""
        with self._lock:
            self._store.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries across all sessions.

        Returns the number of entries removed.  Intended to be called
        periodically (e.g. from the session cleanup loop).
        """
        now = time.monotonic()
        removed = 0
        with self._lock:
            empty_sessions: list[str] = []
            for sid, bucket in self._store.items():
                expired_keys = [k for k, v in bucket.items() if now > v.expires_at]
                for k in expired_keys:
                    del bucket[k]
                    removed += 1
                if not bucket:
                    empty_sessions.append(sid)
            for sid in empty_sessions:
                del self._store[sid]
        if removed:
            logger.debug("Geometry store cleanup: removed %d expired entries", removed)
        return removed


# Module-level singleton — import this in MCP servers.
geometry_store = GeometryStore()
