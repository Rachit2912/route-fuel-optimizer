import math
from typing import List, Tuple

EARTH_RADIUS_MILES = 3958.8


def haversine_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculates the Great Circle / Haversine distance in miles between two (lat, lon) points."""
    lat1, lon1 = p1
    lat2, lon2 = p2

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp a to [0.0, 1.0] for floating point precision safety
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_MILES * c


def project_point_to_segment(
    p1: Tuple[float, float], p2: Tuple[float, float], station: Tuple[float, float]
) -> Tuple[float, float]:
    """
    Projects a station point (lat, lon) onto a segment p1(lat1, lon1) -> p2(lat2, lon2).
    Returns (off_route_miles, segment_along_miles).
    """
    lat1, lon1 = p1
    lat2, lon2 = p2
    lat_s, lon_s = station

    # If segment start and end are identical
    if math.isclose(lat1, lat2) and math.isclose(lon1, lon2):
        off_dist = haversine_distance(station, p1)
        return off_dist, 0.0

    lat_avg = math.radians((lat1 + lat2) / 2.0)
    cos_lat_avg = math.cos(lat_avg)

    # Convert lat/lon differences to local planar miles relative to p1
    # 1 degree latitude ~ 69.172 miles
    # 1 degree longitude ~ 69.172 * cos(lat_avg) miles
    x2 = (lon2 - lon1) * 69.172 * cos_lat_avg
    y2 = (lat2 - lat1) * 69.172

    xs = (lon_s - lon1) * 69.172 * cos_lat_avg
    ys = (lat_s - lat1) * 69.172

    l2 = x2 * x2 + y2 * y2
    if l2 == 0.0:
        off_dist = haversine_distance(station, p1)
        return off_dist, 0.0

    # Fraction t along segment [0.0, 1.0]
    t = (xs * x2 + ys * y2) / l2
    t = max(0.0, min(1.0, t))

    # Projected point in lat/lon
    lat_proj = lat1 + t * (lat2 - lat1)
    lon_proj = lon1 + t * (lon2 - lon1)
    proj_point = (lat_proj, lon_proj)

    off_route_miles = haversine_distance(station, proj_point)
    segment_along_miles = haversine_distance(p1, proj_point)

    return off_route_miles, segment_along_miles


class RouteGeometry:
    def __init__(self, coordinates: List[List[float]]):
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            raise ValueError("Route geometry must contain at least two coordinates.")

        parsed_points: List[Tuple[float, float]] = []
        for idx, coord in enumerate(coordinates):
            if not isinstance(coord, (list, tuple)) or len(coord) < 2:
                raise ValueError(f"Malformed coordinate at index {idx}: {coord}")
            try:
                lon = float(coord[0])
                lat = float(coord[1])
                parsed_points.append((lat, lon))
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid coordinate numbers at index {idx}: {coord}") from e

        self.points = parsed_points

        # Calculate cumulative distances along route once
        cum_dist = [0.0]
        for i in range(1, len(self.points)):
            dist = haversine_distance(self.points[i - 1], self.points[i])
            cum_dist.append(cum_dist[-1] + dist)

        self.cumulative_distances = cum_dist
        self.total_distance = cum_dist[-1]

        # Bounding box
        lats = [p[0] for p in self.points]
        lons = [p[1] for p in self.points]
        self.min_lat = min(lats)
        self.max_lat = max(lats)
        self.min_lon = min(lons)
        self.max_lon = max(lons)

    def find_nearest_point_on_route(
        self, lat: float, lon: float
    ) -> Tuple[float, float]:
        """
        Finds the nearest point on the route for station (lat, lon).
        Returns (off_route_miles, mile_along_route).
        """
        station = (lat, lon)
        min_off_route = float("inf")
        best_mile_along = 0.0

        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i + 1]

            off_route, seg_along = project_point_to_segment(p1, p2, station)

            if off_route < min_off_route:
                min_off_route = off_route
                best_mile_along = self.cumulative_distances[i] + seg_along

        return round(min_off_route, 2), round(best_mile_along, 2)
