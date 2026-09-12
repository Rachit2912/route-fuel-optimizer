from typing import Any, Dict, Optional
from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult
from trips.exceptions import UnsupportedRegionError
from trips.providers.base import BaseRoutingProvider
from trips.providers.openrouteservice import OpenRouteServiceProvider
from trips.services.geocoding import GeocodingService
from trips.services.routing import RoutingService

USA_COUNTRY_NAMES = {
    "united states",
    "united states of america",
    "usa",
    "us",
}


def is_usa_location(location: ResolvedLocation) -> bool:
    if location.country:
        return location.country.strip().lower() in USA_COUNTRY_NAMES
    label_lower = location.label.lower()
    return any(name in label_lower for name in ["usa", "united states", " u.s.a.", ", us", ", usa"])


class TripOptimizationService:
    def __init__(
        self,
        provider: Optional[BaseRoutingProvider] = None,
        geocoding_service: Optional[GeocodingService] = None,
        routing_service: Optional[RoutingService] = None,
    ):
        self.provider = provider or OpenRouteServiceProvider()
        self.geocoding_service = geocoding_service or GeocodingService(self.provider)
        self.routing_service = routing_service or RoutingService(self.provider)

    def optimize_trip(self, start_input: str, finish_input: str) -> Dict[str, Any]:
        start_location = self.geocoding_service.resolve(start_input)
        finish_location = self.geocoding_service.resolve(finish_input)

        if not is_usa_location(start_location):
            raise UnsupportedRegionError(
                f"Start location '{start_input}' resolves to outside the USA."
            )

        if not is_usa_location(finish_location):
            raise UnsupportedRegionError(
                f"Finish location '{finish_input}' resolves to outside the USA."
            )

        route = self.routing_service.calculate_route(start_location, finish_location)

        return {
            "start": {
                "input": start_location.input,
                "label": start_location.label,
                "lat": start_location.lat,
                "lon": start_location.lon,
            },
            "finish": {
                "input": finish_location.input,
                "label": finish_location.label,
                "lat": finish_location.lat,
                "lon": finish_location.lon,
            },
            "route": {
                "distance_miles": route.distance_miles,
                "duration_minutes": route.duration_minutes,
                "geometry": route.geometry,
            },
        }
