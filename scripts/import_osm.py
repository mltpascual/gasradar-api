"""
OpenStreetMap Import Script — Fetches gas stations from Overpass API.
Run with: python -m scripts.import_osm --country PH
"""
import asyncio
import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import engine, AsyncSessionLocal, Base
from app.models.core import Country, Station

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding boxes for target countries
COUNTRY_BOUNDS = {
    "PH": {
        "south": 4.5,
        "west": 116.9,
        "north": 21.2,
        "east": 127.0,
        "description": "Philippines",
    },
    "CA": {
        "south": 41.7,
        "west": -141.0,
        "north": 83.1,
        "east": -52.6,
        "description": "Canada",
    },
}

# For large countries, we query major metro areas instead of the whole country
METRO_AREAS = {
    "CA": [
        {"name": "Toronto", "south": 43.5, "west": -79.7, "north": 43.9, "east": -79.1},
        {"name": "Vancouver", "south": 49.0, "west": -123.3, "north": 49.4, "east": -122.7},
        {"name": "Montreal", "south": 45.4, "west": -73.8, "north": 45.7, "east": -73.4},
        {"name": "Calgary", "south": 50.9, "west": -114.3, "north": 51.2, "east": -113.9},
        {"name": "Ottawa", "south": 45.3, "west": -75.8, "north": 45.5, "east": -75.5},
    ],
    "PH": [
        {"name": "Metro Manila", "south": 14.35, "west": 120.9, "north": 14.78, "east": 121.15},
        {"name": "Cebu City", "south": 10.25, "west": 123.8, "north": 10.4, "east": 123.95},
        {"name": "Davao City", "south": 7.0, "west": 125.5, "north": 7.15, "east": 125.7},
    ],
}


def build_overpass_query(south: float, west: float, north: float, east: float) -> str:
    """Build Overpass QL query for gas stations in a bounding box."""
    return f"""
    [out:json][timeout:60];
    (
      node["amenity"="fuel"]({south},{west},{north},{east});
      way["amenity"="fuel"]({south},{west},{north},{east});
    );
    out center;
    """


async def fetch_stations_from_osm(area: dict) -> list:
    """Fetch gas stations from Overpass API for a given area."""
    query = build_overpass_query(area["south"], area["west"], area["north"], area["east"])

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        data = response.json()

    stations = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name", tags.get("brand", "Unknown Station"))
        brand = tags.get("brand", tags.get("operator", "Unknown"))

        # Get coordinates (nodes have lat/lon directly, ways have center)
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lng = element.get("lon") or element.get("center", {}).get("lon")

        if lat and lng:
            stations.append({
                "osm_id": str(element.get("id", "")),
                "name": name,
                "brand": brand,
                "address": tags.get("addr:full", tags.get("addr:street", "")),
                "lat": lat,
                "lng": lng,
            })

    return stations


async def import_country(country_code: str):
    """Import gas stations for a country from OpenStreetMap."""
    code = country_code.upper()
    if code not in METRO_AREAS:
        logger.error("[OSM] Unsupported country: %s", code)
        return

    async with AsyncSessionLocal() as db:
        # Find country in database
        result = await db.execute(select(Country).where(Country.code == code))
        country = result.scalar_one_or_none()
        if not country:
            logger.error("[OSM] Country %s not found in database. Run seed_data.py first.", code)
            return

        total_imported = 0
        total_skipped = 0

        for area in METRO_AREAS[code]:
            logger.info("[OSM] Fetching stations for %s...", area["name"])
            try:
                osm_stations = await fetch_stations_from_osm(area)
                logger.info("[OSM] Found %d stations in %s", len(osm_stations), area["name"])

                for s in osm_stations:
                    # Check if already exists by osm_id
                    existing = await db.execute(
                        select(Station).where(Station.osm_id == s["osm_id"])
                    )
                    if existing.scalar_one_or_none():
                        total_skipped += 1
                        continue

                    station = Station(
                        country_id=country.id,
                        name=s["name"][:200],
                        brand=s["brand"][:100],
                        address=s["address"] or None,
                        latitude=Decimal(str(round(s["lat"], 7))),
                        longitude=Decimal(str(round(s["lng"], 7))),
                        source="osm",
                        osm_id=s["osm_id"],
                    )
                    db.add(station)
                    total_imported += 1

                await db.flush()

            except Exception as e:
                logger.error("[OSM] Error fetching %s: %s", area["name"], str(e))
                continue

        await db.commit()
        logger.info("[OSM] Import complete for %s: %d imported, %d skipped (duplicates)",
                     code, total_imported, total_skipped)


async def main():
    parser = argparse.ArgumentParser(description="Import gas stations from OpenStreetMap")
    parser.add_argument("--country", type=str, required=True, help="Country code (PH, CA)")
    args = parser.parse_args()

    await import_country(args.country)


if __name__ == "__main__":
    asyncio.run(main())
