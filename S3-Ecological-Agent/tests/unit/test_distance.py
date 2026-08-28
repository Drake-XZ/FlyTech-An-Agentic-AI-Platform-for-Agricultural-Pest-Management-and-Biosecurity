"""Unit tests for the haversine great-circle distance baseline."""

from __future__ import annotations

import math

from s3_ecological.occurrence.distance import EARTH_MEAN_RADIUS_KM, haversine_km


def test_distance_between_identical_points_is_zero():
    assert haversine_km(10.0, 20.0, 10.0, 20.0) == 0.0


def test_distance_for_quarter_great_circle_matches_expected_arc_length():
    # (0, 0) to (0, 90) is a quarter of the equatorial great circle.
    expected = (math.pi / 2) * EARTH_MEAN_RADIUS_KM
    assert math.isclose(haversine_km(0.0, 0.0, 0.0, 90.0), expected, rel_tol=1e-9)


def test_distance_for_antipodal_points_is_half_circumference():
    expected = math.pi * EARTH_MEAN_RADIUS_KM
    assert math.isclose(haversine_km(0.0, 0.0, 0.0, 180.0), expected, rel_tol=1e-9)


def test_distance_is_symmetric():
    forward = haversine_km(-33.8, 151.2, 40.7, -74.0)
    backward = haversine_km(40.7, -74.0, -33.8, 151.2)
    assert math.isclose(forward, backward, rel_tol=1e-12)


def test_distance_is_never_negative():
    assert haversine_km(5.0, 5.0, -5.0, -5.0) > 0.0
