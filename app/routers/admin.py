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
