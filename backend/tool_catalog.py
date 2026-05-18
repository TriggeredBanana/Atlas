import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TOOL_CATALOG_PATH = Path(__file__).resolve().parents[1] / "shared" / "tool_catalog.json"
_MAX_TOOL_HINTS = 10
_DATABASE_PROMPT_LINES = (
    "DATABASE (server: database)",
    "  database-list_tables               - List approved tables and schemas available through this tool.",
    "  database-describe_table            - Columns, types, keys, and spatial metadata for one table.",
    "  database-get_schema_overview       - Full approved schema overview. Call once per session if needed.",
    "  database-explain_query             - Validate a read-only SELECT query before execution.",
    "  database-query_database            - Execute a read-only SELECT against approved schemas.",
)
_TOOL_EFFICIENCY_PROMPT_LINES = (
    "1. NEVER call the same tool twice with the same parameters in the same turn.",
    "2. Use vector-buffer_features instead of calling vector-buffer in a loop.",
    "3. Use map-draw_shapes_batch instead of calling map-draw_shape multiple times.",
    "4. Always pass session_id to every map-*, vector-*, and osm-* tool.",
    "5. Use vector-get_verdensarv_sites(latitude, longitude, limit) for nearest-site queries.",
    "6. Do not make exploratory tool calls if you already know the schema or available tools.",
    "7. If a tool call fails, report the error immediately and do not repeat it with identical parameters more than once.",
    "8. When a tool returns a geometry_ref, pass it directly to downstream map/vector tools instead of rebuilding geometry by hand.",
    "9. Use osm-osm_geocode or osm-osm_reverse_geocode for address and location lookups of Norwegian places. These return real OSM data — never guess addresses or coordinates.",
    "10. Use osm-osm_search_features for querying buildings, roads, amenities, and POIs by area name. Always use real data over fabricating location data.",
)


def _load_catalog() -> list[dict]:
    with _TOOL_CATALOG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    tools = raw.get("tools")
    if not isinstance(tools, list):
        raise ValueError("shared/tool_catalog.json must contain a 'tools' list")

    seen_ids: set[str] = set()
    normalized_tools: list[dict] = []
    for entry in tools:
        if not isinstance(entry, dict):
            raise ValueError("Tool catalog entries must be JSON objects")

        name = entry.get("name")
        category = entry.get("category")
        description = entry.get("desc")
        mcp_tool = entry.get("mcpTool")
        server = entry.get("server")

        if not all(isinstance(value, str) and value.strip() for value in (name, category, description, mcp_tool, server)):
            raise ValueError(f"Invalid tool catalog entry: {entry!r}")

        hidden = entry.get("hidden", False)
        if not isinstance(hidden, bool):
            raise ValueError(f"Tool catalog 'hidden' field must be a boolean: {entry!r}")

        if mcp_tool in seen_ids:
            raise ValueError(f"Duplicate MCP tool id in catalog: {mcp_tool}")

        seen_ids.add(mcp_tool)
        normalized_tools.append(entry)

    return normalized_tools


TOOL_CATALOG = _load_catalog()
ALLOWED_TOOL_HINTS = {tool["mcpTool"] for tool in TOOL_CATALOG}


def _build_tool_reference_prompt_section() -> str:
    grouped_tools: dict[str, list[dict]] = {}
    server_order: list[str] = []
    for tool in TOOL_CATALOG:
        server = tool["server"]
        if server not in grouped_tools:
            grouped_tools[server] = []
            server_order.append(server)
        grouped_tools[server].append(tool)

    sections = ["\n".join(_DATABASE_PROMPT_LINES)]
    for server in server_order:
        lines = [f"{server.upper()} (server: {server})"]
        for tool in grouped_tools[server]:
            lines.append(f"  {tool['mcpTool']:<36} - {tool['desc']}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


TOOL_REFERENCE_PROMPT_SECTION = _build_tool_reference_prompt_section()
TOOL_EFFICIENCY_PROMPT_SECTION = "\n".join(_TOOL_EFFICIENCY_PROMPT_LINES)


def normalize_tool_hints(tool_hints) -> list[str]:
    """
    Accept only known MCP tool identifiers from the shared catalog.

    This prevents prompt injection via raw client-supplied hint strings and
    avoids bloating the prompt with arbitrary or duplicated values.
    """
    if not isinstance(tool_hints, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for item in tool_hints:
        if len(normalized) >= _MAX_TOOL_HINTS:
            break
        if not isinstance(item, str):
            continue

        candidate = item.strip()
        if not candidate or candidate in seen or candidate not in ALLOWED_TOOL_HINTS:
            continue

        seen.add(candidate)
        normalized.append(candidate)

    dropped = len(tool_hints) - len(normalized)
    if dropped > 0:
        logger.info("Dropped %d invalid or duplicate tool hint(s)", dropped)

    return normalized
