import math
from typing import Dict, List, Optional

from trips.domain.station import MatchedStation
from trips.models import FuelStation
from trips.routing.geometry import RouteGeometry
from trips.station_data.repository import FuelStationRepository

DEFAULT_CORRIDOR_MILES = 10.0


class RouteStationMatcher:
    def __init__(
        self,
        corridor_miles: float = DEFAULT_CORRIDOR_MILES,
        repository: Optional[FuelStationRepository] = None,
    ):
        self.corridor_miles = corridor_miles
        self.repository = repository or FuelStationRepository()
        self.last_stats: Dict[str, int] = {
            "stations_loaded": 0,
            "surviving_global_bbox": 0,
            "exact_segment_comparisons": 0,
            "matched_stations": 0,
        }

    def match_stations_to_route(
        self,
        route_coordinates: List[List[float]],
        stations: Optional[List[FuelStation]] = None,
    ) -> List[MatchedStation]:
        route_geom = RouteGeometry(route_coordinates)

        if stations is None:
            stations = self.repository.list_geocoded_stations()

        self.last_stats["stations_loaded"] = len(stations)

        if not stations:
            self.last_stats["surviving_global_bbox"] = 0
            self.last_stats["exact_segment_comparisons"] = 0
            self.last_stats["matched_stations"] = 0
            return []

        # Cheap spatial prefilter: conservative global bounding box expansion
        max_abs_lat = max(abs(route_geom.min_lat), abs(route_geom.max_lat))
        max_abs_lat = min(89.9, max_abs_lat)
        cos_max_abs_lat = max(0.001, math.cos(math.radians(max_abs_lat)))

        lat_margin = (self.corridor_miles / 69.0) + 0.001
        lon_margin = (self.corridor_miles / (69.0 * cos_max_abs_lat)) + 0.001

        bbox_min_lat = route_geom.min_lat - lat_margin
        bbox_max_lat = route_geom.max_lat + lat_margin
        bbox_min_lon = route_geom.min_lon - lon_margin
        bbox_max_lon = route_geom.max_lon + lon_margin

        surviving_global_bbox = 0
        total_comparisons = 0
        matched_candidates: List[MatchedStation] = []

        for st in stations:
            if st.latitude is None or st.longitude is None:
                continue

            # Global bounding box test
            if not (
                bbox_min_lat <= st.latitude <= bbox_max_lat
                and bbox_min_lon <= st.longitude <= bbox_max_lon
            ):
                continue

            surviving_global_bbox += 1

            result, comparisons = route_geom.find_nearest_point_within_corridor(
                st.latitude, st.longitude, self.corridor_miles
            )
            total_comparisons += comparisons

            if result is not None:
                off_route_miles, mile_along_route = result
                matched_candidates.append(
                    MatchedStation(
                        opis_id=st.opis_id,
                        name=st.name,
                        latitude=st.latitude,
                        longitude=st.longitude,
                        effective_price=st.effective_price,
                        mile_along_route=mile_along_route,
                        off_route_miles=off_route_miles,
                        geocode_source=st.geocode_source,
                        geocode_precision=st.geocode_precision,
                    )
                )

        # Sort candidate stations by raw mile_along_route ASC
        matched_candidates.sort(key=lambda x: (x.mile_along_route, x.opis_id))

        self.last_stats["surviving_global_bbox"] = surviving_global_bbox
        self.last_stats["exact_segment_comparisons"] = total_comparisons
        self.last_stats["matched_stations"] = len(matched_candidates)

        return matched_candidates
