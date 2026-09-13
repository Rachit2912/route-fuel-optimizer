from unittest.mock import patch
from django.urls import reverse
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from trips.exceptions import (
    InfeasibleRouteError,
    LocationNotFoundError,
    RouteNotFoundError,
    RoutingProviderError,
    RoutingProviderTimeoutError,
    StationDataUnavailableError,
    UnsupportedRegionError,
)


@pytest.fixture
def api_client():
    return APIClient()


def test_api_optimize_trip_success(api_client):
    mock_service_response = {
        "trip": {
            "start": {
                "input": "Chicago, IL",
                "resolved": "Chicago, Illinois, USA",
                "latitude": 41.8781,
                "longitude": -87.6298,
            },
            "finish": {
                "input": "Miami, FL",
                "resolved": "Miami, Florida, USA",
                "latitude": 25.7617,
                "longitude": -80.1918,
            },
        },
        "route": {
            "distance_miles": 1375.42,
            "duration_minutes": 1210.3,
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-87.6298, 41.8781],
                    [-80.1918, 25.7617],
                ],
            },
        },
        "vehicle": {
            "max_range_miles": 500,
            "fuel_efficiency_mpg": 10,
            "tank_capacity_gallons": 50,
        },
        "fuel_plan": {
            "starting_fuel_gallons": 50,
            "starting_fuel_cost_usd": None,
            "starting_fuel_cost_included": False,
            "stops": [
                {
                    "opis_id": 101,
                    "name": "Pilot Station",
                    "mile_along_route": 420.3,
                    "off_route_miles": 1.2,
                    "latitude": 36.1627,
                    "longitude": -86.7816,
                    "price_per_gallon_usd": 3.25,
                    "arrival_fuel_gallons": 7.97,
                    "gallons_purchased": 42.03,
                    "departure_fuel_gallons": 50.0,
                    "fuel_cost_usd": 136.60,
                    "geocode_precision": "address",
                    "geocode_source": "census_address",
                }
            ],
            "total_gallons_purchased": 42.03,
            "total_fuel_cost_usd": 136.60,
            "ending_fuel_gallons": 0.0,
        },
        "assumptions": {
            "route_corridor_miles": 10,
            "starting_tank": "full",
            "starting_fuel_cost": "excluded because source price is unknown",
            "off_route_distance": "approximate geographic distance to route, not driving detour distance",
        },
    }

    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        return_value=mock_service_response,
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["trip"]["start"]["input"] == "Chicago, IL"
        assert data["vehicle"]["max_range_miles"] == 500
        assert data["fuel_plan"]["total_fuel_cost_usd"] == 136.60
        assert len(data["fuel_plan"]["stops"]) == 1


def test_api_optimize_trip_invalid_request(api_client):
    url = reverse("trip-optimize")
    response = api_client.post(url, {"start": "", "finish": "Miami, FL"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_REQUEST"


def test_api_optimize_trip_location_not_found(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=LocationNotFoundError("Start location could not be resolved."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "UnknownPlace", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data == {
            "error": {
                "code": "LOCATION_NOT_FOUND",
                "message": "Start location could not be resolved.",
            }
        }


def test_api_optimize_trip_unsupported_region(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=UnsupportedRegionError("Start location 'Toronto, ON' resolves to outside the USA."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Toronto, ON", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["error"]["code"] == "UNSUPPORTED_REGION"


def test_api_optimize_trip_no_feasible_fuel_plan(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=InfeasibleRouteError("No feasible fuel plan could be found for this route."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["error"]["code"] == "NO_FEASIBLE_FUEL_PLAN"


def test_api_optimize_trip_station_data_unavailable(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=StationDataUnavailableError("Fuel station database is empty."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "STATION_DATA_UNAVAILABLE"


def test_api_optimize_trip_provider_error(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=RoutingProviderError("Provider returned an unexpected upstream error."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        data = response.json()
        assert data["error"]["code"] == "ROUTING_PROVIDER_ERROR"


def test_api_optimize_trip_provider_timeout(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=RoutingProviderTimeoutError("Provider request timed out."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Miami, FL"},
            format="json",
        )

        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
        data = response.json()
        assert data["error"]["code"] == "ROUTING_PROVIDER_TIMEOUT"
