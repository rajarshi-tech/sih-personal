from math import radians, sin, cos, sqrt, atan2
from typing import List

from pydantic import BaseModel


class Coordinate(BaseModel):
    latitude: float
    longitude: float


class NavigationRequest(BaseModel):
    start: Coordinate
    destination: Coordinate


def distance_km(a: Coordinate, b: Coordinate) -> float:
    R = 6371.0

    lat1 = radians(a.latitude)
    lat2 = radians(b.latitude)

    dlat = radians(b.latitude - a.latitude)
    dlon = radians(b.longitude - a.longitude)

    x = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * R * atan2(sqrt(x), sqrt(1 - x))


def generate_route(
    start: Coordinate,
    destination: Coordinate,
    points: int = 30,
) -> List[dict]:

    route = []

    for i in range(points + 1):
        t = i / points

        latitude = (
            start.latitude
            + (destination.latitude - start.latitude) * t
        )

        longitude = (
            start.longitude
            + (destination.longitude - start.longitude) * t
        )

        route.append({
            "latitude": latitude,
            "longitude": longitude,
            "status": "unknown",
        })

    return route
