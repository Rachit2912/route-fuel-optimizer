from unittest.mock import MagicMock
import pytest

from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult
from trips.exceptions import LocationNotFoundError, RouteNotFoundError, UnsupportedRegionError
from trips.services.trip_optimization import TripOptimizationService


@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def service(mock_provider):
    return TripOptimizationService(provider=mock_provider)


def test_trip_optimization_success(service, mock_provider):
    mock_provider.geocode.side_effect = [
        ResolvedLocation(
            input="Chicago, IL",
            label="Chicago, Illinois, USA",
            lat=41.8781,
            lon=-87.6298,
            country="United States",
        ),
        ResolvedLocation(
            input="Miami, FL",
            label="Miami, Florida, USA",
            lat=25.7617,
            lon=-80.1918,
            country="United States",
        ),
    ]

    mock_provider.get_route.return_value = RouteResult(
        distance_miles=1375.42,
        duration_minutes=1210.3,
        geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-80.1918, 25.7617]]},
    )

    result = service.optimize_trip("Chicago, IL", "Miami, FL")

    assert result["start"]["input"] == "Chicago, IL"
    assert result["start"]["label"] == "Chicago, Illinois, USA"
    assert result["start"]["lat"] == 41.8781
    assert result["start"]["lon"] == -87.6298

    assert result["finish"]["input"] == "Miami, FL"
    assert result["finish"]["label"] == "Miami, Florida, USA"
    assert result["finish"]["lat"] == 25.7617
    assert result["finish"]["lon"] == -80.1918

    assert result["route"]["distance_miles"] == 1375.42
    assert result["route"]["duration_minutes"] == 1210.3
    assert result["route"]["geometry"]["type"] == "LineString"

    assert mock_provider.geocode.call_count == 2
    assert mock_provider.get_route.call_count == 1


def test_trip_optimization_start_not_found(service, mock_provider):
    mock_provider.geocode.side_effect = LocationNotFoundError("Start location could not be resolved.")

    with pytest.raises(LocationNotFoundError):
        service.optimize_trip("UnknownLocation", "Miami, FL")


def test_trip_optimization_finish_not_found(service, mock_provider):
    mock_provider.geocode.side_effect = [
        ResolvedLocation("Chicago, IL", "Chicago, Illinois, USA", 41.8781, -87.6298, "United States"),
        LocationNotFoundError("Finish location could not be resolved."),
    ]

    with pytest.raises(LocationNotFoundError):
        service.optimize_trip("Chicago, IL", "UnknownLocation")


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
