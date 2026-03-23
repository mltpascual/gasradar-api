"""
Geolocation utilities.
Haversine formula for distance calculation between two lat/lng points.
"""
import math
import logging

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth
    using the Haversine formula.

    Returns distance in kilometers.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def haversine_sql_expression(lat: float, lng: float) -> str:
    """
    Returns a SQL expression for calculating Haversine distance.
    Used in ORDER BY and WHERE clauses for nearby station queries.

    Usage:
        distance_expr = haversine_sql_expression(user_lat, user_lng)
        query = f"SELECT *, {distance_expr} AS distance_km FROM stations ORDER BY distance_km"
    """
    return f"""
    (
        {EARTH_RADIUS_KM} * 2 * ASIN(
            SQRT(
                POWER(SIN(RADIANS(latitude - {lat}) / 2), 2) +
                COS(RADIANS({lat})) * COS(RADIANS(latitude)) *
                POWER(SIN(RADIANS(longitude - {lng}) / 2), 2)
            )
        )
    )
    """
