"""
Copilot usage tracking module.

Listens to SDK session events, normalises them into a stable internal schema,
and emits clean usage snapshots to the rest of the application.

Design principles:
- Provider-specific logic is isolated here; the rest of the app never touches
  raw Copilot SDK event details.
- All values sourced from the SDK are labelled with a confidence field
  (authoritative / estimated / unavailable).
- No hard-coded plan allowances, model multipliers, or token billing rules.
- Idempotent: duplicate events for the same api_call_id are ignored.
- Gracefully degrades when fields are missing or events are partial.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from copilot.generated.session_events import (
    SessionEvent,
    SessionEventType,
)

logger = logging.getLogger(__name__)

_MAX_TOOL_SUMMARY_CHARS = 240
_MAX_TOOL_VALUE_JSON_CHARS = 16_384


# ---------------------------------------------------------------------------
# Internal schema
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """Record of a single MCP tool invocation during a turn."""

    tool_call_id: str = field(default="", repr=False)
    tool_name: str = ""
    server_name: str = ""
    summary: str = ""
    document_names: list[str] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "summary": self.summary,
            "document_names": list(self.document_names),
        }


@dataclass
class TurnUsage:
    """Per-turn usage snapshot for a single user prompt → assistant reply."""

    turn_id: str = ""
    model: str = ""
    model_multiplier: float | None = None
    premium_requests: float = 0
    input_tokens: float = 0
    output_tokens: float = 0
    cache_read_tokens: float = 0
    cache_write_tokens: float = 0
    total_nano_aiu: float = 0
    duration_ms: float = 0
    tool_calls: list[ToolCall] = field(default_factory=list, repr=False)
    # IDs of assistant.usage events already accounted for (idempotency guard).
    _seen_api_call_ids: set[str] = field(default_factory=set, repr=False)

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "model": self.model,
            "model_multiplier": self.model_multiplier,
            "premium_requests": self.premium_requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_nano_aiu": self.total_nano_aiu,
            "duration_ms": self.duration_ms,
            "tool_calls": [tool_call.to_dict() for tool_call in self.tool_calls],
        }


@dataclass
class SessionUsage:
    """Cumulative session-level usage totals."""

    total_premium_requests: float = 0
    total_input_tokens: float = 0
    total_output_tokens: float = 0
    total_cache_read_tokens: float = 0
    total_cache_write_tokens: float = 0
    total_nano_aiu: float = 0
    total_duration_ms: float = 0
    # Context window tracking (from session.context_changed).
    current_context_tokens: float | None = None
    context_token_limit: float | None = None

    def to_dict(self) -> dict:
        return {
            "total_premium_requests": self.total_premium_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "total_nano_aiu": self.total_nano_aiu,
            "total_duration_ms": self.total_duration_ms,
            "current_context_tokens": self.current_context_tokens,
            "context_token_limit": self.context_token_limit,
        }


@dataclass
class MonthlyUsage:
    """
    Monthly premium request quota snapshot.

    Populated from QuotaSnapshot if available in the SDK's assistant.usage
    event.  Values come directly from GitHub – they are authoritative when
    present.
    """

    used_requests: float | None = None
    entitlement_requests: float | None = None
    is_unlimited: bool = False
    remaining_percentage: float | None = None
    overage: float | None = None
    reset_date: str | None = None
    confidence: str = "unavailable"  # authoritative | estimated | unavailable

    def to_dict(self) -> dict:
        return {
            "used_requests": self.used_requests,
            "entitlement_requests": self.entitlement_requests,
            "is_unlimited": self.is_unlimited,
            "remaining_percentage": self.remaining_percentage,
            "overage": self.overage,
            "reset_date": self.reset_date,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# Per-chat tracker
# ---------------------------------------------------------------------------

class ChatUsageTracker:
    """
    Tracks usage for a single chat (== Copilot session).

    Attach via ``session.on(tracker.handle_event)`` before sending messages.
    Call ``start_turn()`` before each ``send_and_wait()`` and
    ``finalise_turn()`` after it returns to get a clean turn snapshot.
    """

    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.session_usage = SessionUsage()
        self.monthly_usage = MonthlyUsage()
        self._current_turn: TurnUsage | None = None
        self._finalised_turns: list[TurnUsage] = []
        # Set to True once SESSION_USAGE_INFO provides an authoritative running
        # session total.  When True, finalise_turn() does NOT add the turn's
        # premium_requests to the session total a second time (avoid double-
        # counting when both sources are active).  Reset each turn so that if
        # the SDK stops sending SESSION_USAGE_INFO we fall back to accumulation.
        self._session_total_is_authoritative: bool = False

    # -- Turn lifecycle -----------------------------------------------------

    def start_turn(self, turn_id: str = "") -> None:
        """Begin a new turn; resets the per-turn accumulator."""
        self._current_turn = TurnUsage(turn_id=turn_id)
        # Reset per-turn so that if the SDK stops emitting SESSION_USAGE_INFO
        # for a particular turn we fall back to turn-level accumulation.
        self._session_total_is_authoritative = False

    def finalise_turn(self) -> TurnUsage:
        """
        Finalise and return the current turn, folding it into session totals.

        Returns a zeroed TurnUsage if no turn was started (defensive).
        """
        turn = self._current_turn or TurnUsage()
        self._current_turn = None

        # Fold into session totals.
        # premium_requests: only accumulate from turns when the SDK has NOT
        # provided an authoritative running total via SESSION_USAGE_INFO.
        # If it has, the session total is already correct and adding the turn
        # value again would double-count.
        if not self._session_total_is_authoritative:
            self.session_usage.total_premium_requests += turn.premium_requests
        self.session_usage.total_input_tokens += turn.input_tokens
        self.session_usage.total_output_tokens += turn.output_tokens
        self.session_usage.total_cache_read_tokens += turn.cache_read_tokens
        self.session_usage.total_cache_write_tokens += turn.cache_write_tokens
        self.session_usage.total_nano_aiu += turn.total_nano_aiu
        self.session_usage.total_duration_ms += turn.duration_ms

        self._finalised_turns.append(turn)
        return turn

    # -- Event handler ------------------------------------------------------

    def handle_event(self, event: SessionEvent) -> None:
        """
        Session-event callback.  Safe to register via ``session.on()``.

        Handles:
        - assistant.usage  → per-turn token/cost accumulation + quota snapshot
        - session.context_changed → context window tracking
        - session.usage_info → additional session-level info
        """
        try:
            if event.type == SessionEventType.ASSISTANT_USAGE:
                self._on_assistant_usage(event)
            elif event.type == SessionEventType.SESSION_CONTEXT_CHANGED:
                self._on_context_changed(event)
            elif event.type == SessionEventType.SESSION_USAGE_INFO:
                self._on_session_usage_info(event)
            elif event.type == SessionEventType.TOOL_EXECUTION_START:
                self._on_tool_execution_start(event)
            elif event.type == SessionEventType.TOOL_EXECUTION_PROGRESS:
                self._on_tool_execution_progress(event)
            elif event.type == SessionEventType.TOOL_EXECUTION_COMPLETE:
                self._on_tool_execution_complete(event)
        except Exception:
            logger.warning(
                "Usage tracker event error for chat %s", self.chat_id, exc_info=True,
            )

    # -- Private event processors -------------------------------------------

    def _on_assistant_usage(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return

        # Idempotency: skip duplicate events keyed by api_call_id.
        api_call_id = getattr(d, "api_call_id", None)

        turn = self._current_turn
        if turn is None:
            # Usage event arrived outside a tracked turn; log but don't crash.
            logger.debug("Usage event outside turn for chat %s", self.chat_id)
            return

        if api_call_id:
            if api_call_id in turn._seen_api_call_ids:
                logger.debug("Duplicate usage event %s ignored", api_call_id)
                return
            turn._seen_api_call_ids.add(api_call_id)

        # Token counts.
        turn.input_tokens += _safe_float(d, "input_tokens")
        turn.output_tokens += _safe_float(d, "output_tokens")
        turn.cache_read_tokens += _safe_float(d, "cache_read_tokens")
        turn.cache_write_tokens += _safe_float(d, "cache_write_tokens")
        turn.duration_ms += _safe_float(d, "duration")

        # Model & cost.
        model = getattr(d, "model", None)
        if model:
            turn.model = model
        cost = getattr(d, "cost", None)
        if cost is not None:
            turn.model_multiplier = cost
            turn.premium_requests += cost

        # Nano-AIU from CopilotUsage if present.
        copilot_usage = getattr(d, "copilot_usage", None)
        if copilot_usage is not None:
            nano = getattr(copilot_usage, "total_nano_aiu", None)
            if nano is not None:
                turn.total_nano_aiu += nano

        # Quota snapshot → monthly usage (authoritative from GitHub).
        quota_snapshots = getattr(d, "quota_snapshots", None)
        if quota_snapshots:
            self._update_monthly_from_quota(quota_snapshots)

    def _on_context_changed(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return
        current = getattr(d, "current_tokens", None)
        limit = getattr(d, "token_limit", None)
        if current is not None:
            self.session_usage.current_context_tokens = current
        if limit is not None:
            self.session_usage.context_token_limit = limit

    def _on_session_usage_info(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return
        # SESSION_USAGE_INFO carries a running total of premium requests for
        # the whole Copilot session (authoritative from GitHub's billing layer).
        # Mark the flag so finalise_turn() knows not to add the turn's
        # premium_requests on top of this.
        total_pr = getattr(d, "total_premium_requests", None)
        if total_pr is not None:
            self._session_total_is_authoritative = True
            self.session_usage.total_premium_requests = total_pr

    def _on_tool_execution_start(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return

        turn = self._current_turn
        if turn is None:
            return

        tool_call_id, tool_name, server_name = _extract_tool_identity(d)
        arguments = getattr(d, "arguments", None)
        summary = _build_tool_summary(
            server_name,
            tool_name,
            raw_summary=_extract_tool_summary(d),
            arguments=arguments,
        )
        if tool_name or server_name:
            turn.tool_calls.append(ToolCall(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                server_name=server_name,
                summary=summary,
                document_names=_extract_document_names(
                    server_name,
                    tool_name,
                    arguments,
                ),
            ))
            logger.debug(
                "Tool call recorded for chat %s: %s/%s",
                self.chat_id, server_name, tool_name,
            )

    def _on_tool_execution_progress(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return

        turn = self._current_turn
        if turn is None:
            return

        tool_call_id, tool_name, server_name = _extract_tool_identity(d)
        summary = _build_tool_summary(
            server_name,
            tool_name,
            raw_summary=_extract_tool_summary(d),
            arguments=getattr(d, "arguments", None),
            result=getattr(d, "result", None),
            allow_raw_fallback=False,
        )
        tool_call = _find_or_create_tool_call(
            turn,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            server_name=server_name,
        )
        if tool_call is None:
            return

        if summary:
            tool_call.summary = _merge_tool_summary(tool_call.summary, summary)

    def _on_tool_execution_complete(self, event: SessionEvent) -> None:
        d = event.data
        if d is None:
            return

        turn = self._current_turn
        if turn is None:
            return

        tool_call_id, tool_name, server_name = _extract_tool_identity(d)
        arguments = getattr(d, "arguments", None)
        result = getattr(d, "result", None)
        summary = _build_tool_summary(
            server_name,
            tool_name,
            raw_summary=_extract_tool_summary(d),
            arguments=arguments,
            result=result,
        )
        document_names = _extract_document_names(
            server_name,
            tool_name,
            arguments,
            result,
        )
        tool_call = _find_or_create_tool_call(
            turn,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            server_name=server_name,
        )
        if tool_call is None:
            return

        if summary:
            tool_call.summary = _merge_tool_summary(tool_call.summary, summary)
        if document_names:
            tool_call.document_names = _merge_unique_strings(
                tool_call.document_names,
                document_names,
            )

    def _update_monthly_from_quota(self, snapshots: dict) -> None:
        """
        Select the most relevant quota snapshot entry for premium request tracking.

        The SDK sends multiple quota keys (e.g. "completions", "chat",
        "premium_requests").  The "completions" / "chat" entries are typically
        unlimited for all plans; the "premium_requests" entry carries the
        bounded monthly allowance that we actually want to display.

        Selection priority:
          1. Any key whose name contains "premium" (case-insensitive).
          2. Any key where is_unlimited_entitlement = False (bounded quota).
          3. Fall back to the first entry if all are unlimited or only one exists.
        """
        if not snapshots:
            return

        best_key: str | None = None
        best_snap = None
        fallback_key: str | None = None
        fallback_snap = None

        for key, snap in snapshots.items():
            is_unlimited = getattr(snap, "is_unlimited_entitlement", False)
            logger.debug(
                "Quota snapshot key=%r unlimited=%s used=%s entitlement=%s remaining_pct=%s",
                key, is_unlimited,
                getattr(snap, "used_requests", None),
                getattr(snap, "entitlement_requests", None),
                getattr(snap, "remaining_percentage", None),
            )

            # Keep the very first entry as a last-resort fallback.
            if fallback_snap is None:
                fallback_key, fallback_snap = key, snap

            # Highest priority: explicit "premium" key.
            if "premium" in key.lower():
                best_key, best_snap = key, snap
                break

            # Second priority: any bounded (non-unlimited) quota.
            if not is_unlimited and best_snap is None:
                best_key, best_snap = key, snap

        chosen_key = best_key if best_snap is not None else fallback_key
        chosen_snap = best_snap if best_snap is not None else fallback_snap

        if chosen_snap is None:
            return

        logger.info(
            "Monthly quota from snapshot key=%r: used=%s / %s unlimited=%s",
            chosen_key,
            getattr(chosen_snap, "used_requests", None),
            getattr(chosen_snap, "entitlement_requests", None),
            getattr(chosen_snap, "is_unlimited_entitlement", False),
        )

        self.monthly_usage.used_requests = getattr(chosen_snap, "used_requests", None)
        self.monthly_usage.entitlement_requests = getattr(chosen_snap, "entitlement_requests", None)
        self.monthly_usage.is_unlimited = getattr(chosen_snap, "is_unlimited_entitlement", False)
        # Normalise remaining_percentage to the 0–1 scale expected by the
        # frontend formula ``(1 - remaining) * 100``.  The SDK may return a
        # 0-100 value (e.g. 73.0 meaning 73 % remaining), which would produce
        # absurd results like -7200 % without normalisation.
        remaining = getattr(chosen_snap, "remaining_percentage", None)
        if remaining is not None and remaining > 1.0:
            remaining = remaining / 100.0
        self.monthly_usage.remaining_percentage = remaining
        self.monthly_usage.overage = getattr(chosen_snap, "overage", None)
        reset = getattr(chosen_snap, "reset_date", None)
        if reset is not None:
            self.monthly_usage.reset_date = (
                reset.isoformat() if isinstance(reset, datetime) else str(reset)
            )
        self.monthly_usage.confidence = "authoritative"

    # -- Snapshot for API response ------------------------------------------

    def snapshot(self, turn: TurnUsage | None = None) -> dict:
        """
        Return a complete usage snapshot suitable for sending to the frontend.

        If *turn* is provided its data is included; otherwise the in-progress
        turn (if any) is snapshotted.
        """
        t = turn or self._current_turn
        return {
            "turn": t.to_dict() if t else None,
            "session": self.session_usage.to_dict(),
            "monthly": self.monthly_usage.to_dict(),
        }


# ---------------------------------------------------------------------------
# Registry – maps chat_id to its tracker
# ---------------------------------------------------------------------------

_trackers: dict[str, ChatUsageTracker] = {}


def get_or_create_tracker(chat_id: str) -> ChatUsageTracker:
    """Return (or create) the usage tracker for a chat."""
    if chat_id not in _trackers:
        _trackers[chat_id] = ChatUsageTracker(chat_id)
    return _trackers[chat_id]


def discard_tracker(chat_id: str) -> None:
    """Remove the tracker for a chat (when the session is destroyed)."""
    _trackers.pop(chat_id, None)


def get_tracker(chat_id: str) -> ChatUsageTracker | None:
    """Return the tracker for a chat, or None."""
    return _trackers.get(chat_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(obj: Any, attr: str) -> float:
    """Read a float attribute defensively, returning 0 if missing/None."""
    val = getattr(obj, attr, None)
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _extract_tool_summary(data: Any) -> str:
    for attr in ("summary", "description", "progress_message", "reason", "intention_summary"):
        value = getattr(data, attr, None)
        if isinstance(value, str) and value.strip():
            cleaned = " ".join(value.strip().split())
            return cleaned[:_MAX_TOOL_SUMMARY_CHARS]
    return ""


def _extract_tool_identity(data: Any) -> tuple[str, str, str]:
    tool_call_id = (
        getattr(data, "tool_call_id", None)
        or getattr(data, "parent_tool_call_id", None)
        or ""
    )
    tool_name = (
        getattr(data, "tool_name", None)
        or getattr(data, "mcp_tool_name", None)
        or getattr(data, "name", None)
        or getattr(data, "tool_title", None)
        or ""
    )
    server_name = (
        getattr(data, "mcp_server_name", None)
        or getattr(data, "server_name", None)
        or ""
    )
    return tool_call_id, tool_name, server_name


def _merge_tool_summary(existing: str, incoming: str) -> str:
    current = (existing or "").strip()
    candidate = (incoming or "").strip()
    if not candidate:
        return current
    if not current or len(candidate) > len(current):
        return candidate
    return current


_DOCS_SERVER_NAMES = {"blob_docs", "docs"}
_SEARCH_SERVER_NAMES = {"search_server", "search"}
_GEO_SERVER_NAMES = {"geo_server", "geo"}
_MAP_SERVER_NAMES = {"map_server", "map"}
_VECTOR_SERVER_NAMES = {"vector_server", "vector"}
_DOCUMENT_NAME_SERVERS = _DOCS_SERVER_NAMES | _SEARCH_SERVER_NAMES
_BLOB_NAME_KEYS = {"blob", "blob_name", "name", "source_blob"}
_SEARCH_BLOB_NAME_KEYS = {"blob", "blob_name", "source_blob"}


def _find_or_create_tool_call(
    turn: TurnUsage,
    *,
    tool_call_id: str,
    tool_name: str,
    server_name: str,
) -> ToolCall | None:
    if tool_call_id:
        for tool_call in reversed(turn.tool_calls):
            if tool_call.tool_call_id == tool_call_id:
                if tool_name and not tool_call.tool_name:
                    tool_call.tool_name = tool_name
                if server_name and not tool_call.server_name:
                    tool_call.server_name = server_name
                return tool_call

    for tool_call in reversed(turn.tool_calls):
        if tool_call.tool_name == tool_name and tool_call.server_name == server_name:
            return tool_call

    if not (tool_name or server_name):
        return None

    tool_call = ToolCall(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        server_name=server_name,
    )
    turn.tool_calls.append(tool_call)
    return tool_call


def _extract_document_names(server_name: str, tool_name: str, *values: Any) -> list[str]:
    normalized_server = (server_name or "").lower()
    normalized_tool = (tool_name or "").lower()
    if normalized_server not in _DOCUMENT_NAME_SERVERS:
        return []

    if normalized_server in _DOCS_SERVER_NAMES and normalized_tool == "list_documents":
        return []

    if normalized_server in _SEARCH_SERVER_NAMES and normalized_tool == "get_indexing_status":
        return []

    found: list[str] = []
    for value in values:
        _collect_document_names(
            value,
            found,
            server_name=normalized_server,
            tool_name=normalized_tool,
        )
    return _merge_unique_strings([], found)


def _build_tool_summary(
    server_name: str,
    tool_name: str,
    *,
    raw_summary: str = "",
    arguments: Any = None,
    result: Any = None,
    allow_raw_fallback: bool = True,
) -> str:
    derived_summary = _derive_tool_task_summary(
        server_name,
        tool_name,
        arguments=arguments,
        result=result,
    )
    if derived_summary:
        return derived_summary
    if allow_raw_fallback and raw_summary:
        return raw_summary
    return _build_generic_tool_summary(server_name, tool_name)


def _derive_tool_task_summary(
    server_name: str,
    tool_name: str,
    *,
    arguments: Any = None,
    result: Any = None,
) -> str:
    normalized_server = (server_name or "").lower()
    normalized_tool = (tool_name or "").lower()
    tool_label = _humanize_tool_name(tool_name)

    query_text = _quote_tool_text(_extract_tool_text(arguments, "query", "search"))
    name_text = _quote_tool_text(_extract_tool_text(arguments, "name", "blob_name"))
    search_text = _quote_tool_text(_extract_tool_text(arguments, "search"))
    layer_name = _quote_tool_text(
        _extract_tool_text(arguments, "layer_name")
        or _extract_tool_text(result, "layer_name")
    )
    distance_text = _format_distance(
        _extract_tool_number(arguments, "distance", "meter_radius", "radius")
    )
    document_names = _extract_document_names(server_name, tool_name, arguments, result)
    primary_document = _quote_tool_text(
        document_names[0] if document_names else (
            _extract_tool_text(result, "source_blob", "document_title", "name")
        )
    )
    section_title = _quote_tool_text(_extract_tool_text(result, "section_title"))
    point_count = _extract_geojson_feature_count(
        _find_tool_value(arguments, "points_geojson")
        or _find_tool_value(arguments, "geojson")
    )

    if normalized_server in _DOCS_SERVER_NAMES:
        if normalized_tool == "fetch_document":
            if name_text:
                return f"Hentet innhold fra {name_text}."
            if primary_document:
                return f"Hentet innhold fra {primary_document}."
            return "Hentet innhold fra et dokument."
        if normalized_tool == "list_documents":
            return "Sjekket hvilke dokumenter som var tilgjengelige."

    if normalized_server in _SEARCH_SERVER_NAMES:
        if normalized_tool == "search_documents":
            if query_text:
                return f"Sokte med fulltekstsok etter {query_text}."
            return "Sokte i dokumentene med fulltekstsok."
        if normalized_tool == "search_documents_fuzzy":
            if query_text:
                return f"Gjorde et bredt sok etter {query_text}."
            return "Gjorde et bredt sok i dokumentene."
        if normalized_tool == "search_documents_semantic":
            if query_text:
                return f"Lette etter dokumenter om {query_text} med semantisk sok."
            return "Lette etter lignende innhold med semantisk sok."
        if normalized_tool == "search_hybrid":
            if query_text:
                return f"Kombinerte flere sokemetoder for a finne informasjon om {query_text}."
            return "Kombinerte flere sokemetoder for a finne relevant informasjon."
        if normalized_tool == "get_search_result_chunk":
            if primary_document and section_title:
                return f"Hentet et relevant utdrag fra {primary_document}, under {section_title}."
            if primary_document:
                return f"Hentet et relevant utdrag fra {primary_document}."
            return "Hentet mer tekst fra et relevant soketreff."
        if normalized_tool == "get_indexing_status":
            return "Sjekket statusen for dokumentindekseringen."
        if normalized_tool == "index_document":
            blob_name = _quote_tool_text(_extract_tool_text(arguments, "blob_name", "name"))
            if blob_name:
                return f"Indekserte dokumentet {blob_name}."
            return "Indekserte et dokument for sok."
        if normalized_tool == "index_all_documents":
            return "Kjorte indeksering av alle dokumentene."

    if normalized_server in _GEO_SERVER_NAMES:
        if normalized_tool == "buffer_search":
            if distance_text:
                return f"Lette etter kulturmiljoer innen {distance_text} fra valgt punkt."
            return "Lette etter kulturmiljoer i naerheten av valgt punkt."
        if normalized_tool == "forward_geocode":
            if name_text:
                return f"Slo opp stedet {name_text}."
            return "Slo opp et stedsnavn."
        if normalized_tool == "reverse_geocode":
            return "Slo opp sted, kommune og fylke for koordinatene."
        if normalized_tool == "list_kommuner":
            if search_text:
                return f"Slo opp kommuner som matcher {search_text}."
            return "Hentet listen over kommuner."
        if normalized_tool == "list_vernetyper":
            return "Hentet tilgjengelige vernetyper."

    if normalized_server in _MAP_SERVER_NAMES:
        if normalized_tool == "draw_shape":
            if layer_name:
                return f"Tegnet resultatet pa kartet som laget {layer_name}."
            return "Tegnet resultatet pa kartet."
        if normalized_tool == "get_drawn_layers":
            return "Leste lagene som allerede ligger pa kartet."

    if normalized_server in _VECTOR_SERVER_NAMES:
        if normalized_tool == "buffer":
            if distance_text:
                return f"Lagde en buffersone pa {distance_text} rundt den valgte geometrien."
            return "Lagde en buffersone rundt den valgte geometrien."
        if normalized_tool == "intersection":
            return "Fant overlappen mellom to geografiske omrader."
        if normalized_tool == "envelope":
            return "Beregnet det omsluttende rektangelet for geometrien."
        if normalized_tool == "get_coordinates":
            return "Hentet koordinatene fra geometrien."
        if normalized_tool == "point_in_polygon":
            if point_count:
                return f"Sjekket hvilke av {point_count} punkter som ligger innenfor omradet."
            return "Sjekket hvilke punkter som ligger innenfor omradet."
        if normalized_tool == "get_verdensarv_sites":
            return "Hentet norske verdensarvsteder."
        if normalized_tool == "voronoi":
            if point_count:
                return f"Genererte Voronoi-omrader basert pa {point_count} objekter."
            return "Genererte Voronoi-omrader for de valgte objektene."

    if query_text:
        return f"Brukte {tool_label} for a finne informasjon om {query_text}."
    if name_text:
        return f"Brukte {tool_label} for {name_text}."
    if primary_document:
        return f"Brukte {tool_label} med {primary_document} som kilde."
    if distance_text:
        return f"Brukte {tool_label} med radius {distance_text}."
    return ""


def _build_generic_tool_summary(server_name: str, tool_name: str) -> str:
    normalized_tool = (tool_name or "").lower()
    tool_label = _humanize_tool_name(tool_name)
    server_label = _humanize_tool_name(server_name)

    if normalized_tool == "report_intent":
        return "Vurderte hvilke verktøy og datakilder som passet best til oppgaven."

    if normalized_tool == "powershell":
        return "Hentet eller kontrollerte lokal informasjon i arbeidsomradet."

    if tool_name and server_name:
        return f"Brukte {tool_label} via {server_label}."

    if tool_name:
        return f"Brukte {tool_label}."

    if server_name:
        return f"Brukte et verktoy via {server_label}."

    return ""


def _collect_document_names(
    value: Any,
    found: list[str],
    *,
    server_name: str,
    tool_name: str,
    key: str = "",
) -> None:
    value = _coerce_tool_value(value)

    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_document_names(
                child_value,
                found,
                server_name=server_name,
                tool_name=tool_name,
                key=str(child_key).lower(),
            )
        return

    if isinstance(value, list):
        for item in value:
            _collect_document_names(
                item,
                found,
                server_name=server_name,
                tool_name=tool_name,
                key=key,
            )
        return

    if not isinstance(value, str):
        return

    candidate = value.strip()
    if not candidate:
        return

    if _is_document_name_candidate(
        candidate,
        server_name=server_name,
        tool_name=tool_name,
        key=key,
    ):
        found.append(_normalize_document_name(candidate))


def _coerce_tool_value(value: Any) -> Any:
    if value is None:
        return None

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            return value

    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in "[{":
            if len(text) > _MAX_TOOL_VALUE_JSON_CHARS:
                return value
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value

    return value


def _find_tool_value(value: Any, *keys: str) -> Any:
    target_keys = {key.lower() for key in keys}
    value = _coerce_tool_value(value)

    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if str(child_key).lower() in target_keys:
                return child_value
        for child_value in value.values():
            found = _find_tool_value(child_value, *keys)
            if found is not None:
                return found
        return None

    if isinstance(value, list):
        for item in value:
            found = _find_tool_value(item, *keys)
            if found is not None:
                return found

    return None


def _extract_tool_text(value: Any, *keys: str) -> str:
    found = _find_tool_value(value, *keys)
    if found is None:
        return ""
    if not isinstance(found, str):
        return ""
    return " ".join(found.strip().split())


def _extract_tool_number(value: Any, *keys: str) -> float | None:
    found = _find_tool_value(value, *keys)
    if found is None:
        return None
    try:
        return float(found)
    except (TypeError, ValueError):
        return None


def _extract_geojson_feature_count(value: Any) -> int | None:
    value = _coerce_tool_value(value)
    if isinstance(value, dict):
        if value.get("type") == "FeatureCollection" and isinstance(value.get("features"), list):
            return len(value["features"])
        if value.get("type") == "Feature":
            return 1
    return None


def _quote_tool_text(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""
    if len(normalized) > 80:
        normalized = normalized[:77].rstrip() + "..."
    return f'"{normalized}"'


def _format_distance(value: float | None) -> str:
    if value is None or value <= 0:
        return ""
    if value >= 1000 and value % 1000 == 0:
        return f"{int(value / 1000)} km"
    if value >= 1000:
        return f"{value / 1000:.1f} km"
    if value.is_integer():
        return f"{int(value)} m"
    return f"{value:.0f} m"


def _humanize_tool_name(tool_name: str) -> str:
    normalized = (tool_name or "").strip().replace("_", " ").replace("-", " ")
    if not normalized:
        return "verktoyet"
    return normalized


def _is_document_name_candidate(
    candidate: str,
    *,
    server_name: str,
    tool_name: str,
    key: str,
) -> bool:
    normalized_server = (server_name or "").lower()
    normalized_key = key.lower()

    if normalized_server in _DOCS_SERVER_NAMES:
        return normalized_key in _BLOB_NAME_KEYS

    if normalized_server in _SEARCH_SERVER_NAMES:
        return normalized_key in _SEARCH_BLOB_NAME_KEYS

    return False


def _normalize_document_name(candidate: str) -> str:
    normalized = candidate.strip().replace("\\", "/")
    normalized = normalized.split("?", 1)[0].split("#", 1)[0]
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for value in [*existing, *incoming]:
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)

    return merged
