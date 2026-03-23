"""
Price report submission schemas.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class PriceSubmission(BaseModel):
    fuel_type_id: int
    price: float = Field(..., gt=0)


class ReportCreateRequest(BaseModel):
    station_id: int
    prices: List[PriceSubmission] = Field(..., min_length=1)
    device_hash: str = Field(..., min_length=16, max_length=64)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)


class ReportResultItem(BaseModel):
    id: int
    fuel_type_name: str
    price: float
    status: str  # approved, needs_confirmation, rejected
    message: str


class ReportCreateResponse(BaseModel):
    reports: List[ReportResultItem]


class ReportAdminResponse(BaseModel):
    id: int
    station_id: int
    station_name: str
    fuel_type_name: str
    price: float
    status: str
    rejection_reason: Optional[str] = None
    device_hash: str
    ip_address: str
    created_at: str

    class Config:
        from_attributes = True


class ReportStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    rejection_reason: Optional[str] = None
