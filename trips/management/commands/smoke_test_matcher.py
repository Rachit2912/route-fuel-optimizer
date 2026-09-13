import time
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

        total_start_time = time.perf_counter()

        # Step 1: Geocoding + Routing API calls
        t0 = time.perf_counter()
        provider = OpenRouteServiceProvider()
        geocoding_service = GeocodingService(provider)
        routing_service = RoutingService(provider)

        start_loc = geocoding_service.resolve(start_input)
        finish_loc = geocoding_service.resolve(finish_input)
        route_result = routing_service.calculate_route(start_loc, finish_loc)
        geocoding_routing_time = time.perf_counter() - t0

        coords = route_result.geometry.get("coordinates", [])

        # Step 2: Load stations from database
        t1 = time.perf_counter()
        repository = FuelStationRepository()
        geocoded_stations = repository.list_geocoded_stations()
        db_load_time = time.perf_counter() - t1

        # Step 3: Match stations to route
        t2 = time.perf_counter()
        matcher = RouteStationMatcher(corridor_miles=corridor_miles, repository=repository)
        matched_candidates = matcher.match_stations_to_route(coords, stations=geocoded_stations)
        station_matching_time = time.perf_counter() - t2

        total_time = time.perf_counter() - total_start_time

        stats = matcher.last_stats

        self.stdout.write(self.style.SUCCESS("\n--- Smoke Test Results ---"))
        self.stdout.write(f"Start:                      {start_input} ({start_loc.label})")
        self.stdout.write(f"Finish:                     {finish_input} ({finish_loc.label})")
        self.stdout.write(f"Route total distance:       {route_result.distance_miles} miles")
        self.stdout.write(f"Route coordinate count:      {len(coords)} points")
        self.stdout.write(f"Corridor miles tolerance:   {corridor_miles} miles")

        self.stdout.write("\n--- Counts ---")
        self.stdout.write(f"geocoded stations loaded:   {stats.get('stations_loaded', 0)}")
        self.stdout.write(f"stations surviving global bbox: {stats.get('surviving_global_bbox', 0)}")
        self.stdout.write(f"exact segment comparisons performed: {stats.get('exact_segment_comparisons', 0)}")
        self.stdout.write(f"matched station count:      {stats.get('matched_stations', 0)}")

        self.stdout.write("\n--- Timings ---")
        self.stdout.write(f"geocoding + routing time:   {geocoding_routing_time:.3f}s")
        self.stdout.write(f"station DB load time:       {db_load_time:.3f}s")
        self.stdout.write(f"station matching time:      {station_matching_time:.3f}s")
        self.stdout.write(f"total time:                 {total_time:.3f}s")

        if matched_candidates:
            self.stdout.write("\nFirst 5 matched candidate stations:")
            for s in matched_candidates[:5]:
                self.stdout.write(
                    f"  OPIS #{s.opis_id:<6} | {s.name[:25]:<25} | "
                    f"Mile {s.mile_along_route:>6.1f} | Off-route: {s.off_route_miles:>4.1f} mi | "
                    f"${s.effective_price:>6.4f}/gal | {s.geocode_precision}"
                )
