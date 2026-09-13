from decimal import Decimal
import pytest

from trips.domain.fuel_optimization import InvalidOptimizerInputError
from trips.domain.station import MatchedStation
from trips.exceptions import InfeasibleRouteError
from trips.services.fuel_optimizer import FuelOptimizer


def create_mock_station(
    opis_id: int,
    mile_along_route: float,
    price: str,
    name: str = "Test Station",
) -> MatchedStation:
    return MatchedStation(
        opis_id=opis_id,
        name=name,
        latitude=40.0,
        longitude=-80.0,
        effective_price=Decimal(price),
        mile_along_route=mile_along_route,
        off_route_miles=1.0,
        geocode_source="census_address",
        geocode_precision="address",
    )


@pytest.fixture
def optimizer():
    return FuelOptimizer()


# 1. Destination within 500 miles
def test_1_destination_within_500_miles(optimizer):
    stations = [create_mock_station(1, 200.0, "3.50")]
    plan = optimizer.optimize_fuel_plan(400.0, stations)

    assert len(plan.stops) == 0
    assert plan.total_gallons_purchased == 0.0
    assert plan.total_fuel_cost_usd == Decimal("0.00")
    assert plan.ending_fuel_gallons == 10.0  # 50 - 400/10


# 2. Destination exactly 500 miles
def test_2_destination_exactly_500_miles(optimizer):
    stations = [create_mock_station(1, 250.0, "3.50")]
    plan = optimizer.optimize_fuel_plan(500.0, stations)

    assert len(plan.stops) == 0
    assert plan.total_gallons_purchased == 0.0
    assert plan.total_fuel_cost_usd == Decimal("0.00")
    assert plan.ending_fuel_gallons == 0.0


# 3. Destination just beyond 500 miles
def test_3_destination_just_beyond_500_miles(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.00"),
    ]
    plan = optimizer.optimize_fuel_plan(510.0, stations)

    assert len(plan.stops) == 1
    stop = plan.stops[0]
    assert stop.station.opis_id == 1
    assert stop.arrival_fuel_gallons == 10.0  # 50 - 400/10
    # Destination is 110 miles from station 1 (needs 11 gal). Arrival fuel is 10. Needs 1 gal purchase.
    assert stop.gallons_purchased == 1.0
    assert stop.departure_fuel_gallons == 11.0
    assert stop.fuel_cost_usd == Decimal("3.00")


# 4. First station beyond 500 miles
def test_4_first_station_beyond_500_miles(optimizer):
    stations = [
        create_mock_station(1, 510.0, "3.00"),
    ]
    with pytest.raises(InfeasibleRouteError):
        optimizer.optimize_fuel_plan(700.0, stations)


# 5. Route with no stations and distance > 500 miles
def test_5_no_stations_distance_over_500_miles(optimizer):
    with pytest.raises(InfeasibleRouteError):
        optimizer.optimize_fuel_plan(600.0, [])


# 6. Cheaper station reachable ahead
def test_6_cheaper_station_reachable_ahead(optimizer):
    # Start -> Station 1 ($4.00 at mile 200) -> Station 2 ($3.00 at mile 400) -> Dest (mile 800)
    stations = [
        create_mock_station(1, 200.0, "4.00"),
        create_mock_station(2, 400.0, "3.00"),
    ]
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    # Station 2 ($3.00) is cheaper than Station 1 ($4.00) and reachable from Start.
    # From Station 1, Station 2 is reachable with current fuel (30 gal >= 20 gal).
    # So buy 0 at Station 1! Buy at Station 2.
    assert len(plan.stops) == 1
    assert plan.stops[0].station.opis_id == 2


# 7. No cheaper station reachable (fill tank appropriately)
def test_7_no_cheaper_station_reachable(optimizer):
    # Start -> Station 1 ($3.00 at mile 400) -> Station 2 ($4.00 at mile 700) -> Dest (mile 1200)
    stations = [
        create_mock_station(1, 400.0, "3.00"),
        create_mock_station(2, 700.0, "4.00"),
    ]
    plan = optimizer.optimize_fuel_plan(1200.0, stations)

    # At Station 1 ($3.00), no station in 500 mile reach is cheaper. So fill tank to 50 gal.
    assert len(plan.stops) >= 1
    stop1 = plan.stops[0]
    assert stop1.station.opis_id == 1
    assert stop1.arrival_fuel_gallons == 10.0
    assert stop1.gallons_purchased == 40.0
    assert stop1.departure_fuel_gallons == 50.0


# 8. Expensive station followed by cheap station
def test_8_expensive_followed_by_cheap_station(optimizer):
    stations = [
        create_mock_station(1, 300.0, "5.00"),
        create_mock_station(2, 400.0, "2.50"),
    ]
    plan = optimizer.optimize_fuel_plan(750.0, stations)

    # Station 1 is passed without buying fuel because Station 2 is cheaper
    assert len(plan.stops) == 1
    assert plan.stops[0].station.opis_id == 2


# 9. Cheap station followed by expensive stations
def test_9_cheap_followed_by_expensive_stations(optimizer):
    stations = [
        create_mock_station(1, 200.0, "2.00"),
        create_mock_station(2, 600.0, "4.00"),
        create_mock_station(3, 900.0, "4.50"),
    ]
    plan = optimizer.optimize_fuel_plan(1200.0, stations)

    # Station 1 is cheap. At Station 1, stations ahead are more expensive.
    # Fills tank to 50 gal at Station 1 ($2.00).
    stop1 = plan.stops[0]
    assert stop1.station.opis_id == 1
    assert stop1.departure_fuel_gallons == 50.0


# 10. Destination reachable from current station
def test_10_destination_reachable_from_current_station(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.00"),
        create_mock_station(2, 700.0, "3.50"),
    ]
    # Total distance 800 miles. From Station 1 (mile 400), dest is 400 miles away (reachable within 500 miles).
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    assert len(plan.stops) == 1
    stop = plan.stops[0]
    assert stop.station.opis_id == 1
    # Needs 40 gal total from mile 400 to 800. Arrives with 10 gal. Buys 30 gal.
    assert stop.gallons_purchased == 30.0


# 11. Multiple stops fuel state tracking & 12. Legs <= 500
def test_11_multiple_stops_fuel_state_tracking(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.00"),
        create_mock_station(2, 850.0, "3.20"),
        create_mock_station(3, 1300.0, "3.10"),
    ]
    plan = optimizer.optimize_fuel_plan(1700.0, stations)

    assert len(plan.stops) > 1
    prev_pos = 0.0
    for stop in plan.stops:
        leg_dist = stop.station.mile_along_route - prev_pos
        assert leg_dist <= 500.0
        assert 0.0 <= stop.arrival_fuel_gallons <= 50.0
        assert 0.0 <= stop.departure_fuel_gallons <= 50.0
        assert stop.gallons_purchased >= 0.0
        prev_pos = stop.station.mile_along_route


# 13. Tank capacity never exceeded & 14. Arrival fuel never negative & 15. Gallons purchased never negative
def test_13_invariants_fuel_bounds(optimizer):
    stations = [
        create_mock_station(1, 300.0, "3.00"),
        create_mock_station(2, 700.0, "2.80"),
        create_mock_station(3, 1100.0, "3.10"),
    ]
    plan = optimizer.optimize_fuel_plan(1500.0, stations)

    for stop in plan.stops:
        assert 0.0 <= stop.arrival_fuel_gallons <= 50.0
        assert 0.0 <= stop.departure_fuel_gallons <= 50.0
        assert stop.gallons_purchased >= 0.0


# 16. Total cost equals sum of individual stop costs using Decimal
def test_16_total_cost_sum_of_stop_costs(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.25"),
        create_mock_station(2, 800.0, "3.10"),
    ]
    plan = optimizer.optimize_fuel_plan(1200.0, stations)

    calculated_sum = sum((s.fuel_cost_usd for s in plan.stops), Decimal("0.00"))
    assert plan.total_fuel_cost_usd == calculated_sum


# 17. Identical station mile positions (cheapest station chosen)
def test_17_identical_station_mile_positions(optimizer):
    stations = [
        create_dummy_station_at_mile(10, 400.0, "4.00"),
        create_dummy_station_at_mile(11, 400.0, "2.90"),
        create_dummy_station_at_mile(12, 400.0, "3.50"),
    ]
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    assert len(plan.stops) == 1
    assert plan.stops[0].station.opis_id == 11
    assert plan.stops[0].station.effective_price == Decimal("2.90")


def create_dummy_station_at_mile(opis_id: int, mile: float, price: str) -> MatchedStation:
    return create_mock_station(opis_id, mile, price)


# 18. Unsorted station inputs sorted internally
def test_18_unsorted_station_inputs(optimizer):
    stations = [
        create_mock_station(2, 800.0, "3.10"),
        create_mock_station(1, 400.0, "3.25"),
    ]
    plan = optimizer.optimize_fuel_plan(1200.0, stations)

    assert len(plan.stops) == 2
    assert plan.stops[0].station.opis_id == 1
    assert plan.stops[1].station.opis_id == 2


# 19. Station mile < 0 rejected
def test_19_station_mile_less_than_zero_rejected(optimizer):
    stations = [create_mock_station(1, -10.0, "3.00")]
    with pytest.raises(InvalidOptimizerInputError):
        optimizer.optimize_fuel_plan(500.0, stations)


# 20. Station mile > route distance rejected
def test_20_station_mile_greater_than_route_distance_rejected(optimizer):
    stations = [create_mock_station(1, 600.0, "3.00")]
    with pytest.raises(InvalidOptimizerInputError):
        optimizer.optimize_fuel_plan(500.0, stations)


# 21. Duplicate stations handled cleanly
def test_21_duplicate_stations_handled_cleanly(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.00"),
        create_mock_station(1, 400.0, "3.00"),
    ]
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    assert len(plan.stops) == 1


# 22. Zero/negative price rejected
def test_22_zero_or_negative_price_rejected(optimizer):
    stations_zero = [create_mock_station(1, 200.0, "0.00")]
    with pytest.raises(InvalidOptimizerInputError):
        optimizer.optimize_fuel_plan(500.0, stations_zero)

    stations_neg = [create_mock_station(1, 200.0, "-2.50")]
    with pytest.raises(InvalidOptimizerInputError):
        optimizer.optimize_fuel_plan(500.0, stations_neg)


# 23. Floating-point boundary around 500 miles handled safely
def test_23_floating_point_boundary_500_miles(optimizer):
    # Station at 499.9999 miles
    stations = [create_mock_station(1, 499.9999, "3.00")]
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    assert len(plan.stops) == 1
    assert plan.stops[0].station.opis_id == 1


# 24. Ending fuel consistency check
def test_24_ending_fuel_consistency(optimizer):
    stations = [
        create_mock_station(1, 400.0, "3.00"),
    ]
    plan = optimizer.optimize_fuel_plan(800.0, stations)

    # Start 50 gal -> arrive mile 400 with 10 gal.
    # Needs 40 gal for 400-800 leg. Buys 30 gal -> departure fuel 40 gal.
    # Arrives at mile 800 with 0 gal.
    assert plan.ending_fuel_gallons == 0.0
