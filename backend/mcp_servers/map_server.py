"""
Tools:
  - draw_shape:        Draw a GeoJSON shape on the map with a given layer name.
  - get_drawn_layers:  Retrieve all layers currently drawn on the user's map.
"""

import json
import logging
from fastmcp import FastMCP
from geometry_store import geometry_store

logger = logging.getLogger(__name__)

mcp = FastMCP("map_server")

_pending_shapes: dict[str, list] = {}
_session_map_context: dict[str, list] = {}


def get_and_clear_shapes(session_id: str) -> list:
    return _pending_shapes.pop(session_id, [])


def store_map_context(session_id: str, map_context: list) -> None:
    """Store the latest map context for a session so the MCP tool can access it."""
    _session_map_context[session_id] = map_context


def clear_map_context(session_id: str) -> None:
    """Remove stored map context when a session is discarded."""
    _session_map_context.pop(session_id, None)


def _resolve_geojson(geojson, geometry_ref: str, session_id: str):
    """Resolve geometry from a reference ID or use the provided geojson directly."""
    if geometry_ref and session_id:
        cached = geometry_store.retrieve(session_id, geometry_ref)
        if cached:
            return cached
    return geojson


@mcp.tool()
def draw_shape(layer_name: str, session_id: str = "", geojson: dict = None, geometry_ref: str = "") -> dict:
    """
    Draw a shape on the map.

    Accepts either a raw GeoJSON dict OR a geometry_ref returned by a previous
    tool call (e.g. get_verdensarv_sites, buffer, voronoi).  Using geometry_ref
    is strongly preferred — it avoids generating large coordinate payloads.

    Args:
        layer_name: The display name to give the layer on the map.
        session_id: The current session ID, used to route the shape to the correct user.
        geojson: A valid GeoJSON Feature or FeatureCollection (optional if geometry_ref is provided).
        geometry_ref: A geometry reference ID from a previous tool call (preferred over geojson).
    """
    logger.info("draw_shape called: layer_name=%s session_id=%s geometry_ref=%s", layer_name, session_id, geometry_ref)
    resolved = _resolve_geojson(geojson, geometry_ref, session_id)
    if not resolved:
        return {"status": "error", "message": "No geometry provided. Supply geojson or geometry_ref."}
    if session_id:
        _pending_shapes.setdefault(session_id, []).append({
            "layer_name": layer_name,
            "geojson": resolved,
        })
    return {"status": "ok", "layer_name": layer_name}


@mcp.tool()
def draw_shapes_batch(shapes: str, session_id: str = "") -> dict:
    """
    Draw MULTIPLE layers on the map in a single call.
    ALWAYS prefer this over calling draw_shape() multiple times.

    Args:
        shapes: A JSON array of objects, each with:
                - "layer_name" (str): display name for this layer
                - "geometry_ref" (str): geometry reference from a previous tool call (preferred)
                - "geojson" (dict, optional): raw GeoJSON if no geometry_ref
        session_id: The current session ID, used to route shapes to the correct user.
    """
    logger.info("draw_shapes_batch called: session_id=%s", session_id)
    try:
        items = json.loads(shapes) if isinstance(shapes, str) else shapes
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": "Invalid shapes JSON."}

    if not isinstance(items, list) or not items:
        return {"status": "error", "message": "shapes must be a non-empty JSON array."}

    drawn = []
    errors = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"Item {i}: not an object")
            continue
        name = item.get("layer_name", f"Layer {i + 1}")
        ref = item.get("geometry_ref", "")
        raw = item.get("geojson")
        resolved = _resolve_geojson(raw, ref, session_id)
        if not resolved:
            errors.append(f"Item {i} ({name}): no geometry")
            continue
        if session_id:
            _pending_shapes.setdefault(session_id, []).append({
                "layer_name": name,
                "geojson": resolved,
            })
        drawn.append(name)

    return {
        "status": "ok",
        "drawn_count": len(drawn),
        "drawn_layers": drawn,
        "errors": errors if errors else None,
    }


@mcp.tool()
def get_drawn_layers(session_id: str = "") -> str:
    """
    Retrieve all layers currently drawn on the user's map with exact coordinates.
    Use this tool when the user asks about shapes, markers, points, lines, or
    drawings on the map, or asks "what have I drawn?", "where are my markers?",
    or any question about the current map state.

    Returns a JSON array of layers, each with:
    - name: display name of the layer
    - shape: geometry type (Marker, Polygon, Rectangle, Circle, etc.)
    - summary: human-readable coordinate summary
    - geoJson: full GeoJSON geometry for precise analysis

    Args:
        session_id: the current session ID, used to retrieve the correct user's map state.
    """
    layers = _session_map_context.get(session_id, [])
    if not layers:
        return json.dumps({"status": "empty", "message": "Ingen lag er tegnet på kartet.", "layers": []})

    result = []
    for layer in layers:
        name = layer.get('name', 'Unnamed')
        shape = layer.get('shape', '?')
        geojson = layer.get('geoJson')
        summary = _build_layer_summary(shape, geojson)
        result.append({
            "name": name,
            "shape": shape,
            "summary": summary,
            "geoJson": geojson,
        })

    return json.dumps({"status": "ok", "layers": result}, ensure_ascii=False)


def _build_layer_summary(shape: str, geojson: dict | None) -> str:
    """Build a human-readable coordinate summary for a single layer."""
    if not geojson:
        return "Ingen geometridata"

    geometry = None
    properties = {}
    if geojson.get('type') == 'Feature':
        geometry = geojson.get('geometry')
        properties = geojson.get('properties', {})
    elif geojson.get('type') == 'FeatureCollection':
        features = geojson.get('features', [])
        if features:
            geometry = features[0].get('geometry')
            properties = features[0].get('properties', {})
    else:
        geometry = geojson

    if not geometry:
        return "Ingen geometridata"

    geom_type = geometry.get('type', '')
    coords = geometry.get('coordinates', [])
    parts = []

    if geom_type == 'Point':
        lon, lat = coords[0], coords[1]
        parts.append(f"Posisjon: {lon:.6f}°Ø, {lat:.6f}°N")

    elif geom_type == 'Polygon':
        ring = coords[0] if coords else []
        if ring:
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            center_lon = (min(lons) + max(lons)) / 2
            center_lat = (min(lats) + max(lats)) / 2
            parts.append(f"Senter: {center_lon:.6f}°Ø, {center_lat:.6f}°N")
            parts.append(f"Bounding box: ({min(lons):.6f}°Ø, {min(lats):.6f}°N) til ({max(lons):.6f}°Ø, {max(lats):.6f}°N)")
            if 'radiusMeters' in properties:
                parts.append(f"Radius: {properties['radiusMeters']} m")

    elif geom_type == 'LineString':
        if coords:
            parts.append(f"Start: {coords[0][0]:.6f}°Ø, {coords[0][1]:.6f}°N")
            parts.append(f"Slutt: {coords[-1][0]:.6f}°Ø, {coords[-1][1]:.6f}°N")
            parts.append(f"Antall punkter: {len(coords)}")

    elif geom_type == 'MultiPolygon':
        all_lons, all_lats = [], []
        for polygon in coords:
            for ring in polygon:
                for c in ring:
                    all_lons.append(c[0])
                    all_lats.append(c[1])
        if all_lons:
            center_lon = (min(all_lons) + max(all_lons)) / 2
            center_lat = (min(all_lats) + max(all_lats)) / 2
            parts.append(f"Senter: {center_lon:.6f}°Ø, {center_lat:.6f}°N")
            parts.append(f"Bounding box: ({min(all_lons):.6f}°Ø, {min(all_lats):.6f}°N) til ({max(all_lons):.6f}°Ø, {max(all_lats):.6f}°N)")
            parts.append(f"Antall polygoner: {len(coords)}")

    return "; ".join(parts) if parts else f"Geometritype: {geom_type}"


map_app = mcp.http_app(path="/mcp")
