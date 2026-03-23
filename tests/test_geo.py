"""
Tests for the geo utility (Haversine distance).
"""
import pytest
from app.utils.geo import haversine_distance


def test_same_point():
    """Distance between the same point should be 0."""
    dist = haversine_distance(14.5995, 120.9842, 14.5995, 120.9842)
    assert dist == 0.0


def test_known_distance_manila_to_makati():
    """Distance from Manila City Hall to Makati (~7-8km)."""
    dist = haversine_distance(14.5995, 120.9842, 14.5547, 121.0244)
    assert 5.0 < dist < 10.0  # Roughly 7km


def test_known_distance_toronto_to_vancouver():
    """Distance from Toronto to Vancouver (~3,360km)."""
    dist = haversine_distance(43.6532, -79.3832, 49.2827, -123.1207)
    assert 3300 < dist < 3500


def test_short_distance():
    """Two points ~1km apart."""
    # ~1km north of a point at equator
    dist = haversine_distance(0.0, 0.0, 0.009, 0.0)
    assert 0.9 < dist < 1.1


def test_antipodal_points():
    """Distance between antipodal points should be roughly half Earth circumference."""
    dist = haversine_distance(0.0, 0.0, 0.0, 180.0)
    assert 20000 < dist < 20100  # ~20,015km
