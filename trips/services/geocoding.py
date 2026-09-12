from trips.domain.location import ResolvedLocation
from trips.providers.base import BaseRoutingProvider


class GeocodingService:
    def __init__(self, provider: BaseRoutingProvider):
        self.provider = provider

    def resolve(self, location: str) -> ResolvedLocation:
        return self.provider.geocode(location)
