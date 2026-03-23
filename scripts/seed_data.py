"""
Seed Data Script — Populates the database with initial countries, fuel types, and sample stations.
Run with: python -m scripts.seed_data
"""
import asyncio
import logging
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import engine, AsyncSessionLocal, Base
from app.models.core import Country, FuelType, Station, ActivePrice

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# SEED DATA DEFINITIONS
# ──────────────────────────────────────────────

COUNTRIES = [
    {
        "code": "PH",
        "name": "Philippines",
        "currency_code": "PHP",
        "currency_symbol": "₱",
        "price_unit": "per liter",
        "min_price": Decimal("20.00"),
        "max_price": Decimal("200.00"),
        "deviation_warn_pct": 15,
        "deviation_reject_pct": 30,
    },
    {
        "code": "CA",
        "name": "Canada",
        "currency_code": "CAD",
        "currency_symbol": "$",
        "price_unit": "per liter",
        "min_price": Decimal("0.50"),
        "max_price": Decimal("5.00"),
        "deviation_warn_pct": 15,
        "deviation_reject_pct": 30,
    },
]

FUEL_TYPES = {
    "PH": [
        {"name": "Regular (RON 91)", "sort_order": 1},
        {"name": "Premium (RON 95)", "sort_order": 2},
        {"name": "Premium Plus (RON 97)", "sort_order": 3},
        {"name": "Diesel", "sort_order": 4},
        {"name": "Diesel Plus", "sort_order": 5},
    ],
    "CA": [
        {"name": "Regular 87", "sort_order": 1},
        {"name": "Mid-Grade 89", "sort_order": 2},
        {"name": "Premium 91-93", "sort_order": 3},
        {"name": "Diesel", "sort_order": 4},
    ],
}

# Sample stations — enough to test with, crowd-sourcing fills the rest
SAMPLE_STATIONS = {
    "PH": [
        {"name": "Shell EDSA Balintawak", "brand": "Shell", "address": "EDSA, Balintawak, Quezon City", "lat": 14.6572, "lng": 120.9721},
        {"name": "Petron C5 Libis", "brand": "Petron", "address": "C5 Road, Libis, Quezon City", "lat": 14.6292, "lng": 121.0754},
        {"name": "Caltex Ortigas", "brand": "Caltex", "address": "Ortigas Ave, Pasig City", "lat": 14.5876, "lng": 121.0615},
        {"name": "Phoenix Marcos Highway", "brand": "Phoenix", "address": "Marcos Highway, Marikina", "lat": 14.6320, "lng": 121.1012},
        {"name": "Shell Katipunan", "brand": "Shell", "address": "Katipunan Ave, Quezon City", "lat": 14.6310, "lng": 121.0740},
        {"name": "Petron Alabang", "brand": "Petron", "address": "Alabang-Zapote Road, Muntinlupa", "lat": 14.4173, "lng": 121.0395},
        {"name": "Seaoil Commonwealth", "brand": "Seaoil", "address": "Commonwealth Ave, Quezon City", "lat": 14.6812, "lng": 121.0556},
        {"name": "Caltex Makati Ave", "brand": "Caltex", "address": "Makati Ave, Makati City", "lat": 14.5547, "lng": 121.0244},
        {"name": "Unioil BGC", "brand": "Unioil", "address": "Bonifacio Global City, Taguig", "lat": 14.5515, "lng": 121.0503},
        {"name": "Jetti Antipolo", "brand": "Jetti", "address": "Sumulong Highway, Antipolo", "lat": 14.5862, "lng": 121.1761},
    ],
    "CA": [
        {"name": "Petro-Canada Yonge & Bloor", "brand": "Petro-Canada", "address": "Yonge St & Bloor St, Toronto, ON", "lat": 43.6710, "lng": -79.3868},
        {"name": "Shell Dundas West", "brand": "Shell", "address": "Dundas St W, Toronto, ON", "lat": 43.6525, "lng": -79.4280},
        {"name": "Esso Highway 401", "brand": "Esso", "address": "Highway 401, Scarborough, ON", "lat": 43.7735, "lng": -79.2577},
        {"name": "Costco Gas Etobicoke", "brand": "Costco", "address": "The Queensway, Etobicoke, ON", "lat": 43.6205, "lng": -79.5132},
        {"name": "Canadian Tire Gas Mississauga", "brand": "Canadian Tire", "address": "Hurontario St, Mississauga, ON", "lat": 43.5890, "lng": -79.6441},
        {"name": "Petro-Canada Granville", "brand": "Petro-Canada", "address": "Granville St, Vancouver, BC", "lat": 49.2632, "lng": -123.1382},
        {"name": "Shell Broadway", "brand": "Shell", "address": "Broadway, Vancouver, BC", "lat": 49.2634, "lng": -123.1015},
        {"name": "Esso Kingsway", "brand": "Esso", "address": "Kingsway, Burnaby, BC", "lat": 49.2286, "lng": -123.0032},
        {"name": "Ultramar Sainte-Catherine", "brand": "Ultramar", "address": "Rue Sainte-Catherine, Montreal, QC", "lat": 45.5088, "lng": -73.5698},
        {"name": "Petro-Canada Laurier", "brand": "Petro-Canada", "address": "Boul Laurier, Quebec City, QC", "lat": 46.7774, "lng": -71.2756},
    ],
}

# Sample seed prices (approximate current prices)
SEED_PRICES = {
    "PH": {
        "Regular (RON 91)": Decimal("62.50"),
        "Premium (RON 95)": Decimal("68.00"),
        "Premium Plus (RON 97)": Decimal("73.50"),
        "Diesel": Decimal("55.80"),
        "Diesel Plus": Decimal("60.20"),
    },
    "CA": {
        "Regular 87": Decimal("1.55"),
        "Mid-Grade 89": Decimal("1.70"),
        "Premium 91-93": Decimal("1.85"),
        "Diesel": Decimal("1.60"),
    },
}


async def seed():
    """Run the full seed process."""
    logger.info("[Seed] Starting database seed...")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[Seed] Tables created/verified")

    async with AsyncSessionLocal() as db:
        # ── Phase 1: Countries ──
        country_map = {}
        for country_data in COUNTRIES:
            existing = await db.execute(
                select(Country).where(Country.code == country_data["code"])
            )
            country = existing.scalar_one_or_none()
            if not country:
                country = Country(**country_data)
                db.add(country)
                await db.flush()
                logger.info("[Seed] Created country: %s (%s)", country.name, country.code)
            else:
                logger.info("[Seed] Country already exists: %s", country.code)
            country_map[country.code] = country

        # ── Phase 2: Fuel Types ──
        fuel_type_map = {}
        for code, fuel_types in FUEL_TYPES.items():
            country = country_map[code]
            for ft_data in fuel_types:
                existing = await db.execute(
                    select(FuelType).where(
                        FuelType.country_id == country.id,
                        FuelType.name == ft_data["name"],
                    )
                )
                ft = existing.scalar_one_or_none()
                if not ft:
                    ft = FuelType(country_id=country.id, **ft_data)
                    db.add(ft)
                    await db.flush()
                    logger.info("[Seed] Created fuel type: %s (%s)", ft.name, code)
                fuel_type_map[(code, ft_data["name"])] = ft

        # ── Phase 3: Stations ──
        station_map = {}
        for code, stations in SAMPLE_STATIONS.items():
            country = country_map[code]
            for s_data in stations:
                existing = await db.execute(
                    select(Station).where(
                        Station.name == s_data["name"],
                        Station.country_id == country.id,
                    )
                )
                station = existing.scalar_one_or_none()
                if not station:
                    station = Station(
                        country_id=country.id,
                        name=s_data["name"],
                        brand=s_data["brand"],
                        address=s_data["address"],
                        latitude=Decimal(str(s_data["lat"])),
                        longitude=Decimal(str(s_data["lng"])),
                        source="seed",
                    )
                    db.add(station)
                    await db.flush()
                    logger.info("[Seed] Created station: %s", station.name)
                station_map[(code, s_data["name"])] = station

        # ── Phase 4: Seed Prices ──
        for code, prices in SEED_PRICES.items():
            for fuel_name, price in prices.items():
                ft = fuel_type_map.get((code, fuel_name))
                if not ft:
                    continue
                for s_name, station in station_map.items():
                    if s_name[0] != code:
                        continue
                    existing = await db.execute(
                        select(ActivePrice).where(
                            ActivePrice.station_id == station.id,
                            ActivePrice.fuel_type_id == ft.id,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        # Add slight variation per station (±3%)
                        import random
                        variation = Decimal(str(round(random.uniform(-0.03, 0.03), 4)))
                        varied_price = price * (1 + variation)
                        varied_price = varied_price.quantize(Decimal("0.01"))

                        ap = ActivePrice(
                            station_id=station.id,
                            fuel_type_id=ft.id,
                            price=varied_price,
                            source="seed",
                        )
                        db.add(ap)

        await db.commit()
        logger.info("[Seed] Database seeding complete!")

        # Summary
        countries_count = (await db.execute(select(Country))).scalars().all()
        fuel_types_count = (await db.execute(select(FuelType))).scalars().all()
        stations_count = (await db.execute(select(Station))).scalars().all()
        prices_count = (await db.execute(select(ActivePrice))).scalars().all()

        logger.info("[Seed] Summary: %d countries, %d fuel types, %d stations, %d active prices",
                     len(countries_count), len(fuel_types_count), len(stations_count), len(prices_count))


if __name__ == "__main__":
    asyncio.run(seed())
