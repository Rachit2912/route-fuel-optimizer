from unittest.mock import MagicMock, patch
import pytest
import requests

from trips.domain.location import ResolvedLocation
from trips.exceptions import (
    LocationNotFoundError,
    RouteNotFoundError,
    RoutingProviderError,
    RoutingProviderTimeoutError,
)
from trips.providers.openrouteservice import OpenRouteServiceProvider


@pytest.fixture
def provider():
    return OpenRouteServiceProvider(api_key="test-api-key")


def test_geocode_success(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "features": [
            {
                "geometry": {"coordinates": [-87.6298, 41.8781]},
                "properties": {
                    "label": "Chicago, Illinois, USA",
                    "country": "United States",
                },
            }
        ]
    }

    with patch("requests.get", return_value=mock_response) as mock_get:
        result = provider.geocode("Chicago, IL")
        mock_get.assert_called_once()
        assert result.input == "Chicago, IL"
        assert result.label == "Chicago, Illinois, USA"
        assert result.lat == 41.8781
        assert result.lon == -87.6298
        assert result.country == "United States"


def test_geocode_location_not_found(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"features": []}

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(LocationNotFoundError):
            provider.geocode("NonexistentLocation12345")


def test_geocode_timeout(provider):
    with patch("requests.get", side_effect=requests.Timeout("Connection timed out")):
        with pytest.raises(RoutingProviderTimeoutError):
            provider.geocode("Chicago, IL")


def test_geocode_http_error(provider):
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(RoutingProviderError):
            provider.geocode("Chicago, IL")


def test_geocode_malformed_json(provider):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch("requests.get", return_value=mock_response):
        with pytest.raises(RoutingProviderError):
            provider.geocode("Chicago, IL")


def test_get_route_success(provider):
    start = ResolvedLocation(
        input="Chicago, IL",
        label="Chicago, Illinois, USA",
        lat=41.8781,
        lon=-87.6298,
        country="United States",
    )
    finish = ResolvedLocation(
        input="Miami, FL",
        label="Miami, Florida, USA",
        lat=25.7617,
        lon=-80.1918,
        country="United States",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-87.6298, 41.8781],
                        [-80.1918, 25.7617],
                    ],
                },
                "properties": {
                    "summary": {
                        "distance": 2213516.0,  # 1375.42 miles
                        "duration": 72618.0,    # 1210.3 minutes
                    }
                },
            }
        ]
    }

    with patch("requests.post", return_value=mock_response) as mock_post:
        route = provider.get_route(start, finish)
        mock_post.assert_called_once()
        assert route.distance_miles == 1375.42
        assert route.duration_minutes == 1210.3
        assert route.geometry["type"] == "LineString"


def test_get_route_not_found(provider):
    start = ResolvedLocation("Start", "Start", 0.0, 0.0)
    finish = ResolvedLocation("Finish", "Finish", 0.0, 0.0)

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("requests.post", return_value=mock_response):
        with pytest.raises(RouteNotFoundError):
            provider.get_route(start, finish)


def test_get_route_timeout(provider):
    start = ResolvedLocation("Start", "Start", 0.0, 0.0)
    finish = ResolvedLocation("Finish", "Finish", 0.0, 0.0)

    with patch("requests.post", side_effect=requests.Timeout("Timeout")):
        with pytest.raises(RoutingProviderTimeoutError):
            provider.get_route(start, finish)
