from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from trips.domain.station import MatchedStation


class InvalidOptimizerInputError(Exception):
    pass


@dataclass(frozen=True)
class FuelStop:
    station: MatchedStation
    arrival_fuel_gallons: float
    gallons_purchased: float
    departure_fuel_gallons: float
    fuel_cost_usd: Decimal


@dataclass(frozen=True)
class FuelPlan:
    stops: List[FuelStop]
    total_gallons_purchased: float
    total_fuel_cost_usd: Decimal
    starting_fuel_gallons: float = 50.0
    starting_fuel_cost_usd: Optional[Decimal] = None
    starting_fuel_cost_included: bool = False
    ending_fuel_gallons: float = 0.0
