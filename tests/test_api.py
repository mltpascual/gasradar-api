"""
API integration tests using httpx + FastAPI TestClient.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from decimal import Decimal

from app.database import Base, get_db
from app.main import app
from app.models.core import Country, FuelType, Station, ActivePrice


@pytest_asyncio.fixture
async def test_db():
    """Create an in-memory SQLite database for API testing."""
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

        active_price = ActivePrice(
            station_id=1, fuel_type_id=1, price=Decimal("62.50"),
            source="seed",
        )
        session.add(active_price)

        await session.commit()

        # Override the get_db dependency
        async def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        yield session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_check(test_db):
    """Health endpoint should return ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_countries(test_db):
    """Countries endpoint should return seeded countries."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/countries")
        assert response.status_code == 200
        data = response.json()
        assert len(data["countries"]) >= 1
        assert data["countries"][0]["code"] == "PH"


@pytest.mark.asyncio
async def test_nearby_stations(test_db):
    """Nearby stations endpoint should return stations within radius."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/stations/nearby",
            params={"lat": 14.6572, "lng": 120.9721, "radius": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert "stations" in data
        assert len(data["stations"]) >= 1


@pytest.mark.asyncio
async def test_station_detail(test_db):
    """Station detail endpoint should return station info."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/stations/1")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Shell"
        assert data["brand"] == "Shell"
        assert len(data["prices"]) >= 1


@pytest.mark.asyncio
async def test_submit_price_report(test_db):
    """Submitting a valid price should return approved status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/reports",
            json={
                "station_id": 1,
                "prices": [{"fuel_type_id": 1, "price": 63.00}],
                "device_hash": "a" * 64,
                "latitude": 14.6572,
                "longitude": 120.9721,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["reports"]) == 1
        assert data["reports"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_submit_invalid_price(test_db):
    """Submitting a price below minimum should return rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/reports",
            json={
                "station_id": 1,
                "prices": [{"fuel_type_id": 1, "price": 5.00}],
                "device_hash": "b" * 64,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reports"][0]["status"] == "rejected"
