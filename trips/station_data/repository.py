from typing import List, Tuple
from django.db import transaction

from trips.models import FuelStation
from trips.station_data.geocoding import GeocodedStationResult


class FuelStationRepository:
    @transaction.atomic
    def save_geocoded_stations(
        self, geocoded_results: List[GeocodedStationResult]
    ) -> Tuple[int, int]:
        created_count = 0
        updated_count = 0

        for item in geocoded_results:
            s = item.station
            defaults = {
                "name": s.name,
                "address": s.address,
                "city": s.city,
                "state": s.state,
                "rack_id": s.rack_id,
                "effective_price": s.effective_price,
                "price_min": s.price_min,
                "price_max": s.price_max,
                "price_observation_count": s.price_observation_count,
                "source_row_count": s.source_row_count,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "geocode_source": item.geocode_source,
                "geocode_precision": item.geocode_precision,
            }

            obj, created = FuelStation.objects.update_or_create(
                opis_id=s.opis_id,
                defaults=defaults,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        return created_count, updated_count

    def list_geocoded_stations(self) -> List[FuelStation]:
        return list(
            FuelStation.objects.filter(
                latitude__isnull=False,
                longitude__isnull=False,
            )
        )
