# Route Fuel Optimizer

Django REST API for the Spotter AI Backend Engineer assessment. Given a start and finish location in the contiguous United States, the service returns a driving route, cost-conscious fuel stops along that route, and the total fuel spend.

## Highlights

- Django + Django REST Framework
- HeiGIT / openrouteservice for runtime geocoding and routing
- One directions request per trip; no routing request per fuel station
- Offline preprocessing of the provided OPIS fuel-price CSV
- Census Batch Geocoder with Census Places Gazetteer fallback
- Route-station matching using geographic distance and a 10-mile corridor
- In-memory chunked spatial prefilter for fast matching
- Greedy next-cheaper-station fuel optimization
- 500-mile vehicle range, 10 MPG, 50-gallon tank
- Structured domain/API errors
- Unit and integration tests with no real HTTP calls

## Architecture

```text
POST /api/v1/trips/optimize/
        |
        v
TripOptimizationService
        |
        +--> GeocodingService ------> HeiGIT geocoding
        |
        +--> RoutingService --------> HeiGIT/openrouteservice directions
        |
        +--> FuelStationRepository -> preprocessed FuelStation rows
        |
        +--> RouteStationMatcher ---> 10-mile route corridor
        |
        +--> FuelOptimizer ---------> purchasing plan + total cost
```

Fuel-station ingestion is intentionally outside the request path:

```text
provided CSV
   -> schema validation / cleanup
   -> contiguous-US filtering
   -> OPIS canonicalization
   -> distinct-price aggregation
   -> Census batch geocoding
   -> Census Places fallback
   -> FuelStation persistence
```

## Core assumptions

- Maximum vehicle range: **500 miles**
- Fuel efficiency: **10 MPG**
- Tank capacity: **50 gallons**
- Vehicle starts with a **full 50-gallon tank**
- The price of the initial tank is unknown, so its acquisition cost is **excluded** from `total_fuel_cost_usd`
- Fuel prices are treated as USD/gallon
- Stations are matched within a configurable internal corridor; default: **10 miles**
- `off_route_miles` is approximate geographic distance from the station coordinate to the route, not driving detour distance
- City-centroid fallback coordinates are explicitly marked as approximate via `geocode_precision`
- Fuel consumption does not add an estimated detour to/from a station
- The supplied dataset is treated as the source of fuel prices

### Duplicate price policy

The source CSV contains repeated OPIS station IDs and multiple observed prices without timestamps. The importer:

1. removes exact duplicate rows,
2. groups records by OPIS station ID,
3. averages the **distinct reported prices** into `effective_price`,
4. preserves min/max price and observation counts.

This avoids arbitrarily selecting a lowest price when no timestamp is available to determine which observation is current.

## Requirements

- Python compatible with Django 6.0
- A HeiGIT/openrouteservice API key
- Internet access for the one-time Census station geocoding import and runtime route/geocoding requests

## Setup

```bash
git clone https://github.com/Rachit2912/route-fuel-optimizer.git
cd route-fuel-optimizer

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Set your API key in `.env`:

```env
OPENROUTESERVICE_API_KEY=your_api_key_here
```

Create the database schema:

```bash
python manage.py migrate
```

## Import the fuel-station dataset

The repository includes the assessment fuel-price CSV:

```text
fuel-prices-for-be-assessment.csv
```

For Census place-centroid fallback, this project uses the U.S. Census **2025 National Places Gazetteer**.

The exact file used during development is also included in the repository root as:

```text
2025_Gaz_place_national.txt
```

So the recommended import works immediately after cloning:

```bash
python manage.py import_fuel_stations \
  --csv fuel-prices-for-be-assessment.csv \
  --gazetteer 2025_Gaz_place_national.txt
```

The Gazetteer is used only as a fallback when the Census address geocoder cannot resolve highway/exit-style station addresses.

If the bundled Gazetteer file is ever missing, it can be downloaded again from the official U.S. Census source:

* 2025 Gazetteer page: https://www.census.gov/geographies/reference-files/2025/geo/gazetter-file.html
* Direct National Places ZIP: https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip

After downloading, extract:

```text
2025_Gaz_place_national.txt
```

and place it in the repository root before running the import command above.

The import pipeline:

1. validates the supplied CSV,
2. filters unsupported/non-contiguous-US records,
3. removes exact duplicate rows,
4. canonicalizes records by OPIS station ID,
5. computes `effective_price` from distinct reported prices,
6. batch-geocodes station addresses using the U.S. Census geocoder,
7. falls back to Census place-centroid coordinates when address-level geocoding fails,
8. persists the canonical `FuelStation` records.

The import is idempotent: existing stations are updated rather than duplicated.

On the supplied assessment dataset, preprocessing produced:

```text
Source rows:                 8151
Exact duplicates removed:      26
Unsupported region rows:      620
Canonical stations:          6626
Address geocoded:             526
City-centroid fallback:      5449
Unresolved:                   651
```

Stations that remain unresolved are excluded from runtime route matching.

## Run the API

```bash
python manage.py runserver
```

Endpoint:

```http
POST /api/v1/trips/optimize/
Content-Type: application/json
```

Request:

```json
{
  "start": "Chicago, IL",
  "finish": "Miami, FL"
}
```

Example curl:

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/v1/trips/optimize/ \
  -H "Content-Type: application/json" \
  -d '{"start":"Chicago, IL","finish":"Miami, FL"}' | jq
```

## Response shape

The response contains:

- resolved start and finish locations,
- route distance, duration, and GeoJSON `LineString`,
- fixed vehicle assumptions,
- purchased fuel stops only,
- gallons purchased and cost at each stop,
- total gallons purchased,
- total purchased-fuel cost,
- ending fuel,
- assumptions explaining the initial tank and route-corridor approximation.

Example excerpt:

```json
{
  "route": {
    "distance_miles": 1387.95,
    "duration_minutes": 1420.16,
    "geometry": {
      "type": "LineString",
      "coordinates": []
    }
  },
  "vehicle": {
    "max_range_miles": 500,
    "fuel_efficiency_mpg": 10,
    "tank_capacity_gallons": 50
  },
  "fuel_plan": {
    "starting_fuel_gallons": 50,
    "starting_fuel_cost_usd": null,
    "starting_fuel_cost_included": false,
    "stops": [],
    "total_gallons_purchased": 88.8,
    "total_fuel_cost_usd": 252.46,
    "ending_fuel_gallons": 0.0
  }
}
```

The actual `stops` array contains each selected station's OPIS ID, name, coordinates, price, mile-along-route, off-route distance, fuel state, purchase amount, cost, and geocode precision.

## Route-station matching

Fuel stations are pre-geocoded and stored locally. During a trip request:

1. unresolved stations are excluded,
2. the route geometry is processed once,
3. cumulative route mileage is precomputed,
4. a global route bounding box removes obviously distant stations,
5. route segments are grouped into small spatial chunks,
6. only relevant chunks are examined precisely,
7. stations within 10 miles are kept and sorted by `mile_along_route`.

Precise distances use geographic/Haversine-aware calculations rather than treating latitude/longitude degrees as miles.

A Chicago -> Miami development smoke test used a 9,188-point route and 5,975 geocoded stations. Matching examined about 60k exact segment comparisons and completed in roughly 0.1 seconds on the development machine; the external geocoding/routing calls dominated request time.

## Fuel optimization

The optimizer is a pure domain service with no HTTP or database dependency.

At a fueling point:

- if a cheaper reachable station exists ahead, buy only enough fuel to reach it;
- otherwise, take advantage of the current price by carrying more fuel, bounded by tank capacity and destination need;
- if destination is reachable, do not buy unnecessary fuel;
- if no station/destination can be reached within the 500-mile range, the optimizer raises `NO_FEASIBLE_FUEL_PLAN`.

Money is accumulated using `Decimal`; USD values are rounded only at the API presentation boundary.

## Error responses

Errors use a consistent structure:

```json
{
  "error": {
    "code": "LOCATION_NOT_FOUND",
    "message": "Start location could not be resolved."
  }
}
```

Important codes include:

| HTTP | Code |
|---|---|
| 400 | `INVALID_REQUEST` |
| 422 | `LOCATION_NOT_FOUND` |
| 422 | `UNSUPPORTED_REGION` |
| 422 | `ROUTE_NOT_FOUND` |
| 422 | `NO_FEASIBLE_FUEL_PLAN` |
| 503 | `STATION_DATA_UNAVAILABLE` |
| 502 | `ROUTING_PROVIDER_ERROR` |
| 504 | `ROUTING_PROVIDER_TIMEOUT` |

## Tests

```bash
pytest
```

The automated suite mocks external services and requires no real HTTP calls. It covers request validation, provider behavior, station canonicalization/geocoding, route geometry and corridor matching, optimizer invariants, error mapping, and final API orchestration.

## Useful smoke test

To inspect route matching separately from the final API:

```bash
python manage.py smoke_test_matcher \
  --start "Chicago, IL" \
  --finish "Miami, FL" \
  --corridor 10
```

It reports route size, station counts, segment-comparison count, matching time, and the first few route candidates.

## Trade-offs / limitations

- Census city-centroid fallback improves coverage but is approximate; precision is preserved in the data and API.
- `off_route_miles` is not a road-network detour distance. Computing exact detours for every station would require many extra routing calls and violate the assessment's routing-call constraint.
- The route corridor is fixed internally at 10 miles for this assessment.
- The initial tank's purchase cost is excluded because the problem provides no source price for it.
- The project intentionally avoids Redis, Celery, PostGIS, and per-station routing calls because the dataset size does not justify that infrastructure for this task.
