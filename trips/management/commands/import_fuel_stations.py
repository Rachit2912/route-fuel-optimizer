import os
from django.core.management.base import BaseCommand, CommandError

from trips.station_data.canonicalizer import CSVValidationError, StationCanonicalizer
from trips.station_data.gazetteer import CensusPlaceResolver
from trips.station_data.geocoding import CensusGeocodingError, StationGeocoder
from trips.station_data.repository import FuelStationRepository


class Command(BaseCommand):
    help = "Imports and canonicalizes fuel stations from a raw OPIS fuel price CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            type=str,
            required=True,
            help="Path to the input fuel price CSV file.",
        )
        parser.add_argument(
            "--gazetteer",
            type=str,
            required=False,
            default=None,
            help="Path to optional Census Gazetteer place file for city centroid fallback.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv"]
        gazetteer_path = options.get("gazetteer")

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV file not found: {csv_path}")

        self.stdout.write(f"Processing fuel stations from: {csv_path}")

        # Step 1: Canonicalize CSV data
        canonicalizer = StationCanonicalizer()
        try:
            canonical_stations, summary = canonicalizer.process_csv(csv_path)
        except CSVValidationError as e:
            raise CommandError(f"CSV validation failed: {e}")

        # Step 2: Load Gazetteer place resolver if provided
        place_resolver = None
        if gazetteer_path:
            if not os.path.exists(gazetteer_path):
                raise CommandError(f"Gazetteer file not found: {gazetteer_path}")
            place_resolver = CensusPlaceResolver()
            place_resolver.load_gazetteer_file(gazetteer_path)
            self.stdout.write(f"Loaded Census Gazetteer file from: {gazetteer_path}")

        # Step 3: Geocode stations
        station_geocoder = StationGeocoder(place_resolver=place_resolver)
        try:
            geocoded_results = station_geocoder.geocode_stations(canonical_stations)
        except CensusGeocodingError as e:
            raise CommandError(f"Census geocoding failed: {e}. Import aborted.") from e

        address_geocoded_count = sum(
            1 for r in geocoded_results if r.geocode_source == "census_address"
        )
        city_centroid_count = sum(
            1 for r in geocoded_results if r.geocode_source == "census_place_centroid"
        )
        unresolved_count = sum(
            1 for r in geocoded_results if r.geocode_source == "unresolved"
        )

        # Step 4: Persist to database
        repository = FuelStationRepository()
        created_count, updated_count = repository.save_geocoded_stations(geocoded_results)

        # Output concise summary statistics
        self.stdout.write(self.style.SUCCESS("\nFuel Station Import Complete!"))
        self.stdout.write(f"Source rows:                 {summary.total_source_rows}")
        self.stdout.write(f"Exact duplicates removed:    {summary.exact_duplicates_removed}")
        self.stdout.write(f"Unsupported region rows:     {summary.unsupported_region_rows_removed}")
        self.stdout.write(f"Invalid rows removed:        {summary.invalid_rows_removed}")
        self.stdout.write(f"Canonical stations:          {summary.canonical_stations_produced}")
        self.stdout.write(f"Address geocoded:            {address_geocoded_count}")
        self.stdout.write(f"City-centroid fallback:      {city_centroid_count}")
        self.stdout.write(f"Unresolved:                  {unresolved_count}")
        self.stdout.write(f"Database rows created:       {created_count}")
        self.stdout.write(f"Database rows updated:       {updated_count}")
