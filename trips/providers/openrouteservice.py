from typing import Any, Dict, Optional
import requests
from django.conf import settings

from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult
from trips.exceptions import (
    LocationNotFoundError,
    RouteNotFoundError,
    RoutingProviderError,
    RoutingProviderTimeoutError,
)
from trips.providers.base import BaseRoutingProvider

METERS_PER_MILE = 1609.344
SECONDS_PER_MINUTE = 60.0


class OpenRouteServiceProvider(BaseRoutingProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or getattr(settings, "OPENROUTESERVICE_API_KEY", "")
        self.base_url = (
            base_url or getattr(settings, "OPENROUTESERVICE_BASE_URL", "https://api.heigit.org")
        ).rstrip("/")
        self.timeout = timeout

    @property
    def geocode_url(self) -> str:
        return f"{self.base_url}/pelias/v1/search"

    @property
    def routing_url(self) -> str:
        return f"{self.base_url}/openrouteservice/v2/directions/driving-car/geojson"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json, application/geo+json"}
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def geocode(self, location: str) -> ResolvedLocation:
        url = self.geocode_url
        params = {"text": location}

        try:
            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            raise RoutingProviderTimeoutError("Geocoding service request timed out.") from e
        except requests.RequestException as e:
            raise RoutingProviderError("Failed to connect to geocoding service.") from e

        if response.status_code != 200:
            raise RoutingProviderError(
                f"Geocoding provider returned status code {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as e:
            raise RoutingProviderError("Malformed JSON response from geocoding service.") from e

        features = data.get("features", [])
        if not features:
            raise LocationNotFoundError(f"Location '{location}' could not be resolved.")

        first_feature = features[0]
        try:
            geometry = first_feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])
            lon, lat = float(coordinates[0]), float(coordinates[1])
            properties = first_feature.get("properties", {})
            label = properties.get("label", location)
            country = properties.get("country")
        except (IndexError, TypeError, ValueError, KeyError) as e:
            raise RoutingProviderError("Malformed feature in geocoding response.") from e

        return ResolvedLocation(
            input=location,
            label=label,
            lat=lat,
            lon=lon,
            country=country,
        )

    def get_route(
        self, start: ResolvedLocation, finish: ResolvedLocation
    ) -> RouteResult:
        url = self.routing_url
        payload = {
            "coordinates": [
                [start.lon, start.lat],
                [finish.lon, finish.lat],
            ]
        }
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            raise RoutingProviderTimeoutError("Routing service request timed out.") from e
        except requests.RequestException as e:
            raise RoutingProviderError("Failed to connect to routing service.") from e

        if response.status_code in (404, 422):
            raise RouteNotFoundError(
                f"No drivable route found between ({start.lat}, {start.lon}) and ({finish.lat}, {finish.lon})."
            )
        elif response.status_code != 200:
            raise RoutingProviderError(
                f"Routing provider returned status code {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as e:
            raise RoutingProviderError("Malformed JSON response from routing service.") from e

        features = data.get("features", [])
        if not features:
            raise RouteNotFoundError("No route features found in response.")

        first_feature = features[0]
        try:
            geometry = first_feature.get("geometry", {})
            if not geometry or geometry.get("type") != "LineString":
                raise RoutingProviderError("Missing or invalid LineString geometry in route response.")

            properties = first_feature.get("properties", {})
            summary = properties.get("summary", {})
            distance_meters = float(summary["distance"])
            duration_seconds = float(summary["duration"])
        except (KeyError, TypeError, ValueError) as e:
            raise RoutingProviderError("Malformed route summary or geometry in response.") from e

        distance_miles = round(distance_meters / METERS_PER_MILE, 2)
        duration_minutes = round(duration_seconds / SECONDS_PER_MINUTE, 2)

        return RouteResult(
            distance_miles=distance_miles,
            duration_minutes=duration_minutes,
            geometry=geometry,
        )
