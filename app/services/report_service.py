"""
Report Service — processes anonymous price submissions.
Orchestrates validation, creates reports, and updates active prices.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Station, FuelType, ActivePrice, PriceReport, PriceHistory
from app.services.validation_service import validate_price_report, ValidationResult

logger = logging.getLogger(__name__)


async def process_price_reports(
    db: AsyncSession,
    station_id: int,
    prices: List[dict],
    device_hash: str,
    ip_address: str,
    reporter_lat: float = None,
    reporter_lng: float = None,
) -> List[dict]:
    """
    Process a batch of price submissions for a single station.
    Each price goes through the validation pipeline independently.
    Returns a list of results per fuel type.
    """
    logger.info("[Report] Processing %d price reports for station=%d from device=%s",
                len(prices), station_id, device_hash[:8])

    results = []

    for price_entry in prices:
        fuel_type_id = price_entry["fuel_type_id"]
        price = price_entry["price"]

        # Run validation pipeline
        validation = await validate_price_report(
            db=db,
            station_id=station_id,
            fuel_type_id=fuel_type_id,
            price=price,
            device_hash=device_hash,
            ip_address=ip_address,
        )

        # Create the price report record (always, even if rejected)
        report = PriceReport(
            station_id=station_id,
            fuel_type_id=fuel_type_id,
            price=Decimal(str(price)),
            status=validation.status,
            rejection_reason=validation.reason if validation.status == "rejected" else None,
            device_hash=device_hash,
            ip_address=ip_address,
            latitude=Decimal(str(reporter_lat)) if reporter_lat else None,
            longitude=Decimal(str(reporter_lng)) if reporter_lng else None,
            validated_at=datetime.now(timezone.utc) if validation.status != "pending" else None,
        )
        db.add(report)
        await db.flush()  # Get the report ID

        logger.info("[Report] Report #%d: fuel=%d price=%s status=%s",
                     report.id, fuel_type_id, price, validation.status)

        # If approved, update active price and create history entry
        if validation.status == "approved":
            await _update_active_price(db, station_id, fuel_type_id, price, report.id)

        # Get fuel type name for response
        fuel_type = await db.get(FuelType, fuel_type_id)
        fuel_type_name = fuel_type.name if fuel_type else "Unknown"

        results.append({
            "id": report.id,
            "fuel_type_name": fuel_type_name,
            "price": price,
            "status": validation.status,
            "message": validation.message,
        })

    await db.commit()
    logger.info("[Report] Batch complete: %d reports processed", len(results))
    return results


async def _update_active_price(
    db: AsyncSession,
    station_id: int,
    fuel_type_id: int,
    price: float,
    report_id: int,
):
    """Update the active price for a station + fuel type and log history."""
    now = datetime.now(timezone.utc)
    price_decimal = Decimal(str(price))

    # Find existing active price
    result = await db.execute(
        select(ActivePrice).where(
            and_(
                ActivePrice.station_id == station_id,
                ActivePrice.fuel_type_id == fuel_type_id,
            )
        )
    )
    active_price = result.scalar_one_or_none()

    if active_price:
        # Close out the old price history entry
        old_history = await db.execute(
            select(PriceHistory).where(
                and_(
                    PriceHistory.station_id == station_id,
                    PriceHistory.fuel_type_id == fuel_type_id,
                    PriceHistory.effective_until.is_(None),
                )
            )
        )
        old_entry = old_history.scalar_one_or_none()
        if old_entry:
            old_entry.effective_until = now

        # Update active price
        active_price.price = price_decimal
        active_price.reported_at = now
        active_price.source = "crowd"
        active_price.report_id = report_id
        active_price.updated_at = now
        logger.info("[Price] Updated active price: station=%d fuel=%d price=%s",
                     station_id, fuel_type_id, price)
    else:
        # Create new active price
        active_price = ActivePrice(
            station_id=station_id,
            fuel_type_id=fuel_type_id,
            price=price_decimal,
            reported_at=now,
            source="crowd",
            report_id=report_id,
        )
        db.add(active_price)
        logger.info("[Price] Created new active price: station=%d fuel=%d price=%s",
                     station_id, fuel_type_id, price)

    # Create new history entry
    history = PriceHistory(
        station_id=station_id,
        fuel_type_id=fuel_type_id,
        price=price_decimal,
        source="crowd",
        report_id=report_id,
        effective_from=now,
    )
    db.add(history)
