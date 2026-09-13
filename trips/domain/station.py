from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MatchedStation:
    opis_id: int
    name: str
    latitude: float
    longitude: float
    effective_price: Decimal
    mile_along_route: float
    off_route_miles: float
    geocode_source: str
    geocode_precision: str
