from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from trips.domain.location import ResolvedLocation
from trips.exceptions import StationDataUnavailableError, UnsupportedRegionError
from trips.providers.base import BaseRoutingProvider
from trips.providers.openrouteservice import OpenRouteServiceProvider
from trips.routing.station_matcher import RouteStationMatcher
from trips.services.fuel_optimizer import FuelOptimizer
from trips.services.geocoding import GeocodingService
from trips.services.routing import RoutingService
from trips.station_data.repository import FuelStationRepository

USA_COUNTRY_NAMES = {
    "united states",
    "united states of america",
    "usa",
    "us",
}

TWO_PLACES = Decimal("0.01")


def quantize_currency(amount: Decimal) -> float:
    return float(amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


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
        station_matcher: Optional[RouteStationMatcher] = None,
        fuel_optimizer: Optional[FuelOptimizer] = None,
        station_repository: Optional[FuelStationRepository] = None,
    ):
        self.provider = provider or OpenRouteServiceProvider()
        self.geocoding_service = geocoding_service or GeocodingService(self.provider)
        self.routing_service = routing_service or RoutingService(self.provider)
        self.station_repository = station_repository or FuelStationRepository()
        self.station_matcher = station_matcher or RouteStationMatcher(repository=self.station_repository)
        self.fuel_optimizer = fuel_optimizer or FuelOptimizer()

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

        # Fetch geocoded fuel stations from repository
        geocoded_stations = self.station_repository.list_geocoded_stations()

        if route.distance_miles > 500.0 and not geocoded_stations:
            raise StationDataUnavailableError(
                "Fuel station database is empty. Please run station preprocessing/import first."
            )

        coords = route.geometry.get("coordinates", [])
        matched_stations = self.station_matcher.match_stations_to_route(
            coords, stations=geocoded_stations
        )

        fuel_plan = self.fuel_optimizer.optimize_fuel_plan(
            route.distance_miles, matched_stations
        )

        formatted_stops = []
        for stop in fuel_plan.stops:
            if stop.gallons_purchased > 0:
                formatted_stops.append(
                    {
                        "opis_id": stop.station.opis_id,
                        "name": stop.station.name,
                        "mile_along_route": round(stop.station.mile_along_route, 1),
                        "off_route_miles": round(stop.station.off_route_miles, 1),
                        "latitude": stop.station.latitude,
                        "longitude": stop.station.longitude,
                        "price_per_gallon_usd": float(stop.station.effective_price),
                        "arrival_fuel_gallons": round(stop.arrival_fuel_gallons, 2),
                        "gallons_purchased": round(stop.gallons_purchased, 2),
                        "departure_fuel_gallons": round(stop.departure_fuel_gallons, 2),
                        "fuel_cost_usd": quantize_currency(stop.fuel_cost_usd),
                        "geocode_precision": stop.station.geocode_precision,
                        "geocode_source": stop.station.geocode_source,
                    }
                )

        return {
            "trip": {
                "start": {
                    "input": start_location.input,
                    "resolved": start_location.label,
                    "latitude": start_location.lat,
                    "longitude": start_location.lon,
                },
                "finish": {
                    "input": finish_location.input,
                    "resolved": finish_location.label,
                    "latitude": finish_location.lat,
                    "longitude": finish_location.lon,
                },
            },
            "route": {
                "distance_miles": route.distance_miles,
                "duration_minutes": route.duration_minutes,
                "geometry": route.geometry,
            },
            "vehicle": {
                "max_range_miles": 500,
                "fuel_efficiency_mpg": 10,
                "tank_capacity_gallons": 50,
            },
            "fuel_plan": {
                "starting_fuel_gallons": 50,
                "starting_fuel_cost_usd": None,
                "starting_fuel_cost_included": False,
                "stops": formatted_stops,
                "total_gallons_purchased": round(fuel_plan.total_gallons_purchased, 2),
                "total_fuel_cost_usd": quantize_currency(fuel_plan.total_fuel_cost_usd),
                "ending_fuel_gallons": round(fuel_plan.ending_fuel_gallons, 2),
            },
            "assumptions": {
                "route_corridor_miles": 10,
                "starting_tank": "full",
                "starting_fuel_cost": "excluded because source price is unknown",
                "off_route_distance": "approximate geographic distance to route, not driving detour distance",
            },
        }
