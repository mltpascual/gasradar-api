"""
Station-related Pydantic schemas.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class PriceResponse(BaseModel):
    fuel_type_id: int
    fuel_type_name: str
    price: float
    currency: str
    freshness: str  # just_updated, recent, this_week, may_be_outdated
    reported_at: Optional[datetime] = None
    report_count_24h: Optional[int] = None

    class Config:
        from_attributes = True


class StationListItem(BaseModel):
    id: int
    name: str
    brand: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    distance_km: float
    prices: List[PriceResponse] = []

    class Config:
        from_attributes = True


class StationDetail(BaseModel):
    id: int
    name: str
    brand: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    country_code: str
    prices: List[PriceResponse] = []
    recent_activity: Optional[dict] = None

    class Config:
        from_attributes = True


class NearbyStationsResponse(BaseModel):
    stations: List[StationListItem]
    meta: dict


class StationCreateRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    name: str = Field(..., min_length=1, max_length=200)
    brand: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class StationUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    brand: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None
