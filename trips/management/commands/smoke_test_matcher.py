from django.core.management.base import BaseCommand

from trips.providers.openrouteservice import OpenRouteServiceProvider
from trips.routing.station_matcher import RouteStationMatcher
from trips.services.geocoding import GeocodingService
from trips.services.routing import RoutingService
from trips.station_data.repository import FuelStationRepository


class Command(BaseCommand):
    help = "Smoke test for route station matching using ORS route and FuelStation database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            type=str,
            default="Chicago, IL",
            help="Start location for the smoke test route.",
        )
        parser.add_argument(
            "--finish",
            type=str,
            default="Miami, FL",
            help="Finish location for the smoke test route.",
        )
        parser.add_argument(
            "--corridor",
            type=float,
            default=10.0,
            help="Corridor miles tolerance.",
        )

    def handle(self, *args, **options):
        start_input = options["start"]
        finish_input = options["finish"]
        corridor_miles = options["corridor"]

        provider = OpenRouteServiceProvider()
        geocoding_service = GeocodingService(provider)
        routing_service = RoutingService(provider)

        self.stdout.write(f"Geocoding start: '{start_input}'...")
        start_loc = geocoding_service.resolve(start_input)

        self.stdout.write(f"Geocoding finish: '{finish_input}'...")
        finish_loc = geocoding_service.resolve(finish_input)

        self.stdout.write("Fetching driving route...")
        route_result = routing_service.calculate_route(start_loc, finish_loc)

        coords = route_result.geometry.get("coordinates", [])
        self.stdout.write(f"Route total distance: {route_result.distance_miles} miles")
        self.stdout.write(f"Route coordinate count: {len(coords)} points")

        repository = FuelStationRepository()
        geocoded_stations = repository.list_geocoded_stations()
        self.stdout.write(f"Geocoded stations in DB considered: {len(geocoded_stations)}")

        matcher = RouteStationMatcher(corridor_miles=corridor_miles, repository=repository)
        matched_candidates = matcher.match_stations_to_route(coords, stations=geocoded_stations)

        self.stdout.write(self.style.SUCCESS(f"\nMatched candidate stations within {corridor_miles}-mile corridor: {len(matched_candidates)}"))

        if matched_candidates:
            self.stdout.write("\nFirst 5 matched candidate stations:")
            for s in matched_candidates[:5]:
                self.stdout.write(
                    f"  OPIS #{s.opis_id:<6} | {s.name[:25]:<25} | "
                    f"Mile {s.mile_along_route:>6.1f} | Off-route: {s.off_route_miles:>4.1f} mi | "
                    f"${s.effective_price:>6.4f}/gal | {s.geocode_precision}"
                )
