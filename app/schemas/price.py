"""
Country and fuel type schemas.
"""
from pydantic import BaseModel
from typing import List, Optional


class FuelTypeResponse(BaseModel):
    id: int
    name: str
    sort_order: int

    class Config:
        from_attributes = True


class CountryResponse(BaseModel):
    id: int
    code: str
    name: str
    currency_code: str
    currency_symbol: str
    price_unit: str
    fuel_types: List[FuelTypeResponse] = []

    class Config:
        from_attributes = True


class CountryListResponse(BaseModel):
    countries: List[CountryResponse]
