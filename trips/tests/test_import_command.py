from decimal import Decimal
import io
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
import pytest

from trips.models import FuelStation
from trips.station_data.canonicalizer import CanonicalStation
from trips.station_data.geocoding import GeocodedStationResult
from trips.station_data.repository import FuelStationRepository


@pytest.mark.django_db
def test_repository_save_and_idempotency():
    station = CanonicalStation(
        opis_id=101,
        name="Pilot Station",
        address="100 Highway 1",
        city="Dallas",
        state="TX",
        rack_id=5,
        effective_price=Decimal("3.2500"),
        price_min=Decimal("3.2000"),
        price_max=Decimal("3.3000"),
        price_observation_count=2,
        source_row_count=2,
    )
    geocoded = GeocodedStationResult(
        station=station,
        latitude=32.7767,
        longitude=-96.7970,
        geocode_source="census_address",
        geocode_precision="address",
    )

    repo = FuelStationRepository()

    # First run -> created=1, updated=0
    created, updated = repo.save_geocoded_stations([geocoded])
    assert created == 1
    assert updated == 0
    assert FuelStation.objects.count() == 1

    db_station = FuelStation.objects.get(opis_id=101)
    assert db_station.name == "Pilot Station"
    assert db_station.effective_price == Decimal("3.2500")
    assert db_station.latitude == 32.7767

    # Second run with same data -> created=0, updated=1
    created2, updated2 = repo.save_geocoded_stations([geocoded])
    assert created2 == 0
    assert updated2 == 1
    assert FuelStation.objects.count() == 1


@pytest.mark.django_db
def test_import_command_success():
    csv_content = (
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "500,Loves Travel Center,123 Main St,Chicago,IL,10,3.4500\n"
    )

    with tempfile.NamedTemporaryFile("w+", suffix=".csv", delete=False) as tf:
        tf.write(csv_content)
        tf.flush()
        csv_path = tf.name

    out = io.StringIO()
    call_command("import_fuel_stations", f"--csv={csv_path}", stdout=out)

    output = out.getvalue()
    assert "Fuel Station Import Complete!" in output
    assert "Database rows created:       1" in output
    assert FuelStation.objects.filter(opis_id=500).exists()


@pytest.mark.django_db
def test_import_command_file_not_found():
    with pytest.raises(CommandError) as exc_info:
        call_command("import_fuel_stations", "--csv=/nonexistent/file.csv")
    assert "CSV file not found" in str(exc_info.value)
