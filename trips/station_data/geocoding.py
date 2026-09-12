from dataclasses import dataclass
import csv
import io
import logging
from typing import Dict, List, Optional, Tuple
import requests

from trips.station_data.canonicalizer import CanonicalStation
from trips.station_data.gazetteer import CensusPlaceResolver

logger = logging.getLogger(__name__)

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 10000


@dataclass(frozen=True)
class GeocodedStationResult:
    station: CanonicalStation
    latitude: Optional[float]
    longitude: Optional[float]
    geocode_source: str
    geocode_precision: str


class CensusBatchGeocoder:
    def __init__(self, url: str = CENSUS_BATCH_URL, timeout: float = 60.0):
        self.url = url
        self.timeout = timeout

    def geocode_batch(
        self, stations: List[CanonicalStation]
    ) -> Dict[int, Tuple[float, float]]:
        if not stations:
            return {}

        results: Dict[int, Tuple[float, float]] = {}

        # Chunk into batches of <= BATCH_SIZE
        for i in range(0, len(stations), BATCH_SIZE):
            chunk = stations[i : i + BATCH_SIZE]
            batch_results = self._process_chunk(chunk)
            results.update(batch_results)

        return results

    def _process_chunk(
        self, chunk: List[CanonicalStation]
    ) -> Dict[int, Tuple[float, float]]:
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)

        # Census format: Unique ID, Street Address, City, State, ZIP
        for s in chunk:
            writer.writerow([s.opis_id, s.address, s.city, s.state, ""])

        csv_content = csv_buffer.getvalue()

        files = {
            "addressFile": ("addresses.csv", csv_content, "text/csv"),
        }
        data = {
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
        }

        try:
            response = requests.post(
                self.url,
                files=files,
                data=data,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Census batch geocoder request failed: {e}")
            return {}

        return self._parse_census_response(response.text)

    def _parse_census_response(
        self, response_text: str
    ) -> Dict[int, Tuple[float, float]]:
        results: Dict[int, Tuple[float, float]] = {}
        reader = csv.reader(io.StringIO(response_text))

        for row in reader:
            if not row or len(row) < 6:
                continue

            try:
                opis_id = int(row[0].strip())
                match_status = row[2].strip().lower()

                if match_status == "match":
                    coords_str = row[5].strip()  # Format: "lon,lat"
                    if "," in coords_str:
                        lon_str, lat_str = coords_str.split(",")
                        lon = float(lon_str.strip())
                        lat = float(lat_str.strip())
                        results[opis_id] = (lat, lon)
            except (ValueError, IndexError):
                continue

        return results


class StationGeocoder:
    def __init__(
        self,
        batch_geocoder: Optional[CensusBatchGeocoder] = None,
        place_resolver: Optional[CensusPlaceResolver] = None,
    ):
        self.batch_geocoder = batch_geocoder or CensusBatchGeocoder()
        self.place_resolver = place_resolver

    def geocode_stations(
        self, stations: List[CanonicalStation]
    ) -> List[GeocodedStationResult]:
        # Step 1: Batch address geocoding via Census API
        address_matches = self.batch_geocoder.geocode_batch(stations)

        results: List[GeocodedStationResult] = []

        for s in stations:
            if s.opis_id in address_matches:
                lat, lon = address_matches[s.opis_id]
                results.append(
                    GeocodedStationResult(
                        station=s,
                        latitude=lat,
                        longitude=lon,
                        geocode_source="census_address",
                        geocode_precision="address",
                    )
                )
            elif self.place_resolver:
                # Step 2: Fallback to Census Gazetteer place centroid
                place_coords = self.place_resolver.resolve(s.city, s.state)
                if place_coords:
                    lat, lon = place_coords
                    results.append(
                        GeocodedStationResult(
                            station=s,
                            latitude=lat,
                            longitude=lon,
                            geocode_source="census_place_centroid",
                            geocode_precision="city",
                        )
                    )
                else:
                    results.append(
                        GeocodedStationResult(
                            station=s,
                            latitude=None,
                            longitude=None,
                            geocode_source="unresolved",
                            geocode_precision="unresolved",
                        )
                    )
            else:
                results.append(
                    GeocodedStationResult(
                        station=s,
                        latitude=None,
                        longitude=None,
                        geocode_source="unresolved",
                        geocode_precision="unresolved",
                    )
                )

        return results
