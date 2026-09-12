from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResolvedLocation:
    input: str
    label: str
    lat: float
    lon: float
    country: Optional[str] = None
