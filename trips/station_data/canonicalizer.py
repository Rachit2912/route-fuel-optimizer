from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import io
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

CONTIGUOUS_US_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "DC",
}

REQUIRED_CSV_COLUMNS = [
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
]


class CSVValidationError(Exception):
    pass


@dataclass(frozen=True)
class CanonicalStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: Optional[int]
    effective_price: Decimal
    price_min: Decimal
    price_max: Decimal
    price_observation_count: int
    source_row_count: int


@dataclass
class CanonicalizationSummary:
    total_source_rows: int = 0
    exact_duplicates_removed: int = 0
    unsupported_region_rows_removed: int = 0
    invalid_rows_removed: int = 0
    location_conflicts_rejected: int = 0
    canonical_stations_produced: int = 0


class StationCanonicalizer:
    def process_csv(
        self, csv_file_or_path: io.TextIOBase | str
    ) -> Tuple[List[CanonicalStation], CanonicalizationSummary]:
        if isinstance(csv_file_or_path, str):
            with open(csv_file_or_path, "r", encoding="utf-8-sig") as f:
                return self._parse_and_canonicalize(f)
        return self._parse_and_canonicalize(csv_file_or_path)

    def _parse_and_canonicalize(
        self, f: io.TextIOBase
    ) -> Tuple[List[CanonicalStation], CanonicalizationSummary]:
        summary = CanonicalizationSummary()
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise CSVValidationError("CSV file is empty or missing headers.")

        # Strip whitespace from headers
        headers = [h.strip() for h in reader.fieldnames if h]
        for col in REQUIRED_CSV_COLUMNS:
            if col not in headers:
                raise CSVValidationError(f"Missing required CSV column: '{col}'")

        raw_rows = []
        for row in reader:
            summary.total_source_rows += 1
            # Clean keys/values
            clean_row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
            raw_rows.append(clean_row)

        # Step 1: Remove exact duplicate rows
        unique_rows = []
        seen_exact_rows = set()
        for row in raw_rows:
            row_tuple = tuple((col, row.get(col, "")) for col in REQUIRED_CSV_COLUMNS)
            if row_tuple in seen_exact_rows:
                summary.exact_duplicates_removed += 1
            else:
                seen_exact_rows.add(row_tuple)
                unique_rows.append(row)

        # Step 2: Filter non-contiguous US states & validate fields
        valid_rows = []
        for row in unique_rows:
            state = row.get("State", "").upper()
            if state not in CONTIGUOUS_US_STATES:
                summary.unsupported_region_rows_removed += 1
                continue

            # Validate OPIS ID and Retail Price
            opis_str = row.get("OPIS Truckstop ID", "")
            price_str = row.get("Retail Price", "")

            try:
                opis_id = int(opis_str)
                price = Decimal(price_str)
            except (ValueError, InvalidOperation):
                summary.invalid_rows_removed += 1
                continue

            row_data = {
                "opis_id": opis_id,
                "name": row.get("Truckstop Name", "").strip(),
                "address": row.get("Address", "").strip(),
                "city": row.get("City", "").strip(),
                "state": state,
                "rack_id": int(row.get("Rack ID")) if row.get("Rack ID") and row.get("Rack ID").isdigit() else None,
                "price": price,
            }
            valid_rows.append(row_data)

        # Step 3: Group by OPIS ID
        grouped = defaultdict(list)
        for row in valid_rows:
            grouped[row["opis_id"]].append(row)

        canonical_stations = []

        for opis_id, rows in sorted(grouped.items()):
            # Check location identity stability across rows
            addresses = set(r["address"].lower() for r in rows)
            cities = set(r["city"].lower() for r in rows)
            states = set(r["state"].upper() for r in rows)
            rack_ids = set(r["rack_id"] for r in rows)

            if len(addresses) > 1 or len(cities) > 1 or len(states) > 1 or len(rack_ids) > 1:
                summary.location_conflicts_rejected += 1
                logger.warning(
                    f"OPIS ID {opis_id} has conflicting location metadata: "
                    f"addresses={addresses}, cities={cities}, states={states}, rack_ids={rack_ids}"
                )
                continue

            # Deterministic canonical name selection:
            # 1. Frequency of non-empty names
            # 2. Lexical tie-break
            name_counts = Counter(r["name"] for r in rows if r["name"])
            if name_counts:
                # Most frequent name; if tie, sort alphabetically
                max_count = max(name_counts.values())
                top_names = [name for name, count in name_counts.items() if count == max_count]
                canonical_name = sorted(top_names)[0]
            else:
                canonical_name = f"Truckstop #{opis_id}"

            base_row = rows[0]

            # Price aggregation: mean of DISTINCT reported prices using Decimal
            all_prices = [r["price"] for r in rows]
            distinct_prices = sorted(list(set(all_prices)))

            effective_price = sum(distinct_prices) / Decimal(len(distinct_prices))
            effective_price = effective_price.quantize(Decimal("0.0001"))

            price_min = min(all_prices)
            price_max = max(all_prices)
            price_observation_count = len(distinct_prices)
            source_row_count = len(rows)

            canonical_station = CanonicalStation(
                opis_id=opis_id,
                name=canonical_name,
                address=base_row["address"],
                city=base_row["city"],
                state=base_row["state"],
                rack_id=base_row["rack_id"],
                effective_price=effective_price,
                price_min=price_min,
                price_max=price_max,
                price_observation_count=price_observation_count,
                source_row_count=source_row_count,
            )
            canonical_stations.append(canonical_station)

        summary.canonical_stations_produced = len(canonical_stations)
        return canonical_stations, summary
