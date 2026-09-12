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


class CensusGeocodingError(Exception):
    pass


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
            raise CensusGeocodingError(
                f"Census batch geocoding service request failed: {e}"
            ) from e

        return self._parse_census_response(response.text, chunk)

    def _parse_census_response(
        self, response_text: str, chunk: List[CanonicalStation]
    ) -> Dict[int, Tuple[float, float]]:
        submitted_ids = {s.opis_id for s in chunk}
        received_ids = set()
        results: Dict[int, Tuple[float, float]] = {}

        try:
            reader = csv.reader(io.StringIO(response_text))
            for row in reader:
                if not row:
                    continue  # Ignore empty line

                if len(row) < 3:
                    raise CensusGeocodingError("Malformed row in Census batch geocoding response.")

                raw_id = row[0].strip()
                try:
                    opis_id = int(raw_id)
                except ValueError as e:
                    raise CensusGeocodingError(f"Invalid station ID '{raw_id}' in Census response.") from e

                if opis_id not in submitted_ids:
                    raise CensusGeocodingError(
                        f"Unexpected station ID '{opis_id}' in Census response (not in submitted batch)."
                    )

                if opis_id in received_ids:
                    raise CensusGeocodingError(
                        f"Duplicate station ID '{opis_id}' in Census batch response."
                    )

                received_ids.add(opis_id)
                match_status = row[2].strip().lower()

                if match_status == "match":
                    if len(row) < 6:
                        raise CensusGeocodingError(f"Missing coordinate data for station ID '{opis_id}' in Census match response.")
                    coords_str = row[5].strip()
                    if "," not in coords_str:
                        raise CensusGeocodingError(f"Invalid coordinates string '{coords_str}' for station ID '{opis_id}'.")
                    try:
                        lon_str, lat_str = coords_str.split(",")
                        lon = float(lon_str.strip())
                        lat = float(lat_str.strip())
                        results[opis_id] = (lat, lon)
                    except ValueError as e:
                        raise CensusGeocodingError(f"Malformed coordinate values for station ID '{opis_id}'.") from e
                elif match_status in ("no_match", "tie", "exact", "non_exact"):
                    # Valid no-match or non-exact match with no coordinates
                    pass
                else:
                    raise CensusGeocodingError(
                        f"Unrecognized match status '{row[2]}' for station ID '{opis_id}' in Census response."
                    )
        except csv.Error as e:
            raise CensusGeocodingError("Malformed CSV response from Census geocoding service.") from e

        if received_ids != submitted_ids:
            missing_ids = submitted_ids - received_ids
            raise CensusGeocodingError(
                f"Partial Census batch response: missing results for submitted station IDs {sorted(list(missing_ids))}."
            )

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
        # Step 1: Batch address geocoding via Census API (raises CensusGeocodingError if network/HTTP or malformed/partial response occurs)
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
