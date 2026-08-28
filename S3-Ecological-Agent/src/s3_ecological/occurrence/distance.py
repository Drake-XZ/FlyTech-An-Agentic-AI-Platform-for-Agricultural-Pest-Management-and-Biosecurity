"""Great-circle distance (EarlyDesign.md Profile v0.1, geographic baseline step 2)."""

from __future__ import annotations

import math

# Earth mean radius, frozen by Prototype Implementation Profile v0.1.
EARTH_MEAN_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    central_angle = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_MEAN_RADIUS_KM * central_angle
