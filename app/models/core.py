"""
GasRadar Database Models
All core tables: countries, fuel_types, stations, active_prices, price_reports, price_history.
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, Text,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Country(Base):
    """Region configuration for global support."""
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(2), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    currency_code = Column(String(3), nullable=False)
    currency_symbol = Column(String(5), nullable=False)
    price_unit = Column(String(20), nullable=False, default="per liter")
    min_price = Column(Numeric(10, 2), nullable=False)
    max_price = Column(Numeric(10, 2), nullable=False)
    deviation_warn_pct = Column(Integer, nullable=False, default=15)
    deviation_reject_pct = Column(Integer, nullable=False, default=30)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fuel_types = relationship("FuelType", back_populates="country")
    stations = relationship("Station", back_populates="country")


class FuelType(Base):
    """Per-country fuel type definitions."""
    __tablename__ = "fuel_types"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    name = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    country = relationship("Country", back_populates="fuel_types")


class Station(Base):
    """Gas stations."""
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    name = Column(String(200), nullable=False)
    brand = Column(String(100), nullable=False)
    address = Column(Text, nullable=True)
    latitude = Column(Numeric(10, 7), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String(20), nullable=False, default="manual")  # osm, manual, crowd
    osm_id = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    country = relationship("Country", back_populates="stations")
    active_prices = relationship("ActivePrice", back_populates="station")
    price_reports = relationship("PriceReport", back_populates="station")

    __table_args__ = (
        Index("idx_stations_geo", "latitude", "longitude"),
        Index("idx_stations_country_active", "country_id", "is_active"),
    )


class ActivePrice(Base):
    """Current visible price per station + fuel type (denormalized for fast reads)."""
    __tablename__ = "active_prices"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    fuel_type_id = Column(Integer, ForeignKey("fuel_types.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    reported_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String(20), nullable=False, default="seed")  # seed, crowd
    report_id = Column(Integer, ForeignKey("price_reports.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    station = relationship("Station", back_populates="active_prices")
    fuel_type = relationship("FuelType")

    __table_args__ = (
        UniqueConstraint("station_id", "fuel_type_id", name="uq_active_price_station_fuel"),
    )


class PriceReport(Base):
    """All anonymous submissions — the audit trail."""
    __tablename__ = "price_reports"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    fuel_type_id = Column(Integer, ForeignKey("fuel_types.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # approved, rejected, pending, needs_confirmation
    rejection_reason = Column(String(100), nullable=True)
    device_hash = Column(String(64), nullable=False)
    ip_address = Column(String(45), nullable=False)  # supports IPv6
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    confirmed_by_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True), nullable=True)

    station = relationship("Station", back_populates="price_reports")
    fuel_type = relationship("FuelType")

    __table_args__ = (
        Index("idx_reports_station_fuel_status", "station_id", "fuel_type_id", "status"),
        Index("idx_reports_device_hash", "device_hash"),
    )


class PriceHistory(Base):
    """Log of every active price change."""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    fuel_type_id = Column(Integer, ForeignKey("fuel_types.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    source = Column(String(20), nullable=False)  # seed, crowd
    report_id = Column(Integer, ForeignKey("price_reports.id"), nullable=True)
    effective_from = Column(DateTime(timezone=True), server_default=func.now())
    effective_until = Column(DateTime(timezone=True), nullable=True)  # NULL = still current
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_history_station_fuel", "station_id", "fuel_type_id"),
    )
