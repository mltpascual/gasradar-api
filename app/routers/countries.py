"""
Countries Router — list supported countries and fuel types.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.core import Country, FuelType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Countries"])


@router.get("/countries")
async def list_countries(db: AsyncSession = Depends(get_db)):
    """List all supported countries with their configurations."""
    logger.info("[API] GET /countries")

    result = await db.execute(select(Country).order_by(Country.name))
    countries = result.scalars().all()

    response = []
    for country in countries:
        # Fetch fuel types for this country
        ft_result = await db.execute(
            select(FuelType)
            .where(FuelType.country_id == country.id, FuelType.is_active == True)
            .order_by(FuelType.sort_order)
        )
        fuel_types = ft_result.scalars().all()

        response.append({
            "id": country.id,
            "code": country.code,
            "name": country.name,
            "currency_code": country.currency_code,
            "currency_symbol": country.currency_symbol,
            "price_unit": country.price_unit,
            "fuel_types": [
                {"id": ft.id, "name": ft.name, "sort_order": ft.sort_order}
                for ft in fuel_types
            ],
        })

    return {"countries": response}


@router.get("/fuel-types")
async def list_fuel_types(
    country_code: Optional[str] = Query(None, min_length=2, max_length=2),
    db: AsyncSession = Depends(get_db),
):
    """List fuel types, optionally filtered by country."""
    logger.info("[API] GET /fuel-types country=%s", country_code)

    query = select(FuelType).where(FuelType.is_active == True)

    if country_code:
        country_result = await db.execute(
            select(Country).where(Country.code == country_code.upper())
        )
        country = country_result.scalar_one_or_none()
        if country:
            query = query.where(FuelType.country_id == country.id)

    query = query.order_by(FuelType.sort_order)
    result = await db.execute(query)
    fuel_types = result.scalars().all()

    return {
        "fuel_types": [
            {"id": ft.id, "name": ft.name, "sort_order": ft.sort_order}
            for ft in fuel_types
        ]
    }
