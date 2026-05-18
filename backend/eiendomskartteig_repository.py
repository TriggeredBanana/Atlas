import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from config import (
    MATR_ADRESSE_SCHEMA,
    MATR_BYGNING_SCHEMA,
    MATR_EIENDOM_MAX_LIMIT,
    MATR_EIENDOM_QUERY_TIMEOUT_MS,
    MATR_EIENDOM_SCHEMA,
)
from db import get_connection

SOURCE_LABEL = "MatrikkelenEiendomskartTeig / PostGIS"
DATASET_SRID = 25833


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


_EIENDOM = _quote_ident(MATR_EIENDOM_SCHEMA)
_ADRESSE = _quote_ident(MATR_ADRESSE_SCHEMA)
_BYGNING = _quote_ident(MATR_BYGNING_SCHEMA)

_TEIG = f"{_EIENDOM}.teig"
_MATRIKKELENHET = f"{_EIENDOM}.matrikkelenhet"
_BRUKSENHET = f"{_BYGNING}.bruksenhet"
_BYGNING_TABLE = f"{_BYGNING}.bygning"


async def _read_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        async with conn.transaction(force_rollback=True):
            await conn.execute("SET TRANSACTION READ ONLY")
            async with conn.cursor() as cur:
                await cur.execute(f"SET LOCAL statement_timeout = '{MATR_EIENDOM_QUERY_TIMEOUT_MS}ms'")
                await cur.execute(f"SET LOCAL lock_timeout = '{MATR_EIENDOM_QUERY_TIMEOUT_MS}ms'")
                await cur.execute(sql, params)
                if cur.description is None:
                    return []
                return await cur.fetchall()


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(val) for key, val in value.items()}
    return value


def _coerce_json(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return _json_value(value)


def _limit(value: int, default: int = 25) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, MATR_EIENDOM_MAX_LIMIT))


def _geometry_select(include_geometry: bool, expression: str = "t.omrade") -> str:
    if not include_geometry:
        return "NULL::text AS geometry"
    return f"ST_AsGeoJSON(ST_Transform({expression}, 4326), 6) AS geometry"


def _compact_teig_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "objid": row.get("objid"),
        "teigid": row.get("teigid"),
        "uuidteig": row.get("uuidteig"),
        "kommunenummer": row.get("kommunenummer"),
        "kommunenavn": row.get("kommunenavn"),
        "matrikkelnummertekst": row.get("matrikkelnummertekst"),
        "areaM2": _json_value(row.get("area_m2")),
        "accuracyClass": row.get("accuracy_class"),
        "disputed": row.get("disputed"),
        "multipleMatrikkelenheter": row.get("multiple_matrikkelenheter"),
        "unregisteredLandCoownership": row.get("unregistered_land_coownership"),
        "distanceMeters": _json_value(row.get("distance_m")),
        "containsPoint": row.get("contains_point"),
        "matrikkelenheter": _coerce_json(row.get("matrikkelenheter")),
        "geometry": None,
    }


def _feature_collection(rows: list[dict[str, Any]], *, geometry_kind: str = "teig") -> dict[str, Any] | None:
    features = []
    for row in rows:
        geometry_raw = row.get("geometry")
        if not geometry_raw:
            continue
        geometry = json.loads(geometry_raw) if isinstance(geometry_raw, str) else geometry_raw
        properties = _compact_teig_row(row)
        properties.pop("geometry", None)
        properties["geometrySource"] = geometry_kind
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties,
        })
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _payload(query: dict[str, Any], rows: list[dict[str, Any]], *, include_geometry: bool, notes: list[str] | None = None, geometry_kind: str = "teig") -> dict[str, Any]:
    result_notes = list(notes or [])
    if not include_geometry:
        result_notes.append("Geometry omitted unless explicitly requested.")
    result_notes.append(f"Results are limited to {query.get('limit', len(rows))} rows.")
    return {
        "source": SOURCE_LABEL,
        "schema": MATR_EIENDOM_SCHEMA,
        "srid": DATASET_SRID,
        "query": _json_value(query),
        "count": len(rows),
        "results": [_compact_teig_row(row) for row in rows],
        "featureCollection": _feature_collection(rows, geometry_kind=geometry_kind) if include_geometry else None,
        "notes": result_notes,
    }


async def get_dataset_metadata() -> dict[str, Any]:
    rows = await _read_rows(
        """
        SELECT f_table_name, f_geometry_column, srid, type
        FROM geometry_columns
        WHERE f_table_schema = %s
          AND f_table_name IN ('teig', 'eiendomsgrense', 'teiggrensepunkt', 'hjelpelinje')
        ORDER BY f_table_name, f_geometry_column
        """,
        (MATR_EIENDOM_SCHEMA,),
    )
    return {
        "source": SOURCE_LABEL,
        "schema": MATR_EIENDOM_SCHEMA,
        "geometryColumns": [_json_value(row) for row in rows],
    }


async def find_teiger_near_point(
    *,
    latitude: float,
    longitude: float,
    radius_meters: float,
    limit: int = 25,
    include_geometry: bool = False,
) -> dict[str, Any]:
    limit = _limit(limit)
    geom_select = _geometry_select(include_geometry)
    rows = await _read_rows(
        f"""
        WITH point_input AS (
            SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), {DATASET_SRID}) AS geom
        )
        SELECT
            t.objid,
            t.teigid,
            t.uuidteig,
            t.kommunenummer,
            t.kommunenavn,
            t.matrikkelnummertekst,
            t.lagretberegnetareal AS area_m2,
            t.noyaktighetsklasseteig AS accuracy_class,
            t.tvist AS disputed,
            t.teigmedflerematrikkelenheter AS multiple_matrikkelenheter,
            t.uregistrertjordsameie AS unregistered_land_coownership,
            ST_Distance(t.omrade, point_input.geom) AS distance_m,
            NULL::boolean AS contains_point,
            COALESCE(m_units.matrikkelenheter, '[]'::jsonb) AS matrikkelenheter,
            {geom_select}
        FROM {_TEIG} t
        CROSS JOIN point_input
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'matrikkelenhetid', m.matrikkelenhetid,
                    'kommunenummer', m.kommunenummer,
                    'gardsnummer', m.gardsnummer,
                    'bruksnummer', m.bruksnummer,
                    'festenummer', m.festenummer,
                    'seksjonsnummer', m.seksjonsnummer,
                    'bruksnavn', m.bruksnavn,
                    'matrikkelenhetstype', m.matrikkelenhetstype,
                    'uuidmatrikkelenhet', m.uuidmatrikkelenhet
                )
                ORDER BY m.matrikkelenhetid
            ) AS matrikkelenheter
            FROM (
                SELECT *
                FROM {_MATRIKKELENHET}
                WHERE teig_fk = t.teigid
                ORDER BY matrikkelenhetid
                LIMIT 10
            ) m
        ) m_units ON TRUE
        WHERE t.omrade && ST_Expand(point_input.geom, %s)
          AND ST_DWithin(t.omrade, point_input.geom, %s)
        ORDER BY ST_Distance(t.omrade, point_input.geom), t.teigid
        LIMIT %s
        """,
        (longitude, latitude, radius_meters, radius_meters, limit),
    )
    return _payload(
        {
            "lat": latitude,
            "lon": longitude,
            "radiusMeters": radius_meters,
            "limit": limit,
            "includeGeometry": include_geometry,
        },
        rows,
        include_geometry=include_geometry,
    )


async def find_teig_at_point(
    *,
    latitude: float,
    longitude: float,
    limit: int = 5,
    include_geometry: bool = True,
) -> dict[str, Any]:
    limit = _limit(limit, default=5)
    geom_select = _geometry_select(include_geometry)
    rows = await _read_rows(
        f"""
        WITH point_input AS (
            SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), {DATASET_SRID}) AS geom
        )
        SELECT
            t.objid,
            t.teigid,
            t.uuidteig,
            t.kommunenummer,
            t.kommunenavn,
            t.matrikkelnummertekst,
            t.lagretberegnetareal AS area_m2,
            t.noyaktighetsklasseteig AS accuracy_class,
            t.tvist AS disputed,
            t.teigmedflerematrikkelenheter AS multiple_matrikkelenheter,
            t.uregistrertjordsameie AS unregistered_land_coownership,
            0::double precision AS distance_m,
            ST_Contains(t.omrade, point_input.geom) AS contains_point,
            COALESCE(m_units.matrikkelenheter, '[]'::jsonb) AS matrikkelenheter,
            {geom_select}
        FROM {_TEIG} t
        CROSS JOIN point_input
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'matrikkelenhetid', m.matrikkelenhetid,
                    'kommunenummer', m.kommunenummer,
                    'gardsnummer', m.gardsnummer,
                    'bruksnummer', m.bruksnummer,
                    'festenummer', m.festenummer,
                    'seksjonsnummer', m.seksjonsnummer,
                    'bruksnavn', m.bruksnavn,
                    'matrikkelenhetstype', m.matrikkelenhetstype,
                    'uuidmatrikkelenhet', m.uuidmatrikkelenhet
                )
                ORDER BY m.matrikkelenhetid
            ) AS matrikkelenheter
            FROM (
                SELECT *
                FROM {_MATRIKKELENHET}
                WHERE teig_fk = t.teigid
                ORDER BY matrikkelenhetid
                LIMIT 10
            ) m
        ) m_units ON TRUE
        WHERE t.omrade && point_input.geom
          AND ST_Intersects(t.omrade, point_input.geom)
        ORDER BY ST_Area(t.omrade) ASC NULLS LAST, t.teigid
        LIMIT %s
        """,
        (longitude, latitude, limit),
    )
    return _payload(
        {
            "lat": latitude,
            "lon": longitude,
            "limit": limit,
            "includeGeometry": include_geometry,
        },
        rows,
        include_geometry=include_geometry,
        notes=["Point lookup uses ST_Intersects; containsPoint marks strict containment."],
    )


async def get_teig_boundary(
    *,
    teig_id: int,
    id_type: str = "teigid",
    include_geometry: bool = True,
) -> dict[str, Any]:
    id_column = "objid" if id_type == "objid" else "teigid"
    rows = await _read_rows(
        f"""
        SELECT
            t.objid,
            t.teigid,
            t.uuidteig,
            t.kommunenummer,
            t.kommunenavn,
            t.matrikkelnummertekst,
            t.lagretberegnetareal AS area_m2,
            t.noyaktighetsklasseteig AS accuracy_class,
            t.tvist AS disputed,
            t.teigmedflerematrikkelenheter AS multiple_matrikkelenheter,
            t.uregistrertjordsameie AS unregistered_land_coownership,
            NULL::double precision AS distance_m,
            NULL::boolean AS contains_point,
            COALESCE(m_units.matrikkelenheter, '[]'::jsonb) AS matrikkelenheter,
            {_geometry_select(include_geometry, "ST_Boundary(t.omrade)")}
        FROM {_TEIG} t
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'matrikkelenhetid', m.matrikkelenhetid,
                    'kommunenummer', m.kommunenummer,
                    'gardsnummer', m.gardsnummer,
                    'bruksnummer', m.bruksnummer,
                    'festenummer', m.festenummer,
                    'seksjonsnummer', m.seksjonsnummer,
                    'bruksnavn', m.bruksnavn,
                    'matrikkelenhetstype', m.matrikkelenhetstype,
                    'uuidmatrikkelenhet', m.uuidmatrikkelenhet
                )
                ORDER BY m.matrikkelenhetid
            ) AS matrikkelenheter
            FROM (
                SELECT *
                FROM {_MATRIKKELENHET}
                WHERE teig_fk = t.teigid
                ORDER BY matrikkelenhetid
                LIMIT 10
            ) m
        ) m_units ON TRUE
        WHERE t.{id_column} = %s
        LIMIT 1
        """,
        (teig_id,),
    )
    return _payload(
        {
            "teigId": teig_id,
            "idType": id_type,
            "limit": 1,
            "includeGeometry": include_geometry,
        },
        rows,
        include_geometry=include_geometry,
        notes=[
            "Boundary is derived from teig.omrade with ST_Boundary because no direct teig-to-eiendomsgrense relation was present in inspected metadata."
        ],
        geometry_kind="teig.omrade boundary",
    )


async def search_property_by_identifier(
    *,
    kommunenummer: str | None = None,
    gardsnummer: int | None = None,
    bruksnummer: int | None = None,
    festenummer: int | None = None,
    seksjonsnummer: int | None = None,
    matrikkelenhetid: int | None = None,
    limit: int = 25,
    include_geometry: bool = False,
) -> dict[str, Any]:
    limit = _limit(limit)
    conditions: list[str] = []
    params: list[Any] = []

    if matrikkelenhetid is not None:
        conditions.append("m.matrikkelenhetid = %s")
        params.append(matrikkelenhetid)
    else:
        conditions.extend([
            "m.kommunenummer = %s",
            "m.gardsnummer = %s",
            "m.bruksnummer = %s",
        ])
        params.extend([kommunenummer, gardsnummer, bruksnummer])
        if festenummer is not None:
            conditions.append("m.festenummer IS NOT DISTINCT FROM %s")
            params.append(festenummer)
        if seksjonsnummer is not None:
            conditions.append("m.seksjonsnummer IS NOT DISTINCT FROM %s")
            params.append(seksjonsnummer)

    where_sql = " AND ".join(conditions)
    params.append(limit)
    geom_select = _geometry_select(include_geometry)

    rows = await _read_rows(
        f"""
        SELECT
            t.objid,
            t.teigid,
            t.uuidteig,
            t.kommunenummer,
            t.kommunenavn,
            t.matrikkelnummertekst,
            t.lagretberegnetareal AS area_m2,
            t.noyaktighetsklasseteig AS accuracy_class,
            t.tvist AS disputed,
            t.teigmedflerematrikkelenheter AS multiple_matrikkelenheter,
            t.uregistrertjordsameie AS unregistered_land_coownership,
            NULL::double precision AS distance_m,
            NULL::boolean AS contains_point,
            jsonb_build_array(jsonb_build_object(
                'matrikkelenhetid', m.matrikkelenhetid,
                'kommunenummer', m.kommunenummer,
                'gardsnummer', m.gardsnummer,
                'bruksnummer', m.bruksnummer,
                'festenummer', m.festenummer,
                'seksjonsnummer', m.seksjonsnummer,
                'bruksnavn', m.bruksnavn,
                'matrikkelenhetstype', m.matrikkelenhetstype,
                'uuidmatrikkelenhet', m.uuidmatrikkelenhet,
                'buildingCount', COALESCE(building_counts.building_count, 0),
                'buildings', COALESCE(building_samples.buildings, '[]'::jsonb)
            )) AS matrikkelenheter,
            {geom_select}
        FROM {_MATRIKKELENHET} m
        LEFT JOIN {_TEIG} t ON t.teigid = m.teig_fk
        LEFT JOIN LATERAL (
            SELECT COUNT(DISTINCT bu.bygning_fk)::integer AS building_count
            FROM {_BRUKSENHET} bu
            WHERE bu.matrikkelenhetid = m.matrikkelenhetid
              AND bu.bygning_fk IS NOT NULL
        ) building_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'bygningid', b.bygningid,
                    'bygningsnummer', b.bygningsnummer,
                    'bygningstype', b.bygningstype,
                    'bygningsstatus', b.bygningsstatus,
                    'stedfestingverifisert', b.stedfestingverifisert
                )
                ORDER BY b.bygningid
            ) AS buildings
            FROM (
                SELECT DISTINCT b.bygningid, b.bygningsnummer, b.bygningstype, b.bygningsstatus, b.stedfestingverifisert
                FROM {_BRUKSENHET} bu
                JOIN {_BYGNING_TABLE} b ON b.bygningid = bu.bygning_fk
                WHERE bu.matrikkelenhetid = m.matrikkelenhetid
                  AND bu.bygning_fk IS NOT NULL
                ORDER BY b.bygningid
                LIMIT 5
            ) b
        ) building_samples ON TRUE
        WHERE {where_sql}
        ORDER BY m.matrikkelenhetid
        LIMIT %s
        """,
        tuple(params),
    )
    return _payload(
        {
            "kommunenummer": kommunenummer,
            "gardsnummer": gardsnummer,
            "bruksnummer": bruksnummer,
            "festenummer": festenummer,
            "seksjonsnummer": seksjonsnummer,
            "matrikkelenhetid": matrikkelenhetid,
            "limit": limit,
            "includeGeometry": include_geometry,
        },
        rows,
        include_geometry=include_geometry,
        notes=[
            "Building context is joined through matrikkel_bygning.bruksenhet.matrikkelenhetid where available.",
            "Address joins are not included by default because inspected address tables did not expose supporting indexes for this access path.",
        ],
    )


async def summarize_property_context_for_point(
    *,
    latitude: float,
    longitude: float,
    radius_meters: float = 250,
    limit: int = 3,
) -> dict[str, Any]:
    at_point = await find_teig_at_point(
        latitude=latitude,
        longitude=longitude,
        limit=3,
        include_geometry=False,
    )
    nearby = await find_teiger_near_point(
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        limit=limit,
        include_geometry=False,
    )
    return {
        "source": SOURCE_LABEL,
        "schema": MATR_EIENDOM_SCHEMA,
        "srid": DATASET_SRID,
        "query": {
            "lat": latitude,
            "lon": longitude,
            "radiusMeters": radius_meters,
            "limit": limit,
        },
        "atPoint": {
            "count": at_point["count"],
            "results": at_point["results"],
        },
        "nearby": {
            "count": nearby["count"],
            "results": nearby["results"],
        },
        "notes": [
            "Geometry omitted for compact LLM context.",
            "Results depend on the imported MatrikkelenEiendomskartTeig source data and query constraints.",
        ],
    }
