"""
Admin Router — protected endpoints for station and report management.
Requires ADMIN_API_KEY in the X-API-Key header.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from datetime import datetime, timezone

from app.database import get_db
from app.config import settings
from app.models.core import Station, Country, PriceReport, ActivePrice, PriceHistory, FuelType
from app.schemas.station import StationCreateRequest, StationUpdateRequest
from app.schemas.report import ReportStatusUpdate
from app.utils.errors import unauthorized, not_found, bad_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


async def verify_admin_key(x_api_key: str = Header(...)):
    """Dependency to verify admin API key."""
    if x_api_key != settings.ADMIN_API_KEY:
        logger.warning("[Admin] Invalid API key attempt")
        return None
    return True


@router.post("/stations")
async def create_station(
    body: StationCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """Create a new gas station."""
    if not auth:
        return unauthorized()

    logger.info("[Admin] Creating station: %s (%s)", body.name, body.brand)

    # Find country
    country_result = await db.execute(
        select(Country).where(Country.code == body.country_code.upper())
    )
    country = country_result.scalar_one_or_none()
    if not country:
        return bad_request(f"Country '{body.country_code}' Not Found")

    station = Station(
        country_id=country.id,
        name=body.name,
        brand=body.brand,
        address=body.address,
        latitude=Decimal(str(body.latitude)),
        longitude=Decimal(str(body.longitude)),
        source="manual",
    )
    db.add(station)
    await db.commit()
    await db.refresh(station)

    return {
        "id": station.id,
        "name": station.name,
        "brand": station.brand,
        "message": "Station Created Successfully",
    }


@router.put("/stations/{station_id}")
async def update_station(
    station_id: int,
    body: StationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """Update an existing gas station."""
    if not auth:
        return unauthorized()

    station = await db.get(Station, station_id)
    if not station:
        return not_found("Station")

    if body.name is not None:
        station.name = body.name
    if body.brand is not None:
        station.brand = body.brand
    if body.address is not None:
        station.address = body.address
    if body.latitude is not None:
        station.latitude = Decimal(str(body.latitude))
    if body.longitude is not None:
        station.longitude = Decimal(str(body.longitude))
    if body.is_active is not None:
        station.is_active = body.is_active

    await db.commit()
    logger.info("[Admin] Updated station #%d", station_id)

    return {"id": station.id, "message": "Station Updated Successfully"}


@router.delete("/stations/{station_id}")
async def deactivate_station(
    station_id: int,
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """Soft-delete (deactivate) a gas station."""
    if not auth:
        return unauthorized()

    station = await db.get(Station, station_id)
    if not station:
        return not_found("Station")

    station.is_active = False
    await db.commit()
    logger.info("[Admin] Deactivated station #%d", station_id)

    return {"id": station.id, "message": "Station Deactivated Successfully"}


@router.get("/reports")
async def list_reports(
    status: Optional[str] = Query(None, pattern="^(approved|rejected|pending|needs_confirmation)$"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """List price reports, optionally filtered by status."""
    if not auth:
        return unauthorized()

    query = select(PriceReport, Station, FuelType).join(
        Station, PriceReport.station_id == Station.id
    ).join(
        FuelType, PriceReport.fuel_type_id == FuelType.id
    )

    if status:
        query = query.where(PriceReport.status == status)

    query = query.order_by(PriceReport.created_at.desc()).limit(limit)
    result = await db.execute(query)

    reports = []
    for report, station, fuel_type in result.all():
        reports.append({
            "id": report.id,
            "station_id": station.id,
            "station_name": station.name,
            "fuel_type_name": fuel_type.name,
            "price": float(report.price),
            "status": report.status,
            "rejection_reason": report.rejection_reason,
            "device_hash": report.device_hash[:8] + "...",
            "ip_address": report.ip_address,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        })

    return {"reports": reports, "count": len(reports)}


@router.patch("/reports/{report_id}")
async def update_report_status(
    report_id: int,
    body: ReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """Manually approve or reject a price report."""
    if not auth:
        return unauthorized()

    report = await db.get(PriceReport, report_id)
    if not report:
        return not_found("Report")

    old_status = report.status
    report.status = body.status
    report.rejection_reason = body.rejection_reason
    report.validated_at = datetime.now(timezone.utc)

    # If manually approving, update active price
    if body.status == "approved" and old_status != "approved":
        from app.services.report_service import _update_active_price
        await _update_active_price(db, report.station_id, report.fuel_type_id, float(report.price), report.id)

    await db.commit()
    logger.info("[Admin] Report #%d status changed: %s -> %s", report_id, old_status, body.status)

    return {"id": report.id, "status": body.status, "message": "Report Status Updated Successfully"}


@router.post("/seed")
async def seed_database(
    db: AsyncSession = Depends(get_db),
    auth: bool = Depends(verify_admin_key),
):
    """Seed the database with initial countries, fuel types, and sample stations."""
    if not auth:
        return unauthorized()

    from decimal import Decimal as D
    import random

    # Check if already seeded
    existing = await db.execute(select(Country))
    if existing.scalars().all():
        return {"message": "Database Already Seeded", "seeded": False}

    logger.info("[Admin] Starting database seed...")

    # Countries
    countries_data = [
        {"code": "PH", "name": "Philippines", "currency_code": "PHP", "currency_symbol": "\u20b1",
         "price_unit": "per liter", "min_price": D("20.00"), "max_price": D("200.00"),
         "deviation_warn_pct": 15, "deviation_reject_pct": 30},
        {"code": "CA", "name": "Canada", "currency_code": "CAD", "currency_symbol": "$",
         "price_unit": "per liter", "min_price": D("0.50"), "max_price": D("5.00"),
         "deviation_warn_pct": 15, "deviation_reject_pct": 30},
    ]
    country_map = {}
    for cd in countries_data:
        c = Country(**cd)
        db.add(c)
        await db.flush()
        country_map[cd["code"]] = c

    # Fuel Types
    fuel_types_data = {
        "PH": [("Regular (RON 91)", 1), ("Premium (RON 95)", 2), ("Premium Plus (RON 97)", 3),
               ("Diesel", 4), ("Diesel Plus", 5)],
        "CA": [("Regular 87", 1), ("Mid-Grade 89", 2), ("Premium 91-93", 3), ("Diesel", 4)],
    }
    ft_map = {}
    for code, fts in fuel_types_data.items():
        for name, order in fts:
            ft = FuelType(country_id=country_map[code].id, name=name, sort_order=order)
            db.add(ft)
            await db.flush()
            ft_map[(code, name)] = ft

    # Stations
    stations_data = {
        "PH": [
            ("Shell EDSA Balintawak", "Shell", "EDSA, Balintawak, Quezon City", 14.6572, 120.9721),
            ("Petron C5 Libis", "Petron", "C5 Road, Libis, Quezon City", 14.6292, 121.0754),
            ("Caltex Ortigas", "Caltex", "Ortigas Ave, Pasig City", 14.5876, 121.0615),
            ("Phoenix Marcos Highway", "Phoenix", "Marcos Highway, Marikina", 14.6320, 121.1012),
            ("Shell Katipunan", "Shell", "Katipunan Ave, Quezon City", 14.6310, 121.0740),
            ("Petron Alabang", "Petron", "Alabang-Zapote Road, Muntinlupa", 14.4173, 121.0395),
            ("Seaoil Commonwealth", "Seaoil", "Commonwealth Ave, Quezon City", 14.6812, 121.0556),
            ("Caltex Makati Ave", "Caltex", "Makati Ave, Makati City", 14.5547, 121.0244),
            ("Unioil BGC", "Unioil", "Bonifacio Global City, Taguig", 14.5515, 121.0503),
            ("Jetti Antipolo", "Jetti", "Sumulong Highway, Antipolo", 14.5862, 121.1761),
        ],
        "CA": [
            ("Petro-Canada Yonge & Bloor", "Petro-Canada", "Yonge St & Bloor St, Toronto, ON", 43.6710, -79.3868),
            ("Shell Dundas West", "Shell", "Dundas St W, Toronto, ON", 43.6525, -79.4280),
            ("Esso Highway 401", "Esso", "Highway 401, Scarborough, ON", 43.7735, -79.2577),
            ("Costco Gas Etobicoke", "Costco", "The Queensway, Etobicoke, ON", 43.6205, -79.5132),
            ("Canadian Tire Gas Mississauga", "Canadian Tire", "Hurontario St, Mississauga, ON", 43.5890, -79.6441),
            ("Petro-Canada Granville", "Petro-Canada", "Granville St, Vancouver, BC", 49.2632, -123.1382),
            ("Shell Broadway", "Shell", "Broadway, Vancouver, BC", 49.2634, -123.1015),
            ("Esso Kingsway", "Esso", "Kingsway, Burnaby, BC", 49.2286, -123.0032),
            ("Ultramar Sainte-Catherine", "Ultramar", "Rue Sainte-Catherine, Montreal, QC", 45.5088, -73.5698),
            ("Petro-Canada Laurier", "Petro-Canada", "Boul Laurier, Quebec City, QC", 46.7774, -71.2756),
        ],
    }
    station_map = {}
    for code, stns in stations_data.items():
        for name, brand, addr, lat, lng in stns:
            s = Station(country_id=country_map[code].id, name=name, brand=brand,
                        address=addr, latitude=D(str(lat)), longitude=D(str(lng)), source="seed")
            db.add(s)
            await db.flush()
            station_map[(code, name)] = s

    # Seed Prices
    seed_prices = {
        "PH": {"Regular (RON 91)": D("62.50"), "Premium (RON 95)": D("68.00"),
               "Premium Plus (RON 97)": D("73.50"), "Diesel": D("55.80"), "Diesel Plus": D("60.20")},
        "CA": {"Regular 87": D("1.55"), "Mid-Grade 89": D("1.70"),
               "Premium 91-93": D("1.85"), "Diesel": D("1.60")},
    }
    price_count = 0
    for code, prices in seed_prices.items():
        for fuel_name, price in prices.items():
            ft = ft_map.get((code, fuel_name))
            if not ft:
                continue
            for key, station in station_map.items():
                if key[0] != code:
                    continue
                variation = D(str(round(random.uniform(-0.03, 0.03), 4)))
                varied = (price * (1 + variation)).quantize(D("0.01"))
                ap = ActivePrice(station_id=station.id, fuel_type_id=ft.id, price=varied, source="seed")
                db.add(ap)
                price_count += 1

    await db.commit()
    logger.info("[Admin] Seed complete: 2 countries, %d fuel types, %d stations, %d prices",
                len(ft_map), len(station_map), price_count)

    return {
        "message": "Database Seeded Successfully",
        "seeded": True,
        "countries": 2,
        "fuel_types": len(ft_map),
        "stations": len(station_map),
        "prices": price_count,
    }
