from abc import ABC, abstractmethod
from trips.domain.location import ResolvedLocation
from trips.domain.route import RouteResult


class BaseRoutingProvider(ABC):
    @abstractmethod
    def geocode(self, location: str) -> ResolvedLocation:
        """Geocodes a location text into a ResolvedLocation."""
        pass

    @abstractmethod
    def get_route(
        self, start: ResolvedLocation, finish: ResolvedLocation
    ) -> RouteResult:
        """Calculates a driving route between start and finish locations."""
        pass
