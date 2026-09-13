from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from trips.domain.fuel_optimization import FuelPlan, FuelStop
from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult
from trips.domain.station import MatchedStation
from trips.exceptions import (
    InfeasibleRouteError,
    LocationNotFoundError,
    RouteNotFoundError,
    StationDataUnavailableError,
    UnsupportedRegionError,
)
from trips.models import FuelStation
from trips.services.trip_optimization import TripOptimizationService


@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def mock_repo():
    return MagicMock()


@pytest.fixture
def service(mock_provider, mock_repo):
    return TripOptimizationService(
        provider=mock_provider,
        station_repository=mock_repo,
    )


def test_trip_optimization_success_full_plan(service, mock_provider, mock_repo):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Chicago, IL", "Chicago, Illinois, USA", 41.8781, -87.6298, "United States"),
        ResolvedLocation("Miami, FL", "Miami, Florida, USA", 25.7617, -80.1918, "United States"),
    ]

    mock_provider.get_route.return_value = RouteResult(
        distance_miles=1375.42,
        duration_minutes=1210.3,
        geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-80.1918, 25.7617]]},
    )

    # Mock matched stations along route (spaced <= 500 miles apart) with realistic prices
    matched_st1 = MatchedStation(
        opis_id=101,
        name="Pilot Center",
        latitude=36.1627,
        longitude=-86.7816,
        effective_price=Decimal("3.2493"),
        mile_along_route=400.0,
        off_route_miles=1.2,
        geocode_source="census_address",
        geocode_precision="address",
    )
    matched_st2 = MatchedStation(
        opis_id=102,
        name="Loves Stop",
        latitude=30.0,
        longitude=-82.0,
        effective_price=Decimal("3.1287"),
        mile_along_route=850.0,
        off_route_miles=0.5,
        geocode_source="census_address",
        geocode_precision="address",
    )
    matched_st3 = MatchedStation(
        opis_id=103,
        name="Speedway",
        latitude=27.0,
        longitude=-80.5,
        effective_price=Decimal("3.1501"),
        mile_along_route=1200.0,
        off_route_miles=0.8,
        geocode_source="census_address",
        geocode_precision="address",
    )

    service.station_matcher.match_stations_to_route = MagicMock(
        return_value=[matched_st1, matched_st2, matched_st3]
    )

    mock_repo.list_geocoded_stations.return_value = [
        FuelStation(
            opis_id=101,
            name="Pilot Center",
            address="100 Hwy 1",
            city="Nashville",
            state="TN",
            rack_id=1,
            effective_price=Decimal("3.2493"),
            price_min=Decimal("3.2493"),
            price_max=Decimal("3.2493"),
            price_observation_count=1,
            source_row_count=1,
            latitude=36.1627,
            longitude=-86.7816,
            geocode_source="census_address",
            geocode_precision="address",
        )
    ]

    result = service.optimize_trip("Chicago, IL", "Miami, FL")

    # 1. Check trip response structure
    assert result["trip"]["start"]["input"] == "Chicago, IL"
    assert result["trip"]["start"]["resolved"] == "Chicago, Illinois, USA"
    assert result["trip"]["start"]["latitude"] == 41.8781
    assert result["trip"]["start"]["longitude"] == -87.6298

    # 2. Check route GeoJSON included
    assert result["route"]["distance_miles"] == 1375.42
    assert result["route"]["geometry"]["type"] == "LineString"

    # 3. Check vehicle assumptions
    assert result["vehicle"] == {
        "max_range_miles": 500,
        "fuel_efficiency_mpg": 10,
        "tank_capacity_gallons": 50,
    }

    # 4. Check fuel plan totals
    assert "fuel_plan" in result
    assert result["fuel_plan"]["starting_fuel_gallons"] == 50
    assert result["fuel_plan"]["starting_fuel_cost_usd"] is None
    assert result["fuel_plan"]["starting_fuel_cost_included"] is False
    assert "total_gallons_purchased" in result["fuel_plan"]
    assert "total_fuel_cost_usd" in result["fuel_plan"]

    # Verify 2-decimal currency quantization
    total_cost_str = str(result["fuel_plan"]["total_fuel_cost_usd"])
    if "." in total_cost_str:
        assert len(total_cost_str.split(".")[1]) <= 2

    for stop in result["fuel_plan"]["stops"]:
        stop_cost_str = str(stop["fuel_cost_usd"])
        if "." in stop_cost_str:
            assert len(stop_cost_str.split(".")[1]) <= 2
        # Verify price_per_gallon_usd preserves dataset precision (3.2493)
        assert stop["price_per_gallon_usd"] in (3.2493, 3.1287, 3.1501)

    # 5. Check assumptions
    assert result["assumptions"]["route_corridor_miles"] == 10

    # 10. Check exactly 1 routing call performed
    assert mock_provider.get_route.call_count == 1


def test_trip_optimization_short_trip_under_500_miles_no_purchases(service, mock_provider, mock_repo):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Chicago, IL", "Chicago, IL, USA", 41.8781, -87.6298, "United States"),
        ResolvedLocation("Milwaukee, WI", "Milwaukee, WI, USA", 43.0389, -87.9065, "United States"),
    ]

    mock_provider.get_route.return_value = RouteResult(
        distance_miles=92.5,
        duration_minutes=90.0,
        geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-87.9065, 43.0389]]},
    )

    mock_repo.list_geocoded_stations.return_value = []  # Empty DB!

    result = service.optimize_trip("Chicago, IL", "Milwaukee, WI")

    assert result["route"]["distance_miles"] == 92.5
    assert result["fuel_plan"]["total_gallons_purchased"] == 0.0
    assert result["fuel_plan"]["total_fuel_cost_usd"] == 0.0
    assert len(result["fuel_plan"]["stops"]) == 0


def test_trip_optimization_empty_station_db_long_trip_raises_error(service, mock_provider, mock_repo):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Chicago, IL", "Chicago, IL, USA", 41.8781, -87.6298, "United States"),
        ResolvedLocation("Miami, FL", "Miami, FL, USA", 25.7617, -80.1918, "United States"),
    ]

    mock_provider.get_route.return_value = RouteResult(
        distance_miles=1375.42,
        duration_minutes=1210.3,
        geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-80.1918, 25.7617]]},
    )

    mock_repo.list_geocoded_stations.return_value = []  # Empty DB!

    with pytest.raises(StationDataUnavailableError):
        service.optimize_trip("Chicago, IL", "Miami, FL")


def test_trip_optimization_start_not_found(service, mock_provider):
    mock_provider.geocode.side_effect = LocationNotFoundError("Start location could not be resolved.")

    with pytest.raises(LocationNotFoundError):
        service.optimize_trip("UnknownLocation", "Miami, FL")


def test_trip_optimization_location_outside_usa(service, mock_provider):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Toronto, ON", "Toronto, Ontario, Canada", 43.6532, -79.3832, "Canada"),
        ResolvedLocation("Miami, FL", "Miami, Florida, USA", 25.7617, -80.1918, "United States"),
    ]

    with pytest.raises(UnsupportedRegionError):
        service.optimize_trip("Toronto, ON", "Miami, FL")


def test_trip_optimization_route_not_found(service, mock_provider):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Chicago, IL", "Chicago, Illinois, USA", 41.8781, -87.6298, "United States"),
        ResolvedLocation("Honolulu, HI", "Honolulu, Hawaii, USA", 21.3069, -157.8583, "United States"),
    ]
    mock_provider.get_route.side_effect = RouteNotFoundError("No route found.")

    with pytest.raises(RouteNotFoundError):
        service.optimize_trip("Chicago, IL", "Honolulu, HI")
