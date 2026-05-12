"""
Tools:
  - draw_shape:        Draw a GeoJSON shape on the map with a given layer name.
  - get_drawn_layers:  Retrieve all layers currently drawn on the user's map.
"""

import json
import logging
from fastmcp import FastMCP

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


@mcp.tool()
def draw_shape(geojson: dict, layer_name: str, session_id: str = "") -> dict:
    """
    Draw a shape on the map.

    geojson: a valid GeoJSON Feature or FeatureCollection representing the shape(s) to draw.
    layer_name: the display name to give the layer on the map.
    session_id: the current session ID, used to route the shape to the correct user.
    """
    logger.info("draw_shape called: layer_name=%s session_id=%s", layer_name, session_id)
    if session_id:
        _pending_shapes.setdefault(session_id, []).append({
            "layer_name": layer_name,
            "geojson": geojson,
        })
    return {"status": "ok", "layer_name": layer_name}


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
