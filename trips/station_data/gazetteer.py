import csv
import io
import re
from typing import Dict, List, Optional, Tuple


def normalize_city_name(city: str) -> str:
    cleaned = city.strip().lower()
    # Replace multiple spaces with single space
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Strip common census place suffixes
    suffixes = [
        " city and borough",
        " city",
        " town",
        " village",
        " cdp",
        " borough",
        " municipality",
        " township",
        " plantation",
        " location",
        " reservation",
    ]
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break
    # Remove punctuation like periods or apostrophes
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return cleaned


class CensusPlaceResolver:
    def __init__(self, gazetteer_data: Optional[Dict[Tuple[str, str], Tuple[float, float]]] = None):
        # Key: (normalized_city, state_code) -> (lat, lon)
        self.places: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}
        if gazetteer_data:
            for (city, state), (lat, lon) in gazetteer_data.items():
                norm_city = normalize_city_name(city)
                key = (norm_city, state.upper().strip())
                if key not in self.places:
                    self.places[key] = []
                self.places[key].append((lat, lon))

    def load_gazetteer_file(self, file_or_path_or_str: io.TextIOBase | str) -> None:
        if isinstance(file_or_path_or_str, str):
            if "\n" in file_or_path_or_str or "\r" in file_or_path_or_str:
                self._parse_file(io.StringIO(file_or_path_or_str))
            else:
                with open(file_or_path_or_str, "r", encoding="utf-8", errors="ignore") as f:
                    self._parse_file(f)
        else:
            self._parse_file(file_or_path_or_str)

    def _parse_file(self, f: io.TextIOBase) -> None:
        content = f.read()
        lines = content.splitlines()
        if not lines:
            return

        first_line = lines[0]
        if "|" in first_line:
            delimiter = "|"
        elif "\t" in first_line:
            delimiter = "\t"
        else:
            delimiter = ","

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

        for row in reader:
            clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
            state = clean_row.get("USPS", clean_row.get("State", "")).upper()
            name = clean_row.get("NAME", clean_row.get("Name", ""))
            lat_str = clean_row.get("INTPTLAT", clean_row.get("Latitude", ""))
            lon_str = clean_row.get("INTPTLONG", clean_row.get("Longitude", ""))

            if state and name and lat_str and lon_str:
                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                    norm_city = normalize_city_name(name)
                    key = (norm_city, state)
                    if key not in self.places:
                        self.places[key] = []
                    self.places[key].append((lat, lon))
                except ValueError:
                    continue

    def resolve(self, city: str, state: str) -> Optional[Tuple[float, float]]:
        norm_city = normalize_city_name(city)
        key = (norm_city, state.upper().strip())

        matches = self.places.get(key, [])
        if len(matches) == 1:
            return matches[0]
        # Ambiguous (>1) or unmatched (0)
        return None
