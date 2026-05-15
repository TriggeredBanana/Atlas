import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import logging
from fastmcp import FastMCP
from db import get_connection
from geometry_store import geometry_store


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
)
logger = logging.getLogger(__name__)


vector_mcp = FastMCP("vector_server")

# ---------------------------------------------------------------------------
# Shapely tools
# Edit docstrings here to guide the AI agent on when to call each tool.
# ---------------------------------------------------------------------------

@vector_mcp.tool()
async def buffer(meter_radius: float, geojson: str = "", geometry_ref: str = "", session_id: str = "") -> str:
    """
    Creates a buffer zone around a geometry.
    Use this when the user asks about areas within a certain distance of a location,
    impact zones, proximity analysis, or wants to create a buffered area.

    Accepts either a raw GeoJSON geometry string OR a geometry_ref returned by
    a previous tool call.  Returns a geometry reference for the buffered result.

    Args:
        meter_radius: Buffer distance in metres.
        geojson: A GeoJSON geometry string (optional if geometry_ref is provided).
        geometry_ref: A geometry reference ID from a previous tool call (preferred).
        session_id: Current session ID for geometry caching.
    """
    # Resolve geometry from ref if provided
    resolved = geojson
    if geometry_ref and session_id:
        cached = geometry_store.retrieve(session_id, geometry_ref)
        if cached:
            resolved = json.dumps(cached) if isinstance(cached, dict) else cached
    if not resolved:
        return json.dumps({"error": "No geometry provided. Supply geojson or geometry_ref."})

    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT ST_AsGeoJSON(ST_Transform(ST_buffer(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 25833), %s), 4326)) AS buffer_geojson;
                    """,
                    (resolved, meter_radius)
                )
                row = await cur.fetchone()
                if not row:
                    return "Buffer operation failed: no result returned from database."
                result_geojson = json.loads(row["buffer_geojson"])
                if session_id:
                    ref = geometry_store.store(session_id, result_geojson)
                    return json.dumps({"status": "success", "geometry_ref": ref, "type": result_geojson.get("type", "Polygon")}, ensure_ascii=False)
                return json.dumps({"buffer_geojson": result_geojson}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error creating buffer: {e}")
        return f"Failed to create buffer: {e}"


@vector_mcp.tool()
async def buffer_features(geojson_collection: str, meter_radius: float, session_id: str = "") -> str:
    """
    Buffer ALL features in a GeoJSON FeatureCollection at once in a single
    database query.  ALWAYS prefer this over calling buffer() in a loop.

    Args:
        geojson_collection: A GeoJSON FeatureCollection string, or a geometry_ref
                            pointing to one.
        meter_radius: Buffer distance in metres applied to every feature.
        session_id: Current session ID for geometry caching.
    """
    # Resolve geometry ref
    resolved = geojson_collection
    if session_id and resolved.startswith("geo_"):
        cached = geometry_store.retrieve(session_id, resolved)
        if cached:
            resolved = json.dumps(cached) if isinstance(cached, dict) else cached

    try:
        collection = json.loads(resolved)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Invalid GeoJSON: {e}"})

    features = collection.get("features", [])
    if not features:
        return json.dumps({"error": "No features in FeatureCollection."})

    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        ordinality,
                        ST_AsGeoJSON(
                            ST_Transform(
                                ST_Buffer(
                                    ST_Transform(
                                        ST_SetSRID(ST_GeomFromGeoJSON(feat->>'geometry'), 4326),
                                        25833),
                                    %s),
                                4326)
                        ) AS buffered
                    FROM json_array_elements(%s::json) WITH ORDINALITY AS t(feat, ordinality)
                    ORDER BY ordinality;
                    """,
                    (meter_radius, json.dumps(features))
                )
                rows = await cur.fetchall()

        out_features = []
        for row in rows:
            idx = int(row["ordinality"]) - 1
            props = features[idx].get("properties", {}) if idx < len(features) else {}
            out_features.append({
                "type": "Feature",
                "geometry": json.loads(row["buffered"]),
                "properties": props,
            })

        result_fc = {"type": "FeatureCollection", "features": out_features}
        if session_id:
            ref = geometry_store.store(session_id, result_fc)
            return json.dumps({
                "status": "success",
                "geometry_ref": ref,
                "feature_count": len(out_features),
                "message": f"Buffered {len(out_features)} features by {meter_radius}m.",
            }, ensure_ascii=False)
        return json.dumps(result_fc, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"buffer_features failed: {e}")
        return json.dumps({"error": f"Buffer batch failed: {e}"})


@vector_mcp.tool()
async def intersection(geojson1: str, geojson2: str) -> str:
    """
    Finds the overlapping area between two geometries.
    Use this when the user asks what two areas have in common, overlap analysis,
    or wants to find the shared region between two spatial features.
    Both inputs must be GeoJSON geometry strings and the return value is the intersected area in GeoJSON format.
    """
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT ST_AsGeoJSON(
                        ST_Transform(
                             ST_Intersection(
                               ST_Transform(
                                   ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),25833),
                               ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),25833)),4326)) AS intersection_geojson;
                    """,
                    (geojson1, geojson2)
                ) 
                row = await cur.fetchone()
                if not row:
                    return "Intersection operation failed: no result returned from database."
                return json.dumps({"intersection_geojson": json.loads(row["intersection_geojson"])}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error calculating intersection: {e}")
        return f"Failed to calculate intersection: {e}"


@vector_mcp.tool()
async def envelope(geojson: str) -> str:
    """
    Returns the bounding box (minimum enclosing rectangle) of a geometry.
    Use this when the user asks for the extent, bounding box, or spatial bounds of a feature.
    Input must be a GeoJSON string. Returns the bounding rectangle as GeoJSON.
    """
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT ST_AsGeoJSON(
                        ST_Transform(
                            ST_Envelope(
                                ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),25833)),4326)) AS envelope_geojson;
                    """,
                    (geojson,)
                )
                row = await cur.fetchone()
                if not row or not row["envelope_geojson"]:
                    return "Could not create envelope."
                return json.dumps({
                    "envelope_geojson": json.loads(row["envelope_geojson"])
                }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Envelope failed: {e}")
        return f"Error creating envelope: {e}"


@vector_mcp.tool()
async def get_coordinates(geojson: str) -> str:
    """
    Extracts the coordinate pairs from a geometry.
    Use this when the user wants to know the actual lon/lat or x/y values of a geometry,
    or needs the raw coordinate list of a spatial feature.
    """
    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT ST_AsGeoJSON(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) AS geojson_out;
                    """,
                    (geojson,)
                )
                row = await cur.fetchone()
                if not row or not row["geojson_out"]:
                    return "Could not get coordinates."
                geometry = json.loads(row["geojson_out"])
                return json.dumps({"type": geometry["type"], "coordinates": geometry["coordinates"]}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting coordinates: {e}")
        raise ValueError(f"Failed to get coordinates: {e}")


# ---------------------------------------------------------------------------
# GeoPandas tools
# ---------------------------------------------------------------------------

@vector_mcp.tool()
async def point_in_polygon(points_geojson: str, polygon_geojson: str) -> str:
    """
    Checks which points fall inside which polygons using a spatial join.
    Use this when the user wants to know if locations are inside a protected area,
    zone, or region, or asks about containment of point features within polygons.
    Both inputs are GeoJSON strings.
    """
    try:
        points = json.loads(points_geojson)
        results = []
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                for feature in points.get("features", []):
                    geom = json.dumps(feature["geometry"])
                    await cur.execute(
                        """
                        SELECT ST_Within(
                            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 25833),
                            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 25833)
                        ) AS is_inside;
                        """,
                        (geom, polygon_geojson)
                    )
                    row = await cur.fetchone()
                    if row and row["is_inside"]:
                        results.append(feature)
        return json.dumps({
            "status": "success",
            "message": f"{len(results)} point(s) found inside the polygon." if results else "No points found inside the polygon.",
            "num_points": len(results),
            "points_inside": results
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in point_in_polygon: {e}")
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Database tools — custom tools
# ---------------------------------------------------------------------------

@vector_mcp.tool()
async def get_verdensarv_sites(session_id: str = "", latitude: float = 0.0, longitude: float = 0.0, limit: int = 0) -> str:
    """
    Fetches Norwegian world heritage sites from the database.

    When latitude, longitude, and limit are provided, returns only the N
    nearest sites sorted by distance.  Otherwise returns all sites.

    Results include name, protection date, and description.  Geometries are
    stored in the backend geometry cache — each site gets a geometry_ref you
    can pass directly to map-draw_shape or map-draw_shapes_batch.
    The LLM should NEVER request raw GeoJSON from this tool.

    Args:
        session_id: Current session ID (used for geometry caching).
        latitude: Optional latitude for nearest-site queries (WGS84).
        longitude: Optional longitude for nearest-site queries (WGS84).
        limit: Max number of sites to return (0 = all).
    """
    try:
        use_spatial = latitude != 0.0 and longitude != 0.0 and limit > 0
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                if use_spatial:
                    await cur.execute(
                        """
                        SELECT
                            navn,
                            vernedato,
                            informasjon,
                            ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson,
                            ST_Distance(
                                ST_Transform(geom, 4326)::geography,
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                            ) AS distance_m
                        FROM norges_verdensarv
                        ORDER BY distance_m ASC
                        LIMIT %s;
                        """,
                        (longitude, latitude, limit)
                    )
                else:
                    await cur.execute(
                        """
                        SELECT
                            navn,
                            vernedato,
                            informasjon,
                            ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geojson
                        FROM norges_verdensarv;
                        """
                    )
                rows = await cur.fetchall()
                if not rows:
                    return "No world heritage sites found in database."

                results = []
                for row in rows:
                    r = dict(row)
                    geojson_str = r["geojson"]
                    site_info = {
                        "navn": r["navn"],
                        "vernedato": r["vernedato"].isoformat() if r["vernedato"] else None,
                        "informasjon": r["informasjon"],
                    }
                    if use_spatial:
                        site_info["distance_m"] = round(r.get("distance_m", 0), 1)

                    # Store geometry in cache, give LLM only the ref
                    if session_id and geojson_str:
                        geojson_obj = json.loads(geojson_str)
                        ref = geometry_store.store(session_id, geojson_obj)
                        site_info["geometry_ref"] = ref
                    elif geojson_str:
                        # Fallback: include raw geojson only when no session
                        site_info["geojson"] = geojson_str

                    results.append(site_info)

                return json.dumps({
                    "status": "success",
                    "count": len(results),
                    "sites": results,
                    "message": f"Found {len(results)} world heritage site(s). Use geometry_ref values with map-draw_shapes_batch to display them."
                }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to fetch world heritage sites: {e}")
        return f"Error fetching world heritage sites: {e}"

@vector_mcp.tool(annotations={"readOnlyHint": True})
async def voronoi(geojson: str, session_id: str = "") -> str:
    """
    Generates a Voronoi diagram from a GeoJSON FeatureCollection of points (or any geometries,
    whose centroids are used as input seeds). Uses PostGIS ST_VoronoiPolygons for a true
    Delaunay-based result.

    Returns a geometry reference for the resulting FeatureCollection.
    Pass the geometry_ref to map-draw_shape or map-draw_shapes_batch to visualize.

    Use this tool whenever the user asks for Voronoi analysis, influence zones, nearest-feature
    partitioning, or any spatial tessellation from a set of point or polygon features.

    Args:
        geojson: A GeoJSON FeatureCollection (points or polygons). Each feature may carry
                 any properties — they are preserved on the output polygons.
        session_id: Current session ID for geometry caching.
    """
    try:
        collection = json.loads(geojson)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Ugyldig GeoJSON: {e}"})

    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        return json.dumps({"error": "GeoJSON må være en FeatureCollection."})

    features_in = collection.get("features")
    if not isinstance(features_in, list):
        return json.dumps({"error": "GeoJSON mangler en gyldig 'features'-liste."})
    if len(features_in) < 2:
        return json.dumps({"error": "Minst 2 punkter kreves for å generere et Voronoi-diagram."})

    valid_features = []
    for index, feature in enumerate(features_in, start=1):
        if not isinstance(feature, dict):
            return json.dumps({"error": f"Feature #{index} er ugyldig."})

        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or not geometry.get("type"):
            return json.dumps({"error": f"Feature #{index} mangler en gyldig geometri."})

        valid_features.append(feature)

    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    WITH seeds AS (
                        SELECT
                            ST_Centroid(
                                ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON(feat->>'geometry'), 4326),
                                    25833
                                )
                            ) AS centroid
                        FROM json_array_elements(%s::json) AS feat
                    )
                    SELECT
                        COUNT(*) FILTER (WHERE centroid IS NOT NULL AND NOT ST_IsEmpty(centroid)) AS seed_count,
                        COUNT(DISTINCT ST_AsEWKB(centroid)) FILTER (WHERE centroid IS NOT NULL AND NOT ST_IsEmpty(centroid)) AS distinct_seed_count
                    FROM seeds;
                    """,
                    (json.dumps(valid_features),)
                )
                stats = await cur.fetchone()
                seed_count = int(stats["seed_count"] or 0) if stats else 0
                distinct_seed_count = int(stats["distinct_seed_count"] or 0) if stats else 0

                if seed_count < 2:
                    return json.dumps({"error": "Minst 2 gyldige geometrier kreves for å generere et Voronoi-diagram."})
                if distinct_seed_count < 2:
                    return json.dumps({"error": "Minst 2 unike punktposisjoner kreves for å generere et Voronoi-diagram."})
                if distinct_seed_count != seed_count:
                    return json.dumps({"error": "Duplikate seed-posisjoner støttes ikke i Voronoi-verktøyet."})

                await cur.execute(
                    """
                    WITH seeds AS (
                        SELECT
                            ordinality AS seed_id,
                            feat,
                            ST_Centroid(
                                ST_Transform(
                                    ST_SetSRID(ST_GeomFromGeoJSON(feat->>'geometry'), 4326),
                                    25833
                                )
                            ) AS centroid
                        FROM json_array_elements(%s::json) WITH ORDINALITY AS t(feat, ordinality)
                    ),
                    valid_seeds AS (
                        SELECT seed_id, feat, centroid
                        FROM seeds
                        WHERE centroid IS NOT NULL AND NOT ST_IsEmpty(centroid)
                    ),
                    voronoi_polys AS (
                        SELECT ROW_NUMBER() OVER () AS poly_id, dumped.geom AS voronoi_geom
                        FROM (
                            SELECT (ST_Dump(ST_VoronoiPolygons(ST_Collect(centroid)))).geom
                            FROM valid_seeds
                        ) AS dumped
                    )
                    SELECT
                        s.seed_id,
                        s.feat->'properties' AS properties,
                        ST_AsGeoJSON(ST_Transform(p.voronoi_geom, 4326)) AS geojson
                    FROM valid_seeds s
                    JOIN LATERAL (
                        SELECT v.voronoi_geom
                        FROM voronoi_polys v
                        ORDER BY
                            CASE WHEN ST_Covers(v.voronoi_geom, s.centroid) THEN 0 ELSE 1 END,
                            ST_Distance(v.voronoi_geom, s.centroid),
                            v.poly_id
                        LIMIT 1
                    ) p ON TRUE
                    ORDER BY s.seed_id;
                    """,
                    (json.dumps(valid_features),)
                )
                rows = await cur.fetchall()
                if not rows:
                    return json.dumps({"error": "Voronoi-beregning returnerte ingen polygoner."})

                out_features = []
                for row in rows:
                    r = dict(row)
                    geometry = json.loads(r["geojson"]) if r["geojson"] else None
                    properties = r["properties"] if isinstance(r["properties"], dict) else {}
                    out_features.append({
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": properties,
                    })

                result_fc = {"type": "FeatureCollection", "features": out_features}
                # Store in geometry cache if session available
                if session_id:
                    ref = geometry_store.store(session_id, result_fc)
                    return json.dumps({
                        "status": "success",
                        "geometry_ref": ref,
                        "polygon_count": len(out_features),
                        "message": f"Voronoi diagram with {len(out_features)} polygons. Use geometry_ref with map-draw_shape to display.",
                    }, ensure_ascii=False)
                return json.dumps(result_fc, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"voronoi failed: {e}")
        return json.dumps({"error": f"Voronoi-beregning feilet: {e}"})


# Mount the vector MCP ASGI app at the /mcp/vector path
vector_app = vector_mcp.http_app(path="/mcp")
