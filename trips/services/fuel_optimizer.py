from decimal import Decimal
import math
from typing import List, Optional, Tuple

from trips.domain.fuel_optimization import (
    FuelPlan,
    FuelStop,
    InvalidOptimizerInputError,
)
from trips.domain.station import MatchedStation
from trips.exceptions import InfeasibleRouteError

MAX_RANGE_MILES = 500.0
MPG = 10.0
TANK_CAPACITY_GALLONS = 50.0
STARTING_FUEL_GALLONS = 50.0


class FuelOptimizer:
    def optimize_fuel_plan(
        self,
        route_distance_miles: float,
        stations: List[MatchedStation],
    ) -> FuelPlan:
        if route_distance_miles < 0:
            raise InvalidOptimizerInputError("Route distance cannot be negative.")

        # Validate and normalize input stations
        normalized_stations = self._normalize_and_validate_stations(
            route_distance_miles, stations
        )

        # Optimization loop
        current_pos = 0.0
        current_fuel = STARTING_FUEL_GALLONS
        current_price: Optional[Decimal] = None  # None at start
        current_station: Optional[MatchedStation] = None

        stops: List[FuelStop] = []

        while current_pos < route_distance_miles - 1e-6:
            dist_to_dest = route_distance_miles - current_pos

            # 1. Check if destination is reachable with current fuel
            fuel_needed_to_dest = dist_to_dest / MPG
            if current_fuel >= fuel_needed_to_dest - 1e-7:
                # Drive to destination
                current_fuel = max(0.0, current_fuel - fuel_needed_to_dest)
                current_pos = route_distance_miles
                break

            # Destination is NOT reachable with current fuel.
            # Can we reach destination with a full tank from current position?
            if dist_to_dest <= MAX_RANGE_MILES + 1e-6:
                # Destination is reachable within 500 miles of current position.
                # Find if any station ahead between current_pos and destination is cheaper than current_price.
                stations_to_dest = [
                    s for s in normalized_stations if current_pos < s.mile_along_route < route_distance_miles - 1e-6
                ]

                first_cheaper = None
                if current_price is not None:
                    for s in stations_to_dest:
                        if s.effective_price < current_price:
                            first_cheaper = s
                            break

                if first_cheaper is not None:
                    # Drive to first cheaper station
                    dist_to_cheaper = first_cheaper.mile_along_route - current_pos
                    fuel_req = dist_to_cheaper / MPG
                    gallons_to_buy = max(0.0, fuel_req - current_fuel)

                    if current_fuel + gallons_to_buy > TANK_CAPACITY_GALLONS + 1e-6:
                        raise InfeasibleRouteError("Required fuel exceeds tank capacity.")

                    departure_fuel = current_fuel + gallons_to_buy
                    if gallons_to_buy > 1e-6 and current_station is not None:
                        cost = Decimal(str(round(gallons_to_buy, 6))) * current_station.effective_price
                        stops.append(
                            FuelStop(
                                station=current_station,
                                arrival_fuel_gallons=round(current_fuel, 4),
                                gallons_purchased=round(gallons_to_buy, 4),
                                departure_fuel_gallons=round(departure_fuel, 4),
                                fuel_cost_usd=cost,
                            )
                        )
                        current_fuel = departure_fuel

                    current_fuel = max(0.0, current_fuel - fuel_req)
                    current_pos = first_cheaper.mile_along_route
                    current_station = first_cheaper
                    current_price = first_cheaper.effective_price
                else:
                    # Buy enough fuel at current station to reach destination
                    gallons_to_buy = fuel_needed_to_dest - current_fuel
                    if gallons_to_buy > TANK_CAPACITY_GALLONS - current_fuel + 1e-6:
                        raise InfeasibleRouteError("Cannot buy required fuel without exceeding tank capacity.")

                    if current_station is None or current_price is None:
                        raise InfeasibleRouteError(
                            f"Destination is {dist_to_dest:.1f} miles away from start, exceeding initial fuel range."
                        )

                    departure_fuel = current_fuel + gallons_to_buy
                    cost = Decimal(str(round(gallons_to_buy, 6))) * current_price
                    stops.append(
                        FuelStop(
                            station=current_station,
                            arrival_fuel_gallons=round(current_fuel, 4),
                            gallons_purchased=round(gallons_to_buy, 4),
                            departure_fuel_gallons=round(departure_fuel, 4),
                            fuel_cost_usd=cost,
                        )
                    )
                    current_fuel = max(0.0, departure_fuel - fuel_needed_to_dest)
                    current_pos = route_distance_miles
                    break
            else:
                # Destination is NOT reachable within 500 miles from current position.
                full_tank_reach = [
                    s for s in normalized_stations if current_pos < s.mile_along_route <= current_pos + MAX_RANGE_MILES + 1e-6
                ]

                if not full_tank_reach:
                    raise InfeasibleRouteError(
                        f"No fuel station available within 500-mile range after mile {current_pos:.1f}."
                    )

                current_fuel_reach = [
                    s for s in full_tank_reach if s.mile_along_route <= current_pos + (current_fuel * MPG) + 1e-6
                ]

                if not current_fuel_reach and current_station is None:
                    raise InfeasibleRouteError(
                        f"No fuel station reachable with initial fuel from start."
                    )

                # Look for cheaper station in full_tank_reach
                first_cheaper = None
                if current_price is not None:
                    for s in full_tank_reach:
                        if s.effective_price < current_price:
                            first_cheaper = s
                            break

                if first_cheaper is not None:
                    # Drive to first cheaper station
                    dist_to_cheaper = first_cheaper.mile_along_route - current_pos
                    fuel_req = dist_to_cheaper / MPG
                    gallons_to_buy = max(0.0, fuel_req - current_fuel)

                    if gallons_to_buy > TANK_CAPACITY_GALLONS - current_fuel + 1e-6:
                        raise InfeasibleRouteError("Required fuel exceeds tank capacity.")

                    if gallons_to_buy > 1e-6 and current_station is not None and current_price is not None:
                        departure_fuel = current_fuel + gallons_to_buy
                        cost = Decimal(str(round(gallons_to_buy, 6))) * current_price
                        stops.append(
                            FuelStop(
                                station=current_station,
                                arrival_fuel_gallons=round(current_fuel, 4),
                                gallons_purchased=round(gallons_to_buy, 4),
                                departure_fuel_gallons=round(departure_fuel, 4),
                                fuel_cost_usd=cost,
                            )
                        )
                        current_fuel = departure_fuel

                    current_fuel = max(0.0, current_fuel - fuel_req)
                    current_pos = first_cheaper.mile_along_route
                    current_station = first_cheaper
                    current_price = first_cheaper.effective_price
                else:
                    # Current price is cheaper than or equal to all stations in 500-mile reach.
                    # Fill tank at current station if at a station.
                    if current_station is not None and current_price is not None:
                        gallons_to_buy = TANK_CAPACITY_GALLONS - current_fuel
                        if gallons_to_buy > 1e-6:
                            departure_fuel = TANK_CAPACITY_GALLONS
                            cost = Decimal(str(round(gallons_to_buy, 6))) * current_price
                            stops.append(
                                FuelStop(
                                    station=current_station,
                                    arrival_fuel_gallons=round(current_fuel, 4),
                                    gallons_purchased=round(gallons_to_buy, 4),
                                    departure_fuel_gallons=round(departure_fuel, 4),
                                    fuel_cost_usd=cost,
                                )
                            )
                            current_fuel = departure_fuel

                    # Pick cheapest station in full_tank_reach to drive to next
                    # If ties, pick furthest cheapest station to maximize progress
                    min_price_in_reach = min(s.effective_price for s in full_tank_reach)
                    cheapest_in_reach = [
                        s for s in full_tank_reach if s.effective_price == min_price_in_reach
                    ]
                    next_station = max(cheapest_in_reach, key=lambda s: s.mile_along_route)

                    dist_to_next = next_station.mile_along_route - current_pos
                    fuel_needed = dist_to_next / MPG
                    if current_fuel < fuel_needed - 1e-6:
                        raise InfeasibleRouteError(
                            f"Ran out of fuel before reaching next station at mile {next_station.mile_along_route:.1f}."
                        )

                    current_fuel = max(0.0, current_fuel - fuel_needed)
                    current_pos = next_station.mile_along_route
                    current_station = next_station
                    current_price = next_station.effective_price

        # Summarize total cost and gallons
        total_gallons = sum(s.gallons_purchased for s in stops)
        total_cost = sum((s.fuel_cost_usd for s in stops), Decimal("0.00"))

        return FuelPlan(
            stops=stops,
            total_gallons_purchased=round(total_gallons, 4),
            total_fuel_cost_usd=total_cost,
            starting_fuel_gallons=STARTING_FUEL_GALLONS,
            starting_fuel_cost_usd=None,
            starting_fuel_cost_included=False,
            ending_fuel_gallons=round(current_fuel, 4),
        )

    def _normalize_and_validate_stations(
        self,
        route_distance_miles: float,
        stations: List[MatchedStation],
    ) -> List[MatchedStation]:
        if not stations:
            return []

        for s in stations:
            if s.effective_price is None or s.effective_price <= Decimal("0"):
                raise InvalidOptimizerInputError(
                    f"Station OPIS #{s.opis_id} has invalid price: {s.effective_price}"
                )
            if s.mile_along_route < -1e-6 or s.mile_along_route > route_distance_miles + 1e-6:
                raise InvalidOptimizerInputError(
                    f"Station OPIS #{s.opis_id} mile {s.mile_along_route} is outside route bounds [0, {route_distance_miles}]."
                )

        # Sort by mile_along_route ASC
        sorted_stations = sorted(stations, key=lambda s: (s.mile_along_route, s.opis_id))

        # Deduplicate same-mile stations: keep station with lowest effective_price
        deduped: List[MatchedStation] = []
        for s in sorted_stations:
            if not deduped:
                deduped.append(s)
            else:
                last = deduped[-1]
                if abs(s.mile_along_route - last.mile_along_route) < 1e-5:
                    if s.effective_price < last.effective_price:
                        deduped[-1] = s
                else:
                    deduped.append(s)

        return deduped
