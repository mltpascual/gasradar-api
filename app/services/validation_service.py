"""
Validation Service — 6-step pipeline for anonymous price reports.

Step 1: Input Sanitization
Step 2: Absolute Range Check (per country)
Step 3: Deviation Check (against last approved price)
Step 4: Rate Limit Check (device + IP)
Step 5: Passive Confirmation (matching pending reports)
Step 6: Final Decision
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Country, FuelType, Station, ActivePrice, PriceReport

logger = logging.getLogger(__name__)

# Junk value patterns
JUNK_VALUES = {Decimal("99999"), Decimal("11111"), Decimal("0.01"), Decimal("0.1")}


class ValidationResult:
    """Result of the validation pipeline."""

    def __init__(self, status: str, reason: Optional[str] = None, message: Optional[str] = None):
        self.status = status  # approved, rejected, needs_confirmation
        self.reason = reason
        self.message = message or self._default_message()

    def _default_message(self) -> str:
        messages = {
            "approved": "Price Updated. Thanks!",
            "needs_confirmation": "Submitted. Awaiting Confirmation.",
            "rejected": f"Submission Rejected: {self.reason or 'Unknown'}",
        }
        return messages.get(self.status, "Unknown Status")


async def validate_price_report(
    db: AsyncSession,
    station_id: int,
    fuel_type_id: int,
    price: float,
    device_hash: str,
    ip_address: str,
) -> ValidationResult:
    """
    Run the full 6-step validation pipeline on a price submission.
    Returns a ValidationResult with status and reason.
    """
    price_decimal = Decimal(str(price))

    # Step 1: Input Sanitization
    logger.info("[Validation] Step 1: Input sanitization for station=%d fuel=%d price=%s", station_id, fuel_type_id, price)

    station = await db.get(Station, station_id)
    if not station or not station.is_active:
        logger.warning("[Validation] Invalid station_id=%d", station_id)
        return ValidationResult("rejected", "invalid_station", "Station Not Found")

    fuel_type = await db.get(FuelType, fuel_type_id)
    if not fuel_type or not fuel_type.is_active or fuel_type.country_id != station.country_id:
        logger.warning("[Validation] Invalid fuel_type_id=%d for station country", fuel_type_id)
        return ValidationResult("rejected", "invalid_fuel_type", "Invalid Fuel Type For This Station")

    country = await db.get(Country, station.country_id)
    if not country:
        return ValidationResult("rejected", "invalid_country", "Country Configuration Not Found")

    # Step 2: Absolute Range Check
    logger.info("[Validation] Step 2: Range check — price=%s, min=%s, max=%s", price_decimal, country.min_price, country.max_price)

    if price_decimal < country.min_price:
        return ValidationResult("rejected", "below_minimum", "Price Is Below Minimum Expected Range")

    if price_decimal > country.max_price:
        return ValidationResult("rejected", "above_maximum", "Price Is Above Maximum Expected Range")

    if price_decimal in JUNK_VALUES:
        return ValidationResult("rejected", "junk_value", "Suspicious Price Value Detected")

    # Step 3: Deviation Check
    logger.info("[Validation] Step 3: Deviation check")

    last_approved = await _get_last_approved_price(db, station_id, fuel_type_id)

    if last_approved is not None:
        deviation_pct = abs(float(price_decimal - last_approved) / float(last_approved)) * 100
        logger.info("[Validation] Deviation: %.1f%% (warn=%d%%, reject=%d%%)",
                     deviation_pct, country.deviation_warn_pct, country.deviation_reject_pct)

        if deviation_pct > country.deviation_reject_pct:
            return ValidationResult("rejected", "excessive_deviation",
                                    f"Price Deviates Too Much From Current Price ({deviation_pct:.0f}%)")

        if deviation_pct > country.deviation_warn_pct:
            # Check passive confirmation (Step 5 early)
            confirmed = await _check_passive_confirmation(db, station_id, fuel_type_id, price_decimal)
            if confirmed:
                logger.info("[Validation] Passive confirmation found — approving")
                return ValidationResult("approved")
            return ValidationResult("needs_confirmation")

    # Step 4: Rate Limit Check (device-level)
    logger.info("[Validation] Step 4: Rate limit check for device=%s", device_hash[:8])

    rate_limited, rate_reason = await _check_rate_limits(db, device_hash, ip_address, station_id)
    if rate_limited:
        return ValidationResult("rejected", "rate_limited", rate_reason)

    # Step 5: Passive Confirmation (for first-time prices or within-range prices)
    if last_approved is not None:
        confirmed = await _check_passive_confirmation(db, station_id, fuel_type_id, price_decimal)
        if confirmed:
            logger.info("[Validation] Passive confirmation matched — approving")

    # Step 6: Final Decision — if we got here, it's approved
    logger.info("[Validation] Step 6: Final decision — APPROVED")
    return ValidationResult("approved")


async def _get_last_approved_price(
    db: AsyncSession, station_id: int, fuel_type_id: int
) -> Optional[Decimal]:
    """Get the last approved price for a station + fuel type."""
    result = await db.execute(
        select(ActivePrice.price).where(
            and_(
                ActivePrice.station_id == station_id,
                ActivePrice.fuel_type_id == fuel_type_id,
            )
        )
    )
    row = result.scalar_one_or_none()
    return row


async def _check_rate_limits(
    db: AsyncSession, device_hash: str, ip_address: str, station_id: int
) -> Tuple[bool, str]:
    """Check device and IP rate limits. Returns (is_limited, reason)."""
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    # Device hourly limit: max 10 submissions per hour
    device_hourly = await db.execute(
        select(func.count()).select_from(PriceReport).where(
            and_(
                PriceReport.device_hash == device_hash,
                PriceReport.created_at >= one_hour_ago,
            )
        )
    )
    if device_hourly.scalar() >= 10:
        logger.warning("[Validation] Device hourly rate limit exceeded: %s", device_hash[:8])
        return True, "Too Many Submissions This Hour. Please Try Again Later."

    # Device per-station daily limit: max 3 per station per day
    device_station_daily = await db.execute(
        select(func.count()).select_from(PriceReport).where(
            and_(
                PriceReport.device_hash == device_hash,
                PriceReport.station_id == station_id,
                PriceReport.created_at >= one_day_ago,
            )
        )
    )
    if device_station_daily.scalar() >= 3:
        logger.warning("[Validation] Device per-station daily limit exceeded: %s station=%d", device_hash[:8], station_id)
        return True, "You Have Already Submitted Prices For This Station Today."

    # IP hourly limit: max 30 per hour
    ip_hourly = await db.execute(
        select(func.count()).select_from(PriceReport).where(
            and_(
                PriceReport.ip_address == ip_address,
                PriceReport.created_at >= one_hour_ago,
            )
        )
    )
    if ip_hourly.scalar() >= 30:
        logger.warning("[Validation] IP hourly rate limit exceeded: %s", ip_address)
        return True, "Too Many Submissions From This Network. Please Try Again Later."

    return False, ""


async def _check_passive_confirmation(
    db: AsyncSession, station_id: int, fuel_type_id: int, price: Decimal
) -> bool:
    """
    Check if there's a pending report with a similar price (within ±5%).
    If found, increment its confirmed_by_count and auto-approve if threshold met.
    """
    tolerance = float(price) * 0.05
    lower = float(price) - tolerance
    upper = float(price) + tolerance

    result = await db.execute(
        select(PriceReport).where(
            and_(
                PriceReport.station_id == station_id,
                PriceReport.fuel_type_id == fuel_type_id,
                PriceReport.status == "needs_confirmation",
                PriceReport.price >= Decimal(str(lower)),
                PriceReport.price <= Decimal(str(upper)),
            )
        ).order_by(PriceReport.created_at.desc()).limit(1)
    )
    pending_report = result.scalar_one_or_none()

    if pending_report:
        pending_report.confirmed_by_count += 1
        if pending_report.confirmed_by_count >= 1:
            pending_report.status = "approved"
            pending_report.validated_at = datetime.now(timezone.utc)
            logger.info("[Validation] Passive confirmation: report=%d now approved (count=%d)",
                        pending_report.id, pending_report.confirmed_by_count)
            await db.flush()
            return True

    return False
