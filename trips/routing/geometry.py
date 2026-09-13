from dataclasses import dataclass
import math
from typing import List, Optional, Tuple

EARTH_RADIUS_MILES = 3958.8
CHUNK_SIZE = 32


@dataclass(frozen=True)
class RouteChunk:
    start_seg_idx: int
    end_seg_idx: int
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


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
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid coordinate numbers at index {idx}: {coord}") from e

            if not math.isfinite(lon) or not math.isfinite(lat):
                raise ValueError(f"Non-finite coordinate at index {idx}: {coord}")

            if not (-180.0 <= lon <= 180.0):
                raise ValueError(f"Longitude out of range [-180, 180] at index {idx}: {lon}")

            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude out of range [-90, 90] at index {idx}: {lat}")

            parsed_points.append((lat, lon))

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

        # Split segments into contiguous chunks
        num_segments = len(self.points) - 1
        chunks: List[RouteChunk] = []

        for start_idx in range(0, num_segments, CHUNK_SIZE):
            end_idx = min(start_idx + CHUNK_SIZE - 1, num_segments - 1)
            chunk_pts = self.points[start_idx : end_idx + 2]
            c_lats = [p[0] for p in chunk_pts]
            c_lons = [p[1] for p in chunk_pts]
            chunks.append(
                RouteChunk(
                    start_seg_idx=start_idx,
                    end_seg_idx=end_idx,
                    min_lat=min(c_lats),
                    max_lat=max(c_lats),
                    min_lon=min(c_lons),
                    max_lon=max(c_lons),
                )
            )

        self.chunks = chunks

    def find_nearest_point_within_corridor(
        self, lat: float, lon: float, corridor_miles: float
    ) -> Tuple[Optional[Tuple[float, float]], int]:
        """
        Finds nearest point on route within corridor_miles using chunk bounding box index.
        Returns ((off_route_miles, mile_along_route), segment_comparisons_count).
        If off_route_miles > corridor_miles or no candidate chunk matches, result tuple is None.
        """
        max_abs_lat = max(abs(self.min_lat), abs(self.max_lat))
        max_abs_lat = min(89.9, max_abs_lat)
        cos_max_abs_lat = max(0.001, math.cos(math.radians(max_abs_lat)))

        lat_margin = (corridor_miles / 69.0) + 0.001
        lon_margin = (corridor_miles / (69.0 * cos_max_abs_lat)) + 0.001

        candidate_chunks = [
            c
            for c in self.chunks
            if (c.min_lat - lat_margin <= lat <= c.max_lat + lat_margin)
            and (c.min_lon - lon_margin <= lon <= c.max_lon + lon_margin)
        ]

        if not candidate_chunks:
            return None, 0

        station = (lat, lon)
        min_off_route = float("inf")
        best_mile_along = 0.0
        comparisons_performed = 0

        for chunk in candidate_chunks:
            for i in range(chunk.start_seg_idx, chunk.end_seg_idx + 1):
                comparisons_performed += 1
                p1 = self.points[i]
                p2 = self.points[i + 1]

                off_route, seg_along = project_point_to_segment(p1, p2, station)

                if off_route < min_off_route:
                    min_off_route = off_route
                    best_mile_along = self.cumulative_distances[i] + seg_along

        if min_off_route <= corridor_miles:
            return (min_off_route, best_mile_along), comparisons_performed
        return None, comparisons_performed

    def find_nearest_point_on_route(
        self, lat: float, lon: float
    ) -> Tuple[float, float]:
        """
        Brute-force scan across all segments.
        Returns raw full-precision (off_route_miles, mile_along_route).
        """
        res, _ = self.find_nearest_point_within_corridor(lat, lon, float("inf"))
        assert res is not None
        return res
