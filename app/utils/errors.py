"""
Standardized error responses.
All API errors follow a consistent JSON format.
"""
from fastapi.responses import JSONResponse
from fastapi import Request
from typing import Optional


def error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[dict] = None,
) -> JSONResponse:
    """Create a standardized error response."""
    content = {
        "error": error_code,
        "message": message,
    }
    if details:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


def not_found(resource: str = "Resource") -> JSONResponse:
    return error_response(404, "not_found", f"{resource} Not Found")


def bad_request(message: str) -> JSONResponse:
    return error_response(400, "bad_request", message)


def rate_limited(retry_after: int = 360) -> JSONResponse:
    return error_response(
        429,
        "rate_limited",
        "Too Many Submissions. Please Try Again Later.",
        details={"retry_after_seconds": retry_after},
    )


def unauthorized() -> JSONResponse:
    return error_response(401, "unauthorized", "Invalid Or Missing API Key")


def validation_error(message: str, reason: str) -> JSONResponse:
    return error_response(
        422,
        "validation_error",
        message,
        details={"reason": reason},
    )
