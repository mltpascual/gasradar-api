"""
Station Service — handles nearby station queries and station CRUD.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from decimal import Decimal
from sqlalchemy import select, text, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core import Station, ActivePrice, FuelType, Country
from app.utils.geo import haversine_distance

logger = logging.getLogger(__name__)


def _compute_freshness(reported_at: Optional[datetime]) -> str:
    """Compute freshness label based on how old the price report is."""
    if reported_at is None:
        return "may_be_outdated"

    now = datetime.now(timezone.utc)
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)

    age = now - reported_at
    if age < timedelta(hours=24):
        return "just_updated"
    elif age < timedelta(days=3):
        return "recent"
    elif age < timedelta(days=7):
        return "this_week"
    else:
        return "may_be_outdated"


async def get_nearby_stations(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: int = 5,
    country_code: Optional[str] = None,
    fuel_type_id: Optional[int] = None,
    sort_by: str = "distance",  # "distance" or "price"
    limit: int = 50,
) -> dict:
    """
    Get nearby stations with their active prices.
    Uses Python-side Haversine for MVP (no PostGIS dependency).
    """
    logger.info("[API] Fetching nearby stations: lat=%s, lng=%s, radius=%dkm, sort=%s",
                lat, lng, radius_km, sort_by)

    # Build query for active stations
    query = select(Station).where(Station.is_active == True)

    if country_code:
        country_result = await db.execute(
            select(Country).where(Country.code == country_code.upper())
        )
        country = country_result.scalar_one_or_none()
        if country:
            query = query.where(Station.country_id == country.id)

    # Bounding box pre-filter (rough, fast)
    lat_delta = radius_km / 111.0  # ~111km per degree latitude
    lng_delta = radius_km / (111.0 * max(abs(float(lat)) * 0.0175, 0.01))  # rough cos adjustment
    query = query.where(
        and_(
            Station.latitude >= Decimal(str(lat - lat_delta)),
            Station.latitude <= Decimal(str(lat + lat_delta)),
            Station.longitude >= Decimal(str(lng - lng_delta)),
            Station.longitude <= Decimal(str(lng + lng_delta)),
        )
    )

    result = await db.execute(query)
    stations = result.scalars().all()

    # Calculate exact distances and filter
    station_list = []
    for station in stations:
        dist = haversine_distance(lat, lng, float(station.latitude), float(station.longitude))
        if dist <= radius_km:
            # Fetch active prices for this station
            prices_result = await db.execute(
                select(ActivePrice, FuelType).join(
                    FuelType, ActivePrice.fuel_type_id == FuelType.id
                ).where(ActivePrice.station_id == station.id)
            )
            prices = []
            for ap, ft in prices_result.all():
                # Get country for currency
                country_obj = await db.get(Country, station.country_id)
                prices.append({
                    "fuel_type_id": ft.id,
                    "fuel_type_name": ft.name,
                    "price": float(ap.price),
                    "currency": country_obj.currency_code if country_obj else "???",
                    "freshness": _compute_freshness(ap.reported_at),
                    "reported_at": ap.reported_at.isoformat() if ap.reported_at else None,
                })

            # If filtering by fuel type, skip stations without that fuel type
            if fuel_type_id:
                matching_prices = [p for p in prices if p["fuel_type_id"] == fuel_type_id]
                if not matching_prices:
                    continue

            station_list.append({
                "id": station.id,
                "name": station.name,
                "brand": station.brand,
                "address": station.address,
                "latitude": float(station.latitude),
                "longitude": float(station.longitude),
                "distance_km": round(dist, 1),
                "prices": prices,
            })

    # Sort
    if sort_by == "price" and fuel_type_id:
        station_list.sort(
            key=lambda s: next(
                (p["price"] for p in s["prices"] if p["fuel_type_id"] == fuel_type_id),
                float("inf"),
            )
        )
    else:
        station_list.sort(key=lambda s: s["distance_km"])

    station_list = station_list[:limit]

    # Determine country info for meta
    meta_country = country_code.upper() if country_code else "ALL"
    meta_currency = "???"
    if country_code:
        c = await db.execute(select(Country).where(Country.code == country_code.upper()))
        c_obj = c.scalar_one_or_none()
        if c_obj:
            meta_currency = c_obj.currency_code

    return {
        "stations": station_list,
        "meta": {
            "count": len(station_list),
            "radius_km": radius_km,
            "country": meta_country,
            "currency": meta_currency,
        },
    }


async def get_station_detail(
    db: AsyncSession,
    station_id: int,
) -> Optional[dict]:
    """Get detailed information for a single station."""
    logger.info("[API] Fetching station detail: id=%d", station_id)

    station = await db.get(Station, station_id)
    if not station or not station.is_active:
        return None

    country = await db.get(Country, station.country_id)

    # Fetch active prices
    prices_result = await db.execute(
        select(ActivePrice, FuelType).join(
            FuelType, ActivePrice.fuel_type_id == FuelType.id
        ).where(ActivePrice.station_id == station.id).order_by(FuelType.sort_order)
    )

    prices = []
    for ap, ft in prices_result.all():
        # Count reports in last 24h
        from app.models.core import PriceReport
        count_result = await db.execute(
            select(func.count()).select_from(PriceReport).where(
                and_(
                    PriceReport.station_id == station.id,
                    PriceReport.fuel_type_id == ft.id,
                    PriceReport.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
                )
            )
        )
        report_count = count_result.scalar()

        prices.append({
            "fuel_type_id": ft.id,
            "fuel_type_name": ft.name,
            "price": float(ap.price),
            "currency": country.currency_code if country else "???",
            "freshness": _compute_freshness(ap.reported_at),
            "reported_at": ap.reported_at.isoformat() if ap.reported_at else None,
            "report_count_24h": report_count,
        })

    # Recent activity
    from app.models.core import PriceReport
    total_7d = await db.execute(
        select(func.count()).select_from(PriceReport).where(
            and_(
                PriceReport.station_id == station.id,
                PriceReport.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
            )
        )
    )

    last_update = await db.execute(
        select(func.max(ActivePrice.updated_at)).where(ActivePrice.station_id == station.id)
    )

    return {
        "id": station.id,
        "name": station.name,
        "brand": station.brand,
        "address": station.address,
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
        "country_code": country.code if country else "??",
        "prices": prices,
        "recent_activity": {
            "total_reports_7d": total_7d.scalar(),
            "last_updated": (lu.isoformat() if (lu := last_update.scalar()) else None),
        },
    }
