import logging
import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from config import MATR_EIENDOM_MAX_LIMIT, MATR_EIENDOM_MAX_RADIUS_METERS
from eiendomskartteig_repository import (
    find_teig_at_point,
    find_teiger_near_point,
    get_teig_boundary,
    search_property_by_identifier,
)

logger = logging.getLogger(__name__)

_KOMMUNENUMMER_RE = re.compile(r"^\d{4}$")


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def _bool_param(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_param(params: Any, name: str, *, default: float | None = None) -> float:
    raw = params.get(name)
    if raw is None:
        if default is None:
            raise ValueError(f"'{name}' is required.")
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a number.")


def _int_param(params: Any, name: str, *, default: int | None = None) -> int:
    raw = params.get(name)
    if raw is None or raw == "":
        if default is None:
            raise ValueError(f"'{name}' is required.")
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be an integer.")


def _optional_int_param(params: Any, *names: str) -> int | None:
    for name in names:
        raw = params.get(name)
        if raw is not None and raw != "":
            try:
                return int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"'{name}' must be an integer.")
    return None


def _validate_lat_lon(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        raise ValueError("'lat' must be between -90 and 90.")
    if not -180 <= lon <= 180:
        raise ValueError("'lon' must be between -180 and 180.")


def _validate_radius(radius: float) -> None:
    if radius <= 0 or radius > MATR_EIENDOM_MAX_RADIUS_METERS:
        raise ValueError(f"'radius' must be greater than 0 and at most {MATR_EIENDOM_MAX_RADIUS_METERS} meters.")


def _validate_limit(limit: int) -> None:
    if limit <= 0 or limit > MATR_EIENDOM_MAX_LIMIT:
        raise ValueError(f"'limit' must be between 1 and {MATR_EIENDOM_MAX_LIMIT}.")


def _query_lat_lon(request: Request) -> tuple[float, float]:
    params = request.query_params
    lat = _float_param(params, "lat")
    lon = _float_param(params, "lon")
    _validate_lat_lon(lat, lon)
    return lat, lon


async def teig_nearby(request: Request):
    try:
        params = request.query_params
        lat, lon = _query_lat_lon(request)
        radius = _float_param(params, "radius", default=None) if params.get("radius") is not None else _float_param(params, "radiusMeters", default=250)
        limit = _int_param(params, "limit", default=25)
        include_geometry = _bool_param(params.get("includeGeometry") or params.get("include_geometry"), False)
        _validate_radius(radius)
        _validate_limit(limit)
        payload = await find_teiger_near_point(
            latitude=lat,
            longitude=lon,
            radius_meters=radius,
            limit=limit,
            include_geometry=include_geometry,
        )
        return JSONResponse(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Matrikkel nearby lookup failed")
        return _error("Matrikkel lookup failed.", 500)


async def teig_at_point(request: Request):
    try:
        params = request.query_params
        lat, lon = _query_lat_lon(request)
        limit = _int_param(params, "limit", default=5)
        include_geometry = _bool_param(params.get("includeGeometry") or params.get("include_geometry"), True)
        _validate_limit(limit)
        payload = await find_teig_at_point(
            latitude=lat,
            longitude=lon,
            limit=limit,
            include_geometry=include_geometry,
        )
        return JSONResponse(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Matrikkel at-point lookup failed")
        return _error("Matrikkel lookup failed.", 500)


async def teig_boundary(request: Request):
    try:
        raw_id = request.path_params.get("teig_id")
        try:
            teig_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValueError("'teig_id' must be an integer.")
        if teig_id <= 0:
            raise ValueError("'teig_id' must be a positive integer.")

        params = request.query_params
        id_type = (params.get("idType") or params.get("id_type") or "teigid").strip()
        if id_type not in {"teigid", "objid"}:
            raise ValueError("'idType' must be 'teigid' or 'objid'.")
        include_geometry = _bool_param(params.get("includeGeometry") or params.get("include_geometry"), True)
        payload = await get_teig_boundary(
            teig_id=teig_id,
            id_type=id_type,
            include_geometry=include_geometry,
        )
        return JSONResponse(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Matrikkel boundary lookup failed")
        return _error("Matrikkel lookup failed.", 500)


async def property_search(request: Request):
    try:
        params = request.query_params
        matrikkelenhetid = _optional_int_param(params, "matrikkelenhetid", "matrikkelenhetId")
        kommunenummer = (params.get("kommunenummer") or "").strip() or None
        gardsnummer = _optional_int_param(params, "gardsnummer", "gaardsnummer")
        bruksnummer = _optional_int_param(params, "bruksnummer")
        festenummer = _optional_int_param(params, "festenummer")
        seksjonsnummer = _optional_int_param(params, "seksjonsnummer")
        limit = _int_param(params, "limit", default=25)
        include_geometry = _bool_param(params.get("includeGeometry") or params.get("include_geometry"), False)

        if matrikkelenhetid is not None:
            if matrikkelenhetid <= 0:
                raise ValueError("'matrikkelenhetid' must be a positive integer.")
        else:
            if not kommunenummer or gardsnummer is None or bruksnummer is None:
                raise ValueError("Use either 'matrikkelenhetid' or 'kommunenummer', 'gardsnummer' and 'bruksnummer'.")
            if not _KOMMUNENUMMER_RE.fullmatch(kommunenummer):
                raise ValueError("'kommunenummer' must be four digits.")
            if gardsnummer < 0 or bruksnummer < 0:
                raise ValueError("'gardsnummer' and 'bruksnummer' must be non-negative integers.")
        for name, value in (("festenummer", festenummer), ("seksjonsnummer", seksjonsnummer)):
            if value is not None and value < 0:
                raise ValueError(f"'{name}' must be a non-negative integer.")
        _validate_limit(limit)

        payload = await search_property_by_identifier(
            kommunenummer=kommunenummer,
            gardsnummer=gardsnummer,
            bruksnummer=bruksnummer,
            festenummer=festenummer,
            seksjonsnummer=seksjonsnummer,
            matrikkelenhetid=matrikkelenhetid,
            limit=limit,
            include_geometry=include_geometry,
        )
        return JSONResponse(payload)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Matrikkel property search failed")
        return _error("Matrikkel lookup failed.", 500)
