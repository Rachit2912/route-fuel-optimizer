from unittest.mock import patch
from django.urls import reverse
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from trips.exceptions import (
    LocationNotFoundError,
    RouteNotFoundError,
    RoutingProviderError,
    RoutingProviderTimeoutError,
    UnsupportedRegionError,
)


@pytest.fixture
def api_client():
    return APIClient()


def test_api_optimize_trip_success(api_client):
    mock_service_response = {
        "start": {
            "input": "Chicago, IL",
            "label": "Chicago, Illinois, USA",
            "lat": 41.8781,
            "lon": -87.6298,
        },
        "finish": {
            "input": "Miami, FL",
            "label": "Miami, Florida, USA",
            "lat": 25.7617,
            "lon": -80.1918,
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
        assert response.json() == mock_service_response


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


def test_api_optimize_trip_route_not_found(api_client):
    with patch(
        "trips.views.TripOptimizationService.optimize_trip",
        side_effect=RouteNotFoundError("Provider cannot find a drivable route."),
    ):
        url = reverse("trip-optimize")
        response = api_client.post(
            url,
            {"start": "Chicago, IL", "finish": "Honolulu, HI"},
            format="json",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["error"]["code"] == "ROUTE_NOT_FOUND"


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
