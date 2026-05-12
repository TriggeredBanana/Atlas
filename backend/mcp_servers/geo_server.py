"""
Tools:
  - list_kommuner:      List municipality numbers and names.
  - list_vernetyper:    List all protection types for cultural environments.
  - buffer_search:      Find cultural environments within a given radius.
  - reverse_geocode:    Look up place names from coordinates via Kartverket.
  - forward_geocode:    Search place names and get coordinates via Kartverket.
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error

from fastmcp import FastMCP
from db import query
from config import (
    BUFFER_DISTANCE_MAX_METERS,
    BUFFER_DISTANCE_MIN_METERS,
    BUFFER_RESULT_LIMIT,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("geo_server")

_KARTVERKET_STEDSNAVN_URL = "https://ws.geonorge.no/stedsnavn/v1/punkt"
_KARTVERKET_NAVN_URL = "https://ws.geonorge.no/stedsnavn/v1/navn"
_KARTVERKET_STED_URL = "https://ws.geonorge.no/stedsnavn/v1/sted"
_KARTVERKET_KOMMUNEINFO_URL = "https://ws.geonorge.no/kommuneinfo/v1/punkt"


def _fetch_json(url: str) -> dict | None:
    """Fetch JSON from a URL, returning None on failure."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.error("API-kall feilet for %s: %s", url, exc)
        return None


@mcp.tool
async def list_kommuner(search: str = "") -> str:
    """
    List kommunenummer og kommunenavn. Kan filtreres med søkeord.

    Args:
        search: Søkeord for å filtrere på nummer eller navn (valgfritt).
    """
    if search:
        result = await query(
            "SELECT identifier, description FROM kulturmiljoer.kommunenummer "
            "WHERE identifier ILIKE %s OR description ILIKE %s ORDER BY identifier ASC",
            (f"%{search}%", f"%{search}%")
        )
    else:
        result = await query(
            "SELECT identifier, description FROM kulturmiljoer.kommunenummer ORDER BY identifier ASC"
        )
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool
async def list_vernetyper() -> str:
    """List alle vernetyper for kulturmiljøer."""
    result = await query(
        "SELECT identifier, description FROM kulturmiljoer.vernetype ORDER BY identifier ASC"
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool
async def buffer_search(latitude: float, longitude: float, distance: float = 1000) -> str:
    """
    Finn kulturmiljøer innenfor en gitt avstand fra et punkt.
    Returnerer en GeoJSON FeatureCollection med alle treff.
    Etter kall: send resultatet direkte til map-draw_shape() for å vise det på kartet.

    Args:
        latitude:  Breddegrad, f.eks. 58.1599 for Kristiansand.
        longitude: Lengdegrad, f.eks. 8.0182 for Kristiansand.
        distance:  Søkeradius i meter. Standard er 1000m.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return json.dumps({"error": "Ugyldige koordinater."})

    if not (BUFFER_DISTANCE_MIN_METERS <= distance <= BUFFER_DISTANCE_MAX_METERS):
        return json.dumps({
            "error": f"Avstand må være mellom {BUFFER_DISTANCE_MIN_METERS} og {BUFFER_DISTANCE_MAX_METERS} meter."
        })

    try:
        result = await query("""
            SELECT k.objid, k.navn, k.kulturmiljokategori, k.vernetype,
                   k.informasjon,
                   ST_Distance(
                       k.omrade,
                       ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25833)
                   ) as avstand_meter,
                   ST_AsGeoJSON(ST_Transform(k.omrade, 4326)) as geojson
            FROM kulturmiljoer.kulturmiljo k
            WHERE ST_DWithin(
                k.omrade,
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25833),
                %s
            )
            ORDER BY avstand_meter ASC
            LIMIT %s
        """, (longitude, latitude, longitude, latitude, distance, BUFFER_RESULT_LIMIT))

        features = []
        for row in result:
            geometry = json.loads(row["geojson"]) if row["geojson"] else None
            properties = {k: v for k, v in row.items() if k != "geojson"}
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})

        return json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False
        )
    except Exception as exc:
        logger.exception("buffer_search failed: %s", type(exc).__name__)
        return json.dumps({"error": "Feil ved buffersøk. Prøv igjen senere."})


@mcp.tool
async def reverse_geocode(latitude: float, longitude: float, radius: int = 500) -> str:
    """
    Slå opp stedsnavn, kommune og fylke fra koordinater via Kartverkets API-er.
    Bruk dette verktøyet ALLTID når du trenger å finne ut hvilket sted, område
    eller kommune et koordinatpar tilhører.

    Args:
        latitude:  Breddegrad (WGS84), f.eks. 58.46.
        longitude: Lengdegrad (WGS84), f.eks. 8.77.
        radius:    Søkeradius i meter for stedsnavn-oppslag. Standard er 500 m.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return json.dumps({"error": "Ugyldige koordinater."})
    if radius < 1:
        radius = 1
    if radius > 5000:
        radius = 5000

    # 1) Kommuneinfo API — always returns kommune/fylke for points in Norway
    kommune_params = urllib.parse.urlencode({
        "nord": latitude,
        "ost": longitude,
        "koordsys": 4326,
    })
    kommune_data = _fetch_json(f"{_KARTVERKET_KOMMUNEINFO_URL}?{kommune_params}")

    kommune = kommune_data.get("kommunenavn", "") if kommune_data else ""
    kommunenummer = kommune_data.get("kommunenummer", "") if kommune_data else ""
    fylke = kommune_data.get("fylkesnavn", "") if kommune_data else ""
    fylkesnummer = kommune_data.get("fylkesnummer", "") if kommune_data else ""

    # 2) Stedsnavn API — detailed place names near the point
    stedsnavn_params = urllib.parse.urlencode({
        "nord": latitude,
        "ost": longitude,
        "koordsys": 4326,
        "radius": radius,
        "treffPerSide": 10,
        "side": 1,
    })
    stedsnavn_data = _fetch_json(f"{_KARTVERKET_STEDSNAVN_URL}?{stedsnavn_params}")

    stedsnavn_list = []
    if stedsnavn_data:
        for entry in stedsnavn_data.get("navn", []):
            # The API nests writing forms under entry["stedsnavn"][*]["skrivemåte"]
            skrivemaater = entry.get("stedsnavn", [])
            name = skrivemaater[0].get("skrivemåte", "") if skrivemaater else ""
            if not name:
                name = skrivemaater[0].get("skrivemaate", "") if skrivemaater else ""
            stedsnavn_list.append({
                "stedsnavn": name,
                "navnetype": entry.get("navneobjekttype", ""),
                "avstand_meter": entry.get("meterFraPunkt", None),
            })

    if not kommune and not stedsnavn_list:
        return json.dumps({
            "status": "no_results",
            "message": f"Ingen stedsinformasjon funnet for ({latitude}, {longitude}). Koordinatene er muligens utenfor Norge.",
            "koordinater": {"latitude": latitude, "longitude": longitude},
        })

    return json.dumps({
        "status": "ok",
        "koordinater": {"latitude": latitude, "longitude": longitude},
        "kommune": kommune,
        "kommunenummer": kommunenummer,
        "fylke": fylke,
        "fylkesnummer": fylkesnummer,
        "stedsnavn": stedsnavn_list,
    }, ensure_ascii=False)


def _parse_navn_entry(entry: dict) -> dict:
    """Parse a flat Skrivemate entry from /navn endpoint."""
    punkt = entry.get("representasjonspunkt", {})
    kommuner = entry.get("kommuner", [])
    fylker = entry.get("fylker", [])
    return {
        "stedsnavn": entry.get("skrivemåte", ""),
        "navnetype": entry.get("navneobjekttype", ""),
        "latitude": punkt.get("nord"),
        "longitude": punkt.get("øst"),
        "kommune": kommuner[0].get("kommunenavn", "") if kommuner else "",
        "fylke": fylker[0].get("fylkesnavn", "") if fylker else "",
    }


def _parse_sted_entry(entry: dict) -> dict:
    """Parse a nested Sok entry from /sted endpoint."""
    punkt = entry.get("representasjonspunkt", {})
    stedsnavn_list = entry.get("stedsnavn", [])
    display_name = stedsnavn_list[0].get("skrivemåte", "") if stedsnavn_list else ""
    kommuner = entry.get("kommuner", [])
    fylker = entry.get("fylker", [])
    return {
        "stedsnavn": display_name,
        "navnetype": entry.get("navneobjekttype", ""),
        "latitude": punkt.get("nord"),
        "longitude": punkt.get("øst"),
        "kommune": kommuner[0].get("kommunenavn", "") if kommuner else "",
        "fylke": fylker[0].get("fylkesnavn", "") if fylker else "",
    }


@mcp.tool
async def forward_geocode(name: str) -> str:
    """
    Søk etter et stedsnavn og få tilbake koordinater, kommune og fylke.
    Bruk dette verktøyet når brukeren nevner et stedsnavn, adresse eller
    område og du trenger å finne koordinatene.

    Args:
        name:  Stedsnavnet å søke etter, f.eks. "Moster", "Tromsø", "Bryggen".
    """
    if not name or not name.strip():
        return json.dumps({"error": "Tomt søkeord."})

    search_term = name.strip()

    # 1) Try /navn with wildcard — precise match on skrivemåte
    navn_params = urllib.parse.urlencode({
        "sok": f"{search_term}*",
        "treffPerSide": 5,
        "utkoordsys": 4258,
    })
    navn_data = _fetch_json(f"{_KARTVERKET_NAVN_URL}?{navn_params}")

    if navn_data and navn_data.get("navn"):
        results = [_parse_navn_entry(e) for e in navn_data["navn"]]
        return json.dumps({
            "status": "ok",
            "søk": search_term,
            "kilde": "navn",
            "resultater": results,
        }, ensure_ascii=False)

    # 2) Fallback to /sted with fuzzy — broader search
    sted_params = urllib.parse.urlencode({
        "sok": search_term,
        "fuzzy": "true",
        "treffPerSide": 5,
        "utkoordsys": 4258,
    })
    sted_data = _fetch_json(f"{_KARTVERKET_STED_URL}?{sted_params}")

    if sted_data and sted_data.get("navn"):
        results = [_parse_sted_entry(e) for e in sted_data["navn"]]
        return json.dumps({
            "status": "ok",
            "søk": search_term,
            "kilde": "sted_fuzzy",
            "resultater": results,
        }, ensure_ascii=False)

    return json.dumps({
        "status": "no_results",
        "message": f"Ingen stedsnavn funnet for '{search_term}'.",
    })


# Expose as ASGI app for mounting in server.py
geo_app = mcp.http_app(path="/mcp")