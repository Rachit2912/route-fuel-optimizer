from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
import requests

from trips.station_data.canonicalizer import CanonicalStation
from trips.station_data.gazetteer import CensusPlaceResolver
from trips.station_data.geocoding import (
    CensusBatchGeocoder,
    CensusGeocodingError,
    StationGeocoder,
)


@pytest.fixture
def sample_station():
    return CanonicalStation(
        opis_id=100,
        name="Pilot Center",
        address="123 Main St",
        city="Chicago",
        state="IL",
        rack_id=1,
        effective_price=Decimal("3.5000"),
        price_min=Decimal("3.5000"),
        price_max=Decimal("3.5000"),
        price_observation_count=1,
        source_row_count=1,
    )


def test_census_batch_geocoder_success(sample_station):
    # Mock census response format
    # "100","123 Main St, Chicago, IL, ","Match","Exact","123 MAIN ST, CHICAGO, IL, 60601","-87.6298,41.8781","123456","R"
    mock_csv_response = '"100","123 Main St","Match","Exact","123 MAIN ST, CHICAGO, IL","-87.6298,41.8781","1234","R"\n'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_csv_response

    geocoder = CensusBatchGeocoder()

    with patch("requests.post", return_value=mock_response):
        results = geocoder.geocode_batch([sample_station])
        assert 100 in results
        lat, lon = results[100]
        assert lat == 41.8781
        assert lon == -87.6298


def test_census_batch_geocoder_no_match(sample_station):
    mock_csv_response = '"100","I-44 Exit 283","No_Match","","","","",""\n'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_csv_response

    geocoder = CensusBatchGeocoder()

    with patch("requests.post", return_value=mock_response):
        results = geocoder.geocode_batch([sample_station])
        assert 100 not in results


def test_census_batch_geocoder_request_exception(sample_station):
    geocoder = CensusBatchGeocoder()

    with patch("requests.post", side_effect=requests.RequestException("Connection error")):
        with pytest.raises(CensusGeocodingError):
            geocoder.geocode_batch([sample_station])


def test_gazetteer_place_resolver_suffix_and_resolution():
    gazetteer_data = {
        ("Chicago city", "IL"): (41.8781, -87.6298),
        ("Dallas town", "TX"): (32.7767, -96.7970),
    }
    resolver = CensusPlaceResolver(gazetteer_data)

    # Search with "Chicago" should strip " city" and match
    assert resolver.resolve("Chicago", "IL") == (41.8781, -87.6298)
    assert resolver.resolve("Dallas", "TX") == (32.7767, -96.7970)
    assert resolver.resolve("UnknownCity", "IL") is None


def test_gazetteer_ambiguous_city_returns_none():
    gazetteer_content = (
        "USPS\tNAME\tINTPTLAT\tINTPTLONG\n"
        "TX\tSpring city\t30.0799\t-95.4172\n"
        "TX\tSpring CDP\t30.0800\t-95.4170\n"
    )
    resolver = CensusPlaceResolver()
    resolver.load_gazetteer_file(gazetteer_content)

    # Both resolve to "spring", TX -> ambiguous (>1 match)
    assert resolver.resolve("Spring", "TX") is None


def test_station_geocoder_fallback_to_gazetteer(sample_station):
    # Address batch returns no match for station 100
    mock_batch_geocoder = MagicMock()
    mock_batch_geocoder.geocode_batch.return_value = {}

    place_resolver = CensusPlaceResolver({("Chicago", "IL"): (41.8781, -87.6298)})

    station_geocoder = StationGeocoder(
        batch_geocoder=mock_batch_geocoder,
        place_resolver=place_resolver,
    )

    results = station_geocoder.geocode_stations([sample_station])
    assert len(results) == 1
    res = results[0]
    assert res.latitude == 41.8781
    assert res.longitude == -87.6298
    assert res.geocode_source == "census_place_centroid"
    assert res.geocode_precision == "city"


def test_station_geocoder_unresolved_station(sample_station):
    mock_batch_geocoder = MagicMock()
    mock_batch_geocoder.geocode_batch.return_value = {}

    place_resolver = CensusPlaceResolver({})

    station_geocoder = StationGeocoder(
        batch_geocoder=mock_batch_geocoder,
        place_resolver=place_resolver,
    )

    results = station_geocoder.geocode_stations([sample_station])
    assert len(results) == 1
    res = results[0]
    assert res.latitude is None
    assert res.longitude is None
    assert res.geocode_source == "unresolved"
    assert res.geocode_precision == "unresolved"
