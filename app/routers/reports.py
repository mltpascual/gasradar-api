"""
Reports Router — anonymous price submission endpoint.
"""
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.report import ReportCreateRequest, ReportCreateResponse
from app.services.report_service import process_price_reports
from app.middleware.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.post("", response_model=ReportCreateResponse)
@limiter.limit("30/hour")
async def submit_price_report(
    request: Request,
    body: ReportCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit anonymous price report(s) for a gas station.
    Supports multiple fuel types per submission.
    """
    ip_address = request.client.host if request.client else "unknown"
    logger.info("[API] POST /reports from device=%s ip=%s station=%d prices=%d",
                body.device_hash[:8], ip_address, body.station_id, len(body.prices))

    results = await process_price_reports(
        db=db,
        station_id=body.station_id,
        prices=[{"fuel_type_id": p.fuel_type_id, "price": p.price} for p in body.prices],
        device_hash=body.device_hash,
        ip_address=ip_address,
        reporter_lat=body.latitude,
        reporter_lng=body.longitude,
    )

    return ReportCreateResponse(reports=results)
