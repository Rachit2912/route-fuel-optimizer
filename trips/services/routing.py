from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult
from trips.providers.base import BaseRoutingProvider


class RoutingService:
    def __init__(self, provider: BaseRoutingProvider):
        self.provider = provider

    def calculate_route(
        self, start: ResolvedLocation, finish: ResolvedLocation
    ) -> RouteResult:
        return self.provider.get_route(start, finish)
