from decimal import Decimal
import io
import pytest

from trips.station_data.canonicalizer import (
    CSVValidationError,
    StationCanonicalizer,
)


def create_csv_content(rows_dicts):
    headers = [
        "OPIS Truckstop ID",
        "Truckstop Name",
        "Address",
        "City",
        "State",
        "Rack ID",
        "Retail Price",
    ]
    lines = [",".join(headers)]
    for row in rows_dicts:
        line = ",".join(str(row.get(h, "")) for h in headers)
        lines.append(line)
    return "\n".join(lines)


def test_canonicalize_normal_unique_station():
    csv_data = create_csv_content(
        [
            {
                "OPIS Truckstop ID": "100",
                "Truckstop Name": "Pilot Travel Center",
                "Address": "123 Main St",
                "City": "Chicago",
                "State": "IL",
                "Rack ID": "12",
                "Retail Price": "3.5000",
            }
        ]
    )
    canonicalizer = StationCanonicalizer()
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 1
    station = stations[0]
    assert station.opis_id == 100
    assert station.name == "Pilot Travel Center"
    assert station.address == "123 Main St"
    assert station.city == "Chicago"
    assert station.state == "IL"
    assert station.rack_id == 12
    assert station.effective_price == Decimal("3.5000")
    assert station.price_min == Decimal("3.5000")
    assert station.price_max == Decimal("3.5000")
    assert station.price_observation_count == 1
    assert station.source_row_count == 1


def test_canonicalize_exact_duplicate_rows():
    row = {
        "OPIS Truckstop ID": "100",
        "Truckstop Name": "Pilot Travel Center",
        "Address": "123 Main St",
        "City": "Chicago",
        "State": "IL",
        "Rack ID": "12",
        "Retail Price": "3.5000",
    }
    csv_data = create_csv_content([row, row, row])
    canonicalizer = StationCanonicalizer()
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 1
    assert summary.exact_duplicates_removed == 2
    assert summary.total_source_rows == 3
    assert stations[0].source_row_count == 1
    assert stations[0].effective_price == Decimal("3.5000")


def test_canonicalize_distinct_price_average():
    rows = [
        {
            "OPIS Truckstop ID": "123",
            "Truckstop Name": "Speedway",
            "Address": "I-44 Exit 1",
            "City": "St Louis",
            "State": "MO",
            "Rack ID": "5",
            "Retail Price": "3.2000",
        },
        {
            "OPIS Truckstop ID": "123",
            "Truckstop Name": "Speedway",
            "Address": "I-44 Exit 1",
            "City": "St Louis",
            "State": "MO",
            "Rack ID": "5",
            "Retail Price": "3.2000",
        },
        {
            "OPIS Truckstop ID": "123",
            "Truckstop Name": "Speedway Inc",
            "Address": "I-44 Exit 1",
            "City": "St Louis",
            "State": "MO",
            "Rack ID": "5",
            "Retail Price": "3.4000",
        },
    ]
    csv_data = create_csv_content(rows)
    canonicalizer = StationCanonicalizer()
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 1
    s = stations[0]
    # Distinct prices: 3.20, 3.40 => mean 3.30
    assert s.effective_price == Decimal("3.3000")
    assert s.price_min == Decimal("3.2000")
    assert s.price_max == Decimal("3.4000")
    assert s.price_observation_count == 2
    assert s.source_row_count == 2  # 2 unique rows (1 exact dup removed)


def test_canonicalize_name_aliases_and_tie_breaking():
    rows = [
        {
            "OPIS Truckstop ID": "200",
            "Truckstop Name": "Loves Travel Stop",
            "Address": "456 Highway 1",
            "City": "Atlanta",
            "State": "GA",
            "Rack ID": "10",
            "Retail Price": "3.00",
        },
        {
            "OPIS Truckstop ID": "200",
            "Truckstop Name": "Love's #123",
            "Address": "456 Highway 1",
            "City": "Atlanta",
            "State": "GA",
            "Rack ID": "10",
            "Retail Price": "3.10",
        },
        {
            "OPIS Truckstop ID": "200",
            "Truckstop Name": "Loves Travel Stop",
            "Address": "456 Highway 1",
            "City": "Atlanta",
            "State": "GA",
            "Rack ID": "10",
            "Retail Price": "3.20",
        },
    ]
    csv_data = create_csv_content(rows)
    canonicalizer = StationCanonicalizer()
    stations, _ = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 1
    assert stations[0].name == "Loves Travel Stop"  # Most frequent name


def test_canonicalize_excludes_canada_and_non_contiguous_us():
    rows = [
        {
            "OPIS Truckstop ID": "1",
            "Truckstop Name": "Irving",
            "Address": "1 Trans Canada Hwy",
            "City": "Toronto",
            "State": "ON",
            "Rack ID": "1",
            "Retail Price": "1.50",
        },
        {
            "OPIS Truckstop ID": "2",
            "Truckstop Name": "Alaska Fuel",
            "Address": "1 Alaska Hwy",
            "City": "Anchorage",
            "State": "AK",
            "Rack ID": "1",
            "Retail Price": "4.50",
        },
        {
            "OPIS Truckstop ID": "3",
            "Truckstop Name": "Hawaii Stop",
            "Address": "1 Beach Rd",
            "City": "Honolulu",
            "State": "HI",
            "Rack ID": "1",
            "Retail Price": "5.00",
        },
        {
            "OPIS Truckstop ID": "4",
            "Truckstop Name": "Texas Stop",
            "Address": "100 Interstate 35",
            "City": "Dallas",
            "State": "TX",
            "Rack ID": "1",
            "Retail Price": "3.10",
        },
    ]
    csv_data = create_csv_content(rows)
    canonicalizer = StationCanonicalizer()
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 1
    assert stations[0].opis_id == 4
    assert summary.unsupported_region_rows_removed == 3


def test_canonicalize_conflicting_location_rejected():
    rows = [
        {
            "OPIS Truckstop ID": "300",
            "Truckstop Name": "Station A",
            "Address": "100 First St",
            "City": "Dallas",
            "State": "TX",
            "Rack ID": "1",
            "Retail Price": "3.00",
        },
        {
            "OPIS Truckstop ID": "300",
            "Truckstop Name": "Station B",
            "Address": "999 Other St",  # Conflict!
            "City": "Dallas",
            "State": "TX",
            "Rack ID": "1",
            "Retail Price": "3.50",
        },
    ]
    csv_data = create_csv_content(rows)
    canonicalizer = StationCanonicalizer(reject_location_conflicts=True)
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 0
    assert summary.location_conflicts_rejected == 1


def test_canonicalize_missing_required_column():
    csv_data = "OPIS Truckstop ID,Truckstop Name,Address\n100,Test,123 Main"
    canonicalizer = StationCanonicalizer()
    with pytest.raises(CSVValidationError):
        canonicalizer.process_csv(io.StringIO(csv_data))


def test_canonicalize_invalid_price():
    rows = [
        {
            "OPIS Truckstop ID": "400",
            "Truckstop Name": "Bad Price Station",
            "Address": "123 Main St",
            "City": "Chicago",
            "State": "IL",
            "Rack ID": "1",
            "Retail Price": "invalid_price",
        }
    ]
    csv_data = create_csv_content(rows)
    canonicalizer = StationCanonicalizer()
    stations, summary = canonicalizer.process_csv(io.StringIO(csv_data))

    assert len(stations) == 0
    assert summary.invalid_rows_removed == 1
