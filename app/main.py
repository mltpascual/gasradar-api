"""
GasRadar API — Main Application Entry Point
Crowd-sourced gas prices for the Philippines and Canada.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.utils.logging import setup_logging
from app.middleware.rate_limiter import setup_rate_limiter
from app.routers import stations, reports, countries, admin
from app.database import engine, Base
from app.models import core  # noqa: F401 — ensure all models are registered with Base

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("[API] GasRadar API starting up...")
    logger.info("[API] Version: %s", settings.APP_VERSION)
    logger.info("[API] Debug: %s", settings.DEBUG)

    # Auto-create tables on startup (safe for MVP — idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[API] Database tables ensured.")

    yield
    logger.info("[API] GasRadar API shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Crowd-sourced gas prices for the Philippines and Canada.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
setup_rate_limiter(app)

# Routers
app.include_router(stations.router)
app.include_router(reports.router)
app.include_router(countries.router)
app.include_router(admin.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Railway monitoring."""
    logger.debug("[API] Health check called")
    return {"status": "ok", "version": settings.APP_VERSION}
