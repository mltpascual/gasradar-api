"""
Stations Router — public endpoints for browsing stations and prices.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.station_service import get_nearby_stations, get_station_detail
from app.services.price_service import get_price_history
from app.utils.errors import not_found

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stations", tags=["Stations"])


@router.get("/nearby")
async def nearby_stations(
    lat: float = Query(..., ge=-90, le=90, description="User latitude"),
    lng: float = Query(..., ge=-180, le=180, description="User longitude"),
    radius: int = Query(5, ge=1, le=50, description="Search radius in km"),
    country_code: Optional[str] = Query(None, min_length=2, max_length=2, description="Country code (PH, CA)"),
    fuel_type_id: Optional[int] = Query(None, description="Filter by fuel type"),
    sort: str = Query("distance", pattern="^(distance|price)$", description="Sort by distance or price"),
    db: AsyncSession = Depends(get_db),
):
    """Get nearby gas stations with their current approved prices."""
    logger.info("[API] GET /stations/nearby lat=%s lng=%s radius=%d", lat, lng, radius)
    result = await get_nearby_stations(
        db=db,
        lat=lat,
        lng=lng,
        radius_km=radius,
        country_code=country_code,
        fuel_type_id=fuel_type_id,
        sort_by=sort,
    )
    return result


@router.get("/{station_id}")
async def station_detail(
    station_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information for a specific gas station."""
    logger.info("[API] GET /stations/%d", station_id)
    result = await get_station_detail(db=db, station_id=station_id)
    if result is None:
        return not_found("Station")
    return result


@router.get("/{station_id}/history")
async def station_price_history(
    station_id: int,
    fuel_type_id: Optional[int] = Query(None, description="Filter by fuel type"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get price history for a gas station."""
    logger.info("[API] GET /stations/%d/history", station_id)
    history = await get_price_history(
        db=db,
        station_id=station_id,
        fuel_type_id=fuel_type_id,
        limit=limit,
    )
    return {"history": history}
