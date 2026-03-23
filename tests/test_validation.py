"""
Tests for the validation service.
Uses aiosqlite for in-memory testing without PostgreSQL.
"""
import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base
from app.models.core import Country, FuelType, Station, ActivePrice, PriceReport
from app.services.validation_service import validate_price_report


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Seed test data
        country = Country(
            id=1, code="PH", name="Philippines",
            currency_code="PHP", currency_symbol="₱",
            price_unit="per liter",
            min_price=Decimal("20.00"), max_price=Decimal("200.00"),
            deviation_warn_pct=15, deviation_reject_pct=30,
        )
        session.add(country)

        fuel_type = FuelType(id=1, country_id=1, name="Regular (RON 91)", sort_order=1)
        session.add(fuel_type)

        station = Station(
            id=1, country_id=1, name="Test Shell", brand="Shell",
            address="Test Address", latitude=Decimal("14.6572"), longitude=Decimal("120.9721"),
            source="seed",
        )
        session.add(station)

        # Seed an active price
        active_price = ActivePrice(
            station_id=1, fuel_type_id=1, price=Decimal("62.50"),
            source="seed",
        )
        session.add(active_price)

        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_valid_price_within_range(db_session):
    """A price within ±15% of the current price should be auto-approved."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=64.00,  # ~2.4% deviation — within 15%
        device_hash="a" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "approved"


@pytest.mark.asyncio
async def test_price_below_minimum(db_session):
    """A price below the country minimum should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=10.00,  # Below ₱20 minimum
        device_hash="b" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "rejected"
    assert result.reason == "below_minimum"


@pytest.mark.asyncio
async def test_price_above_maximum(db_session):
    """A price above the country maximum should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=250.00,  # Above ₱200 maximum
        device_hash="c" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "rejected"
    assert result.reason == "above_maximum"


@pytest.mark.asyncio
async def test_excessive_deviation(db_session):
    """A price deviating >30% from current should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=100.00,  # ~60% deviation from 62.50
        device_hash="d" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "rejected"
    assert result.reason == "excessive_deviation"


@pytest.mark.asyncio
async def test_needs_confirmation_deviation(db_session):
    """A price deviating 15-30% should need confirmation."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=75.00,  # ~20% deviation from 62.50
        device_hash="e" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "needs_confirmation"


@pytest.mark.asyncio
async def test_invalid_station(db_session):
    """A submission for a non-existent station should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=999,
        fuel_type_id=1,
        price=62.00,
        device_hash="f" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "rejected"
    assert result.reason == "invalid_station"


@pytest.mark.asyncio
async def test_invalid_fuel_type(db_session):
    """A submission for a non-existent fuel type should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=999,
        price=62.00,
        device_hash="g" * 64,
        ip_address="127.0.0.1",
    )
    assert result.status == "rejected"
    assert result.reason == "invalid_fuel_type"


@pytest.mark.asyncio
async def test_junk_value(db_session):
    """Suspicious junk values should be rejected."""
    result = await validate_price_report(
        db=db_session,
        station_id=1,
        fuel_type_id=1,
        price=99999.00,
        device_hash="h" * 64,
        ip_address="127.0.0.1",
    )
    # 99999 is above max, so it should be rejected for above_maximum
    assert result.status == "rejected"
