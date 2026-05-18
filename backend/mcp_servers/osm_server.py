"""
OSM Geodata MCP Server — Nominatim + Overpass API integration.

Tools:
  - osm_geocode:              Forward geocode (name/address → coordinates + polygon) via Nominatim.
  - osm_reverse_geocode:      Reverse geocode (coordinates → structured address) via Nominatim.
  - osm_lookup:               Look up specific OSM objects by node/way/relation ID.
  - osm_search_features:      Query buildings, roads, POIs by tag within a named area (Overpass).
  - osm_search_features_bbox: Query features within a bounding box (Overpass).
"""

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from fastmcp import FastMCP
from geometry_store import geometry_store

logger = logging.getLogger(__name__)

mcp = FastMCP("osm_server")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_USER_AGENT = os.getenv("OSM_USER_AGENT", "Atlas-GIS/1.0")
_OSM_RESULT_LIMIT = int(os.getenv("OSM_RESULT_LIMIT", "200"))

_NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_OVERPASS_PRIMARY = "https://overpass-api.de/api/interpreter"
_OVERPASS_FALLBACK = "https://overpass.private.coffee/api/interpreter"

# Overpass query timeout in seconds (server-side).
_OVERPASS_TIMEOUT = 25

# ---------------------------------------------------------------------------
# Nominatim rate limiter (1 request per second)
# ---------------------------------------------------------------------------

_nominatim_lock = asyncio.Lock()
_nominatim_last_request: float = 0.0


async def _nominatim_throttle():
    """Ensure at least 1 second between Nominatim requests."""
    global _nominatim_last_request
    async with _nominatim_lock:
        now = time.monotonic()
        elapsed = now - _nominatim_last_request
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _nominatim_last_request = time.monotonic()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_json_sync(url: str, *, headers: dict | None = None) -> dict | list | None:
    """Fetch JSON from a URL (synchronous). Returns None on failure."""
    hdrs = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.error("Nominatim request failed for %s: %s", url, exc)
        return None


def _post_overpass_sync(query: str, *, endpoint: str = _OVERPASS_PRIMARY) -> dict | None:
    """POST an Overpass QL query and return the parsed JSON response."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    hdrs = {"User-Agent": _USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        req = urllib.request.Request(endpoint, data=data, headers=hdrs)
        with urllib.request.urlopen(req, timeout=_OVERPASS_TIMEOUT + 10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warning("Overpass request failed on %s: %s", endpoint, exc)
        return None


async def _fetch_nominatim(url: str) -> dict | list | None:
    """Rate-limited async wrapper around Nominatim GET."""
    await _nominatim_throttle()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_json_sync, url)


async def _query_overpass(overpass_ql: str) -> dict | None:
    """Run an Overpass query with automatic fallback to secondary endpoint."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _post_overpass_sync, overpass_ql)
    if result is not None:
        return result
    # Fallback to secondary endpoint
    logger.info("Falling back to secondary Overpass endpoint")
    return await loop.run_in_executor(
        None, lambda: _post_overpass_sync(overpass_ql, endpoint=_OVERPASS_FALLBACK)
    )


# ---------------------------------------------------------------------------
# Overpass → GeoJSON conversion
# ---------------------------------------------------------------------------

def _overpass_to_geojson(overpass_json: dict) -> dict:
    """Convert Overpass JSON response to GeoJSON FeatureCollection."""
    try:
        import osm2geojson
        return osm2geojson.json2geojson(overpass_json)
    except ImportError:
        logger.error("osm2geojson not installed — cannot convert Overpass response")
        return {"type": "FeatureCollection", "features": []}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _extract_centroid(geometry: dict) -> tuple[float, float] | None:
    """
    Extract a representative (latitude, longitude) from a GeoJSON geometry.

    For Point: return the point itself.
    For Polygon/MultiPolygon/LineString: compute the centroid from the
    bounding box of all coordinates.

    Returns (latitude, longitude) or None if geometry is empty/invalid.
    """
    if not geometry:
        return None

    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates")
    if not coords:
        return None

    if geom_type == "Point":
        # coordinates = [lon, lat]
        return (coords[1], coords[0])

    # For all other types, collect all coordinate pairs and compute bbox centroid
    all_points: list[tuple[float, float]] = []

    def _collect(obj):
        if isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], (int, float)):
                all_points.append((obj[0], obj[1]))  # (lon, lat)
            else:
                for item in obj:
                    _collect(item)

    _collect(coords)

    if not all_points:
        return None

    lons = [p[0] for p in all_points]
    lats = [p[1] for p in all_points]
    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2
    return (center_lat, center_lon)


def _extract_centroid_from_bbox(bbox: list) -> tuple[float, float] | None:
    """Extract centroid from a Nominatim bbox [min_lon, min_lat, max_lon, max_lat]."""
    if bbox and len(bbox) == 4:
        center_lon = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2
        return (center_lat, center_lon)
    return None


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _limit_features(geojson: dict, limit: int) -> dict:
    """Truncate a FeatureCollection to *limit* features."""
    if geojson.get("type") != "FeatureCollection":
        return geojson
    features = geojson.get("features", [])
    truncated = len(features) > limit
    geojson = {**geojson, "features": features[:limit]}
    if truncated:
        geojson["_truncated"] = True
        geojson["_total_available"] = len(features)
    return geojson


def _feature_summary(geojson: dict) -> dict:
    """Build a lightweight summary of a FeatureCollection for the LLM."""
    features = geojson.get("features", [])
    type_counts: dict[str, int] = {}
    sample_names: list[str] = []
    for f in features[:20]:
        props = f.get("properties", {})
        geom = f.get("geometry", {})
        gtype = geom.get("type", "unknown")
        type_counts[gtype] = type_counts.get(gtype, 0) + 1
        name = (
            props.get("tags", {}).get("name", "")
            if isinstance(props.get("tags"), dict)
            else props.get("name", "")
        )
        if name and len(sample_names) < 10:
            sample_names.append(name)
    summary: dict = {
        "feature_count": len(features),
        "geometry_types": type_counts,
    }
    if sample_names:
        summary["sample_names"] = sample_names
    if geojson.get("_truncated"):
        summary["truncated"] = True
        summary["total_available"] = geojson.get("_total_available")
    return summary


def _parse_nominatim_feature(feature: dict, session_id: str) -> dict:
    """
    Parse a single Nominatim GeoJSON feature into a result dict that includes:
    - Exact latitude/longitude (from geometry)
    - A per-feature geometry_ref (so downstream tools can target it individually)
    - All useful metadata (address, display_name, osm_type, etc.)
    """
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    bbox = feature.get("bbox")
    address = props.get("address", {})

    # Extract exact coordinates from the geometry
    centroid = _extract_centroid(geom)
    if centroid is None and bbox:
        centroid = _extract_centroid_from_bbox(bbox)

    latitude = centroid[0] if centroid else None
    longitude = centroid[1] if centroid else None

    # Store this individual feature as its own geometry_ref
    geometry_ref = ""
    if session_id and geom:
        geometry_ref = geometry_store.store(session_id, feature)

    result: dict = {
        "display_name": props.get("display_name", ""),
        "latitude": latitude,
        "longitude": longitude,
        "osm_type": props.get("osm_type", ""),
        "osm_id": props.get("osm_id", ""),
        "category": props.get("category", ""),
        "type": props.get("type", ""),
        "geometry_type": geom.get("type", ""),
        "address": {
            "road": address.get("road", ""),
            "house_number": address.get("house_number", ""),
            "postcode": address.get("postcode", ""),
            "city": address.get("city", address.get("town", address.get("village", ""))),
            "municipality": address.get("municipality", address.get("county", "")),
            "county": address.get("county", ""),
            "country": address.get("country", ""),
        },
    }
    if geometry_ref:
        result["geometry_ref"] = geometry_ref
    return result


# ---------------------------------------------------------------------------
# Tool: osm_geocode
# ---------------------------------------------------------------------------

@mcp.tool()
async def osm_geocode(query: str, session_id: str = "", limit: int = 5) -> str:
    """
    Geokod et stedsnavn eller adresse via OpenStreetMap Nominatim.
    Returnerer eksakte koordinater, adresseinformasjon og geometri for treff i Norge.
    Hvert resultat har sin egen geometry_ref som kan brukes direkte med
    vector-buffer og map-draw_shape.

    Args:
        query:      Stedsnavn, adresse eller søkestreng, f.eks. "Bryggen Bergen",
                    "Karl Johans gate 1, Oslo", "Tromsø kommune".
        session_id: Gjeldende session-ID for geometry_ref-lagring.
        limit:      Maks antall treff (standard 5).
    """
    if not query or not query.strip():
        return json.dumps({"error": "Tomt søkeord."})

    limit = max(1, min(limit, 10))
    params = urllib.parse.urlencode({
        "q": query.strip(),
        "countrycodes": "no",
        "format": "geojson",
        "polygon_geojson": 1,
        "addressdetails": 1,
        "limit": limit,
    })
    url = f"{_NOMINATIM_BASE}/search?{params}"
    data = await _fetch_nominatim(url)

    if data is None:
        return json.dumps({"error": "Nominatim-forespørsel feilet. Prøv igjen senere."})

    features = data.get("features", [])
    if not features:
        return json.dumps({
            "status": "no_results",
            "message": f"Ingen treff for '{query.strip()}' i Norge.",
        })

    # Parse each feature individually — each gets its own geometry_ref
    results = [_parse_nominatim_feature(f, session_id) for f in features]

    response = {
        "status": "ok",
        "query": query.strip(),
        "count": len(results),
        "results": results,
    }
    return json.dumps(response, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: osm_reverse_geocode
# ---------------------------------------------------------------------------

@mcp.tool()
async def osm_reverse_geocode(latitude: float, longitude: float, session_id: str = "") -> str:
    """
    Slå opp adresse og stedsinformasjon fra koordinater via OpenStreetMap Nominatim.
    Returnerer strukturert norsk adresse, eksakte koordinater for treffet, og geometri.

    Args:
        latitude:   Breddegrad (WGS84), f.eks. 59.9139.
        longitude:  Lengdegrad (WGS84), f.eks. 10.7522.
        session_id: Gjeldende session-ID for geometry_ref-lagring.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return json.dumps({"error": "Ugyldige koordinater."})

    params = urllib.parse.urlencode({
        "lat": latitude,
        "lon": longitude,
        "format": "geojson",
        "polygon_geojson": 1,
        "addressdetails": 1,
    })
    url = f"{_NOMINATIM_BASE}/reverse?{params}"
    data = await _fetch_nominatim(url)

    if data is None:
        return json.dumps({"error": "Nominatim-forespørsel feilet. Prøv igjen senere."})

    features = data.get("features", [])
    if not features:
        return json.dumps({
            "status": "no_results",
            "message": f"Ingen adresseinformasjon for ({latitude}, {longitude}).",
            "input_coordinates": {"latitude": latitude, "longitude": longitude},
        })

    # Parse the single result feature
    result = _parse_nominatim_feature(features[0], session_id)

    response = {
        "status": "ok",
        "input_coordinates": {"latitude": latitude, "longitude": longitude},
    }
    response.update(result)
    return json.dumps(response, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: osm_lookup
# ---------------------------------------------------------------------------

@mcp.tool()
async def osm_lookup(osm_ids: str, session_id: str = "") -> str:
    """
    Slå opp spesifikke OSM-objekter via node/way/relation-ID.
    Returnerer eksakte koordinater og geometri for hvert objekt.
    Hvert resultat har sin egen geometry_ref.

    Args:
        osm_ids:    Kommaseparert liste med prefikset ID-er, f.eks.
                    "R2978650,W12345678,N987654".
                    Prefiks: N=node, W=way, R=relation.
        session_id: Gjeldende session-ID for geometry_ref-lagring.
    """
    if not osm_ids or not osm_ids.strip():
        return json.dumps({"error": "Ingen OSM-ID-er oppgitt."})

    params = urllib.parse.urlencode({
        "osm_ids": osm_ids.strip(),
        "format": "geojson",
        "polygon_geojson": 1,
        "addressdetails": 1,
    })
    url = f"{_NOMINATIM_BASE}/lookup?{params}"
    data = await _fetch_nominatim(url)

    if data is None:
        return json.dumps({"error": "Nominatim-forespørsel feilet. Prøv igjen senere."})

    features = data.get("features", [])
    if not features:
        return json.dumps({
            "status": "no_results",
            "message": f"Ingen treff for OSM-ID-er: {osm_ids.strip()}",
        })

    # Parse each feature individually — each gets its own geometry_ref
    results = [_parse_nominatim_feature(f, session_id) for f in features]

    response = {
        "status": "ok",
        "count": len(results),
        "results": results,
    }
    return json.dumps(response, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: osm_search_features
# ---------------------------------------------------------------------------

@mcp.tool()
async def osm_search_features(
    place: str,
    tag_key: str,
    tag_value: str = "",
    session_id: str = "",
    limit: int = 200,
) -> str:
    """
    Søk etter bygninger, veier, fasiliteter og POI-er i et navngitt område via Overpass API.
    Bruk dette verktøyet for å hente faktiske OSM-data om bygninger, veier, butikker,
    skoler, sykehus og andre fasiliteter i et bestemt norsk område.

    Args:
        place:      Navn på området, f.eks. "Trondheim", "Nordland", "Kristiansand".
        tag_key:    OSM-taggnøkkel, f.eks. "building", "amenity", "highway", "shop",
                    "leisure", "tourism".
        tag_value:  OSM-taggverdi (valgfritt). F.eks. "school", "hospital", "residential".
                    Tom streng = alle verdier for angitt nøkkel.
        session_id: Gjeldende session-ID for geometry_ref-lagring.
        limit:      Maks antall features å returnere (standard 200).
    """
    if not place or not place.strip():
        return json.dumps({"error": "Område (place) er påkrevd."})
    if not tag_key or not tag_key.strip():
        return json.dumps({"error": "Tag-nøkkel (tag_key) er påkrevd."})

    limit = max(1, min(limit, _OSM_RESULT_LIMIT))
    place_clean = place.strip().replace('"', '\\"')
    tag_key_clean = tag_key.strip()
    tag_filter = f'"{tag_key_clean}"="{tag_value.strip()}"' if tag_value.strip() else f'"{tag_key_clean}"'

    overpass_ql = f"""[out:json][timeout:{_OVERPASS_TIMEOUT}];
area[name="{place_clean}"]["boundary"="administrative"]->.a;
(
  node[{tag_filter}](area.a);
  way[{tag_filter}](area.a);
  relation[{tag_filter}](area.a);
);
out geom;"""

    result = await _query_overpass(overpass_ql)
    if result is None:
        return json.dumps({"error": "Overpass-forespørsel feilet. Prøv igjen senere."})

    geojson = _overpass_to_geojson(result)
    geojson = _limit_features(geojson, limit)
    summary = _feature_summary(geojson)

    geometry_ref = ""
    if session_id and geojson.get("features"):
        geometry_ref = geometry_store.store(session_id, geojson)

    response = {
        "status": "ok",
        "query": {"place": place.strip(), "tag_key": tag_key_clean, "tag_value": tag_value.strip()},
        "summary": summary,
    }
    if geometry_ref:
        response["geometry_ref"] = geometry_ref
        response["message"] = (
            f"Fant {summary['feature_count']} OSM-objekter. "
            f"Bruk geometry_ref '{geometry_ref}' med map-draw_shape for å vise på kartet."
        )
    else:
        response["message"] = "Ingen treff funnet for angitt søk."
    return json.dumps(response, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: osm_search_features_bbox
# ---------------------------------------------------------------------------

@mcp.tool()
async def osm_search_features_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    tag_key: str,
    tag_value: str = "",
    session_id: str = "",
    limit: int = 200,
) -> str:
    """
    Søk etter OSM-objekter innenfor et kartutsnitt (bounding box) via Overpass API.
    Bruk dette verktøyet når du allerede har koordinater for et kartutsnitt og vil
    finne bygninger, veier eller andre features innenfor det.

    Args:
        south:      Sørlig breddegrad for bounding box.
        west:       Vestlig lengdegrad for bounding box.
        north:      Nordlig breddegrad for bounding box.
        east:       Østlig lengdegrad for bounding box.
        tag_key:    OSM-taggnøkkel, f.eks. "building", "amenity", "highway".
        tag_value:  OSM-taggverdi (valgfritt). Tom streng = alle verdier.
        session_id: Gjeldende session-ID for geometry_ref-lagring.
        limit:      Maks antall features å returnere (standard 200).
    """
    # Validate bounding box
    for coord_name, coord_val in [("south", south), ("north", north)]:
        if not (-90 <= coord_val <= 90):
            return json.dumps({"error": f"Ugyldig breddegrad for {coord_name}: {coord_val}"})
    for coord_name, coord_val in [("west", west), ("east", east)]:
        if not (-180 <= coord_val <= 180):
            return json.dumps({"error": f"Ugyldig lengdegrad for {coord_name}: {coord_val}"})
    if south >= north:
        return json.dumps({"error": "south må være mindre enn north."})

    if not tag_key or not tag_key.strip():
        return json.dumps({"error": "Tag-nøkkel (tag_key) er påkrevd."})

    limit = max(1, min(limit, _OSM_RESULT_LIMIT))
    tag_key_clean = tag_key.strip()
    tag_filter = f'"{tag_key_clean}"="{tag_value.strip()}"' if tag_value.strip() else f'"{tag_key_clean}"'
    bbox = f"{south},{west},{north},{east}"

    overpass_ql = f"""[out:json][timeout:{_OVERPASS_TIMEOUT}];
(
  node[{tag_filter}]({bbox});
  way[{tag_filter}]({bbox});
  relation[{tag_filter}]({bbox});
);
out geom;"""

    result = await _query_overpass(overpass_ql)
    if result is None:
        return json.dumps({"error": "Overpass-forespørsel feilet. Prøv igjen senere."})

    geojson = _overpass_to_geojson(result)
    geojson = _limit_features(geojson, limit)
    summary = _feature_summary(geojson)

    geometry_ref = ""
    if session_id and geojson.get("features"):
        geometry_ref = geometry_store.store(session_id, geojson)

    response = {
        "status": "ok",
        "query": {
            "bbox": {"south": south, "west": west, "north": north, "east": east},
            "tag_key": tag_key_clean,
            "tag_value": tag_value.strip(),
        },
        "summary": summary,
    }
    if geometry_ref:
        response["geometry_ref"] = geometry_ref
        response["message"] = (
            f"Fant {summary['feature_count']} OSM-objekter i angitt kartutsnitt. "
            f"Bruk geometry_ref '{geometry_ref}' med map-draw_shape for å vise på kartet."
        )
    else:
        response["message"] = "Ingen treff funnet innenfor angitt kartutsnitt."
    return json.dumps(response, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Expose as ASGI app for mounting in server.py
# ---------------------------------------------------------------------------

osm_app = mcp.http_app(path="/mcp")
