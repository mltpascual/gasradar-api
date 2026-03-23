"""
Rate limiting middleware using slowapi.
Limits anonymous submissions by IP address.
Device-level rate limiting is handled in the report service.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    logger.warning("[RateLimit] Rate limit exceeded for IP: %s", get_remote_address(request))
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": "Too Many Submissions. Please Try Again Later.",
            "retry_after_seconds": 360,
        },
    )


def setup_rate_limiter(app: FastAPI):
    """Attach rate limiter to the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    logger.info("[RateLimit] Rate limiter initialized")
