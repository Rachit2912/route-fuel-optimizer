import math
from typing import List, Optional

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

    def match_stations_to_route(
        self,
        route_coordinates: List[List[float]],
        stations: Optional[List[FuelStation]] = None,
    ) -> List[MatchedStation]:
        if not route_coordinates:
            return []

        route_geom = RouteGeometry(route_coordinates)

        if stations is None:
            stations = self.repository.list_geocoded_stations()

        if not stations:
            return []

        # Cheap spatial prefilter: bounding box expanded by corridor margin
        avg_lat = (route_geom.min_lat + route_geom.max_lat) / 2.0
        cos_avg_lat = max(0.1, math.cos(math.radians(avg_lat)))

        lat_margin = (self.corridor_miles / 69.0) + 0.05
        lon_margin = (self.corridor_miles / (69.0 * cos_avg_lat)) + 0.05

        bbox_min_lat = route_geom.min_lat - lat_margin
        bbox_max_lat = route_geom.max_lat + lat_margin
        bbox_min_lon = route_geom.min_lon - lon_margin
        bbox_max_lon = route_geom.max_lon + lon_margin

        matched_candidates: List[MatchedStation] = []

        for st in stations:
            if st.latitude is None or st.longitude is None:
                continue

            # Bounding box test
            if not (
                bbox_min_lat <= st.latitude <= bbox_max_lat
                and bbox_min_lon <= st.longitude <= bbox_max_lon
            ):
                continue

            off_route_miles, mile_along_route = route_geom.find_nearest_point_on_route(
                st.latitude, st.longitude
            )

            # Corridor check: off_route_miles <= corridor_miles
            if off_route_miles <= self.corridor_miles:
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

        # Sort candidate stations by mile_along_route ASC
        matched_candidates.sort(key=lambda x: (x.mile_along_route, x.opis_id))
        return matched_candidates
