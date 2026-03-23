"""
Common Pydantic schemas shared across the API.
"""
from pydantic import BaseModel
from typing import Optional


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[dict] = None


class HealthResponse(BaseModel):
    status: str
