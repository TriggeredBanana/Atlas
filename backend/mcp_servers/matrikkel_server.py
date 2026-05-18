"""
MCP Server: Matrikkel / EiendomskartTeig

Compact cadastral tools over the imported MatrikkelenEiendomskartTeig PostGIS
dataset. Geometry is omitted by default; when geometry is requested with a
session_id it is stored in the backend geometry cache and returned as a
geometry_ref for downstream map tools.
"""

import json
import logging

from fastmcp import FastMCP

from config import MATR_EIENDOM_MAX_LIMIT, MATR_EIENDOM_MAX_RADIUS_METERS
from eiendomskartteig_repository import (
    find_teig_at_point,
    find_teiger_near_point,
    get_teig_boundary,
    search_property_by_identifier as repo_search_property_by_identifier,
    summarize_property_context_for_point as repo_summarize_property_context_for_point,
)
from geometry_store import geometry_store

logger = logging.getLogger(__name__)

mcp = FastMCP("matrikkel_server")


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _error(message: str) -> str:
    return _json({"error": message})


def _validate_lat_lon(latitude: float, longitude: float) -> str | None:
    if not -90 <= latitude <= 90:
        return "latitude must be between -90 and 90."
    if not -180 <= longitude <= 180:
        return "longitude must be between -180 and 180."
    return None


def _validate_radius(radius_meters: float) -> str | None:
    if radius_meters <= 0 or radius_meters > MATR_EIENDOM_MAX_RADIUS_METERS:
        return f"radius_meters must be greater than 0 and at most {MATR_EIENDOM_MAX_RADIUS_METERS}."
    return None


def _validate_limit(limit: int) -> str | None:
    if limit <= 0 or limit > MATR_EIENDOM_MAX_LIMIT:
        return f"limit must be between 1 and {MATR_EIENDOM_MAX_LIMIT}."
    return None


def _store_geometry_ref(payload: dict, *, include_geometry: bool, session_id: str) -> dict:
    feature_collection = payload.get("featureCollection")
    if include_geometry and feature_collection and session_id:
        payload["geometry_ref"] = geometry_store.store(session_id, feature_collection)
        payload["featureCollection"] = None
        payload.setdefault("notes", []).append(
            "Geometry stored as geometry_ref. Pass it to map-draw_shape or map-draw_shapes_batch to display it."
        )
    return payload


@mcp.tool(annotations={"readOnlyHint": True})
async def find_property_parcels_near_point(
    latitude: float,
    longitude: float,
    radius_meters: float = 250,
    limit: int = 5,
    include_geometry: bool = False,
    session_id: str = "",
) -> str:
    """
    Find property parcels/teiger near a WGS84 point.

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        radius_meters: Search radius in meters. Capped by backend config.
        limit: Maximum number of parcels to return.
        include_geometry: Return/cache GeoJSON only when explicitly needed.
        session_id: Current chat session ID for geometry caching.
    """
    validation_error = _validate_lat_lon(latitude, longitude) or _validate_radius(radius_meters) or _validate_limit(limit)
    if validation_error:
        return _error(validation_error)
    try:
        payload = await find_teiger_near_point(
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            limit=limit,
            include_geometry=include_geometry,
        )
        return _json(_store_geometry_ref(payload, include_geometry=include_geometry, session_id=session_id))
    except Exception:
        logger.exception("find_property_parcels_near_point failed")
        return _error("Matrikkel lookup failed.")


@mcp.tool(annotations={"readOnlyHint": True})
async def find_property_parcel_at_point(
    latitude: float,
    longitude: float,
    limit: int = 5,
    include_geometry: bool = False,
    session_id: str = "",
) -> str:
    """
    Find the teig that contains or intersects a WGS84 point.

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        limit: Maximum number of intersecting parcels to return.
        include_geometry: Return/cache GeoJSON only when explicitly needed.
        session_id: Current chat session ID for geometry caching.
    """
    validation_error = _validate_lat_lon(latitude, longitude) or _validate_limit(limit)
    if validation_error:
        return _error(validation_error)
    try:
        payload = await find_teig_at_point(
            latitude=latitude,
            longitude=longitude,
            limit=limit,
            include_geometry=include_geometry,
        )
        return _json(_store_geometry_ref(payload, include_geometry=include_geometry, session_id=session_id))
    except Exception:
        logger.exception("find_property_parcel_at_point failed")
        return _error("Matrikkel lookup failed.")


@mcp.tool(annotations={"readOnlyHint": True})
async def get_property_boundary(
    teig_id: int,
    id_type: str = "teigid",
    include_geometry: bool = False,
    session_id: str = "",
) -> str:
    """
    Get a property boundary derived from teig.omrade.

    Args:
        teig_id: teigid by default, or objid when id_type='objid'.
        id_type: Either 'teigid' or 'objid'.
        include_geometry: Return/cache GeoJSON boundary only when explicitly needed.
        session_id: Current chat session ID for geometry caching.
    """
    if teig_id <= 0:
        return _error("teig_id must be a positive integer.")
    if id_type not in {"teigid", "objid"}:
        return _error("id_type must be 'teigid' or 'objid'.")
    try:
        payload = await get_teig_boundary(
            teig_id=teig_id,
            id_type=id_type,
            include_geometry=include_geometry,
        )
        return _json(_store_geometry_ref(payload, include_geometry=include_geometry, session_id=session_id))
    except Exception:
        logger.exception("get_property_boundary failed")
        return _error("Matrikkel lookup failed.")


@mcp.tool(annotations={"readOnlyHint": True})
async def search_property_by_identifier(
    kommunenummer: str = "",
    gardsnummer: int | None = None,
    bruksnummer: int | None = None,
    festenummer: int | None = None,
    seksjonsnummer: int | None = None,
    matrikkelenhetid: int | None = None,
    limit: int = 10,
    include_geometry: bool = False,
    session_id: str = "",
) -> str:
    """
    Search property parcels by matrikkelenhet/property identifier.

    Args:
        kommunenummer: Four-digit municipality number.
        gardsnummer: Farm number.
        bruksnummer: Usage number.
        festenummer: Lease number, when relevant.
        seksjonsnummer: Section number, when relevant.
        matrikkelenhetid: Direct matrikkelenhet id, when known.
        limit: Maximum number of matches to return.
        include_geometry: Return/cache GeoJSON only when explicitly needed.
        session_id: Current chat session ID for geometry caching.
    """
    validation_error = _validate_limit(limit)
    if validation_error:
        return _error(validation_error)
    if matrikkelenhetid is None:
        kommunenummer = (kommunenummer or "").strip()
        if not (kommunenummer and gardsnummer is not None and bruksnummer is not None):
            return _error("Use either matrikkelenhetid or kommunenummer, gardsnummer and bruksnummer.")
    elif matrikkelenhetid <= 0:
        return _error("matrikkelenhetid must be a positive integer.")

    try:
        payload = await repo_search_property_by_identifier(
            kommunenummer=kommunenummer or None,
            gardsnummer=gardsnummer,
            bruksnummer=bruksnummer,
            festenummer=festenummer,
            seksjonsnummer=seksjonsnummer,
            matrikkelenhetid=matrikkelenhetid,
            limit=limit,
            include_geometry=include_geometry,
        )
        return _json(_store_geometry_ref(payload, include_geometry=include_geometry, session_id=session_id))
    except Exception:
        logger.exception("search_property_by_identifier failed")
        return _error("Matrikkel lookup failed.")


@mcp.tool(annotations={"readOnlyHint": True})
async def summarize_property_context_for_point(
    latitude: float,
    longitude: float,
    radius_meters: float = 250,
    limit: int = 3,
) -> str:
    """
    Return compact property context for a point without geometry.

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        radius_meters: Nearby search radius in meters.
        limit: Maximum number of nearby parcels to summarize.
    """
    validation_error = _validate_lat_lon(latitude, longitude) or _validate_radius(radius_meters) or _validate_limit(limit)
    if validation_error:
        return _error(validation_error)
    try:
        payload = await repo_summarize_property_context_for_point(
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            limit=limit,
        )
        return _json(payload)
    except Exception:
        logger.exception("summarize_property_context_for_point failed")
        return _error("Matrikkel lookup failed.")


matrikkel_app = mcp.http_app(path="/mcp")
