from decimal import Decimal
import pytest

from trips.domain.station import MatchedStation
from trips.models import FuelStation
from trips.routing.geometry import RouteGeometry, haversine_distance
from trips.routing.station_matcher import RouteStationMatcher


def test_geometry_known_short_route_distance():
    # Route: 0.1 degree latitude ~ 6.9172 miles
    coords = [[-87.6298, 41.0000], [-87.6298, 41.1000]]
    route_geom = RouteGeometry(coords)
    assert 6.8 < route_geom.total_distance < 7.0


def test_geometry_cumulative_distance_increases():
    coords = [
        [-87.6298, 41.0000],
        [-87.6298, 41.1000],
        [-87.6298, 41.2000],
    ]
    route_geom = RouteGeometry(coords)
    cum = route_geom.cumulative_distances
    assert len(cum) == 3
    assert cum[0] == 0.0
    assert cum[1] < cum[2]


def test_geometry_nearest_point_inside_segment():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    route_geom = RouteGeometry(coords)
    # Station at (-86.0, 41.05) is perpendicular to the middle of segment
    off_route, mile_along = route_geom.find_nearest_point_on_route(41.05, -86.0)
    assert 3.4 < off_route < 3.6
    assert 50.0 < mile_along < 60.0


def test_geometry_nearest_point_at_endpoint():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    route_geom = RouteGeometry(coords)
    # Station at (-88.0, 41.0) is beyond segment start endpoint
    off_route, mile_along = route_geom.find_nearest_point_on_route(41.0, -88.0)
    assert mile_along == 0.0
    assert 50.0 < off_route < 55.0


def test_geometry_lon_lat_order_handled():
    # GeoJSON coords: [lon, lat]
    coords = [[-87.6298, 41.8781], [-87.6298, 42.8781]]
    route_geom = RouteGeometry(coords)
    # First point is lat 41.8781, lon -87.6298
    assert route_geom.points[0] == (41.8781, -87.6298)


def create_dummy_station(
    opis_id: int,
    lat: float,
    lon: float,
    name: str = "Test Station",
    price: str = "3.5000",
    geocode_source: str = "census_address",
    geocode_precision: str = "address",
) -> FuelStation:
    return FuelStation(
        opis_id=opis_id,
        name=name,
        address="123 Main St",
        city="TestCity",
        state="IL",
        rack_id=1,
        effective_price=Decimal(price),
        price_min=Decimal(price),
        price_max=Decimal(price),
        price_observation_count=1,
        source_row_count=1,
        latitude=lat,
        longitude=lon,
        geocode_source=geocode_source,
        geocode_precision=geocode_precision,
    )


def test_corridor_station_directly_on_route():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    station = create_dummy_station(1, 41.0, -86.0)
    matcher = RouteStationMatcher(corridor_miles=10.0)

    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 1
    assert matched[0].off_route_miles == 0.0


def test_corridor_station_clearly_inside():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    # ~3.5 miles off route
    station = create_dummy_station(2, 41.05, -86.0)
    matcher = RouteStationMatcher(corridor_miles=10.0)

    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 1
    assert matched[0].off_route_miles < 10.0


def test_corridor_station_exactly_at_boundary():
    # 0.1445 degrees lat at -86.0 lon is ~10.0 miles
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    station = create_dummy_station(3, 41.1445, -86.0)
    matcher = RouteStationMatcher(corridor_miles=10.0)

    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 1
    assert matched[0].off_route_miles <= 10.0


def test_corridor_station_clearly_outside():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    # ~35 miles north
    station = create_dummy_station(4, 41.5, -86.0)
    matcher = RouteStationMatcher(corridor_miles=10.0)

    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 0


def test_corridor_station_near_bbox_but_outside_corridor():
    # Diagonal segment from (41.0, -87.0) to (42.0, -85.0)
    # Corner of bbox is (42.0, -87.0) which is in bbox, but ~50 miles from diagonal line
    coords = [[-87.0, 41.0], [-85.0, 42.0]]
    station = create_dummy_station(5, 42.0, -87.0)
    matcher = RouteStationMatcher(corridor_miles=10.0)

    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 0


def test_mile_along_route_beginning_middle_end():
    coords = [
        [-87.0, 41.0],
        [-86.0, 41.0],
        [-85.0, 41.0],
    ]
    s_begin = create_dummy_station(10, 41.0, -86.9)
    s_middle = create_dummy_station(11, 41.0, -86.0)
    s_end = create_dummy_station(12, 41.0, -85.1)

    matcher = RouteStationMatcher(corridor_miles=10.0)
    matched = matcher.match_stations_to_route(
        coords, stations=[s_end, s_begin, s_middle]
    )

    assert len(matched) == 3
    # Check ordering by mile_along_route
    assert matched[0].opis_id == 10
    assert matched[1].opis_id == 11
    assert matched[2].opis_id == 12

    assert matched[0].mile_along_route < matched[1].mile_along_route < matched[2].mile_along_route


def test_mile_along_route_monotonic_sorting():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    stations = [
        create_dummy_station(20, 41.0, -85.2),
        create_dummy_station(21, 41.0, -86.8),
        create_dummy_station(22, 41.0, -86.0),
    ]
    matcher = RouteStationMatcher()
    matched = matcher.match_stations_to_route(coords, stations=stations)

    miles = [m.mile_along_route for m in matched]
    assert miles == sorted(miles)


def test_data_quality_unresolved_station_excluded():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    unresolved_station = FuelStation(
        opis_id=99,
        name="Unresolved",
        address="Address",
        city="City",
        state="IL",
        rack_id=1,
        effective_price=Decimal("3.00"),
        price_min=Decimal("3.00"),
        price_max=Decimal("3.00"),
        price_observation_count=1,
        source_row_count=1,
        latitude=None,
        longitude=None,
        geocode_source="unresolved",
        geocode_precision="unresolved",
    )
    matcher = RouteStationMatcher()
    matched = matcher.match_stations_to_route(coords, stations=[unresolved_station])
    assert len(matched) == 0


def test_data_quality_precision_metadata_preserved():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    addr_station = create_dummy_station(
        100, 41.0, -86.5, geocode_source="census_address", geocode_precision="address"
    )
    city_station = create_dummy_station(
        101, 41.0, -86.2, geocode_source="census_place_centroid", geocode_precision="city"
    )

    matcher = RouteStationMatcher()
    matched = matcher.match_stations_to_route(coords, stations=[addr_station, city_station])

    assert len(matched) == 2
    s_addr = next(m for m in matched if m.opis_id == 100)
    s_city = next(m for m in matched if m.opis_id == 101)

    assert s_addr.geocode_source == "census_address"
    assert s_addr.geocode_precision == "address"

    assert s_city.geocode_source == "census_place_centroid"
    assert s_city.geocode_precision == "city"


def test_edge_cases_route_fewer_than_two_coordinates():
    matcher = RouteStationMatcher()
    with pytest.raises(ValueError):
        matcher.match_stations_to_route([[-87.0, 41.0]])


def test_edge_cases_malformed_coordinate():
    matcher = RouteStationMatcher()
    with pytest.raises(ValueError):
        matcher.match_stations_to_route([[-87.0, 41.0], ["invalid", "invalid"]])


def test_edge_cases_empty_station_set():
    coords = [[-87.0, 41.0], [-85.0, 41.0]]
    matcher = RouteStationMatcher()
    matched = matcher.match_stations_to_route(coords, stations=[])
    assert matched == []


def test_edge_cases_duplicate_route_coordinates_do_not_crash():
    coords = [
        [-87.0, 41.0],
        [-87.0, 41.0],  # Duplicate point
        [-85.0, 41.0],
    ]
    station = create_dummy_station(30, 41.0, -86.0)
    matcher = RouteStationMatcher()
    matched = matcher.match_stations_to_route(coords, stations=[station])
    assert len(matched) == 1
