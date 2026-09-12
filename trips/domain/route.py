from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class RouteResult:
    distance_miles: float
    duration_minutes: float
    geometry: Dict[str, Any]
