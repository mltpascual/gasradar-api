"""
Price Service — handles price history and active price queries.
"""
import logging
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import PriceHistory, FuelType

logger = logging.getLogger(__name__)


async def get_price_history(
    db: AsyncSession,
    station_id: int,
    fuel_type_id: Optional[int] = None,
    limit: int = 50,
) -> List[dict]:
    """Get price history for a station, optionally filtered by fuel type."""
    logger.info("[Price] Fetching history for station=%d", station_id)

    query = (
        select(PriceHistory, FuelType)
        .join(FuelType, PriceHistory.fuel_type_id == FuelType.id)
        .where(PriceHistory.station_id == station_id)
    )

    if fuel_type_id:
        query = query.where(PriceHistory.fuel_type_id == fuel_type_id)

    query = query.order_by(PriceHistory.effective_from.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    history = []
    for ph, ft in rows:
        history.append({
            "id": ph.id,
            "fuel_type_id": ft.id,
            "fuel_type_name": ft.name,
            "price": float(ph.price),
            "source": ph.source,
            "effective_from": ph.effective_from.isoformat() if ph.effective_from else None,
            "effective_until": ph.effective_until.isoformat() if ph.effective_until else None,
        })

    return history
