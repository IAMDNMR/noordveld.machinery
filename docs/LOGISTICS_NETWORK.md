# Logistics network, routes and shipment context (Phase 2)

Built on the canonical layer ([CANONICAL_DATA_MODEL.md](CANONICAL_DATA_MODEL.md)): the same models, engine, validation, provenance, deterministic ids, idempotency and integrity checks. No UI and no agent yet; the graph can now answer **"where is my shipment?"** and **"what are the realistic transport options and trade-offs?"** from records.

Everything added is synthetic demonstration data (`data_status = source_type = SYNTHETIC_DEMO`). It is not a real carrier schedule, rate or commitment.

## 1. Geography
A Netherlands-centred network: the Netherlands distribution centre (`WH-005`), Rotterdam seaport, Amsterdam air cargo terminal, then Western Europe (UK, Switzerland, Norway), the USA (Houston, Savannah, Chicago, Los Angeles) and Africa (Lagos, Tema, Durban, Mombasa, Casablanca). **Japan is an origin for one demonstration lane only** (a supplier near Nagoya, its seaport and airport): every other route starts at the Netherlands distribution centre.

Location model (`Location`): `location_id`, `name`, `location_type` (WAREHOUSE, DISTRIBUTION_CENTER, DEALER, PORT, AIRPORT, TERMINAL, CUSTOMS, SUPPLIER, PLANT), `country`, `region` (EUROPE, USA, AFRICA, ASIA), `latitude`, `longitude`, `timezone`, `data_status`, `source_type`. Existing depots, plants, dealers and the 48 terminals already in the graph were enriched in place; 29 locations and 12 dealers were added. A dealer is its own place (`location_id` = `dealer_id`). Nothing was duplicated.

Authoring source: `backend/data/canonical/reference/network_definition.json` (the one place the network is written down). `python backend/scripts/canonical.py network` checks it is coherent (legs contiguous, ends match the lane, days and cost are the sum of the legs, event sequences possible) and expands it into the `network_*` datasets.

## 2. Routes and legs
A `Route` carries `origin_location_id`, `destination_location_id`, `transport_mode`, `planned_transit_days`, `estimated_cost`, `currency`, `service_level`, `status`. Its `RouteLeg`s run in order from the origin to the destination, each with mode, days and cost; a route's days and cost are the **sums of its legs**. 27 routes and 90 legs on 13 lanes. **No mode has a built-in duration or price anywhere in code**: a test fails if one appears.

Same-lane sea vs air (the mandatory pair): supplier `SUP-041` → dealer `DLR-004`:

| Route | Mode | Service | Days | Cost (EUR, synthetic) |
|---|---|---|---|---|
| `RTE-NET-JPNL-SEA-ECO` | SEA | ECONOMY | 91 | 2,835 |
| `RTE-NET-JPNL-SEA-STD` | SEA | STANDARD | 45 | 3,785 |
| `RTE-NET-JPNL-AIR-EXP` | AIR | EXPRESS | 6 | 12,675 |

The 91 days exist on that one route record only (an economy consolidated service with transhipment and port waits). Every other NL-origin lane has a sea (or short-sea, or road) route and an air route with different days and cost.

## 3. Shipments and tracking
Tracking is a list of discrete events with an allowed order (`app/logistics/rules.py`): ORDER_CONFIRMED → BOOKED → DEPARTED_ORIGIN → (IN_TRANSIT) → ARRIVED_PORT → CUSTOMS → DEPARTED_PORT → ARRIVED_DC → OUT_FOR_DELIVERY → DELIVERED, with the seeded shipments' shorter PICKED lifecycle also valid. The engine rejects a shipment whose events are impossible together. **There is no live position**: an event at sea or in flight has no place, only a status, and the context says so.

Scenario shipments (fully linked to order, part, route and places):
* `SHP-NET-0001` A: Japan → sea → Rotterdam → Netherlands DC → dealer. IN_TRANSIT, on leg 2 of 4, planned ETA 2026-11-19.
* `SHP-NET-0002` B: the air alternative for the same order, part and lane. Out for delivery, ETA 2026-10-07.
* `SHP-NET-0003` C: Netherlands DC → Houston port → Houston regional logistics hub → US dealer. Left the port towards the hub, ETA 2026-10-09.
* `SHP-NET-0004` D: a delivered air shipment to a UK dealer (the full lifecycle including DELIVERED).

The 11 seeded shipments have no deterministic route (their depot has no recorded route to the customer's ship-to). They are **not linked**: `route_resolution_status = ROUTE_NOT_DETERMINABLE`, `route_id` null, with remediation flags.

## 4. Route progress
A leg is completed when the shipment has an arrival event (ARRIVED_PORT, ARRIVED_DC, DELIVERED) at the leg's destination. From that: completed legs, remaining legs, the current leg, and whether the shipment is on a leg or at a place. Legs complete in order. No GPS.

## 5. ShipmentContext
`app/logistics/context.py` assembles, from data only (no language model): shipment, order, part, origin, destination, current location, current status, events, route, legs, route progress, planned ETA (with days to ETA), alternative routes for the same origin and destination, a transport comparison, provenance and plain notes. The comparison is arithmetic on each route's own days and cost (difference to the current route, fastest, lowest cost); it never depends on the mode. A shipment without a route says so and has no progress or alternatives.

Two readers feed it with identical vocabulary: `FileReader` (the canonical files) and `GraphReader` (Neo4j, read-only). A test builds the context for six shipments from both and requires the same answer.

## 6. Migration of code values to data
| Was | Now | Status |
|---|---|---|
| `FILM_MACHINE`, `FILM_PART`, `FILM_CUSTOMER` in `services/site.py` | the `FeaturedScenario` FILM record in the graph (`scenarios/discovery.json`), read by the launch-film query | **migrated, constants removed** |
| `CITY_COORDINATES` in `core/geography.py` | graph locations (map positions) and `reference/geography.json` (the exporter's reference) | **migrated, constant removed** |
| hard-coded route durations, transport costs | none existed in code; all values are route records | n/a |
| shipment states (`order_flow.py` SHIPMENT_EFFECT, ACTIONS) | workflow rules for the direct-order flow | kept: rules, not business data |
| hard-coded dealer geography | none; dealers carry country, region and coordinates in the graph | n/a |

Effect of the coordinate migration: plant and depot map pins moved by under 0.01° (the graph's synthetic depot coordinates have two decimals, the old table four), and every city that had no position now has one.

## 7. Commands
```
python backend/scripts/canonical.py network     # validate and expand the network definition
python backend/scripts/canonical.py export      # existing data -> canonical files (enriched)
python backend/scripts/canonical.py dry-run | ingest --yes | verify | checksum
```

## 8. Limits
* All numbers are synthetic and illustrative. There is no carrier integration and no live position.
* Scenario shipments belong to three synthetic orders (channel `DEMO_NETWORK`); processors see them in the orders list, end users do not.
* A shipment uses one route; multi-route or re-routed shipments are not modelled.
* The 11 seeded shipments stay unresolved until a deterministic link exists.
* `CUSTOMS` as a location type exists in the model; customs are events at ports and terminals, not separate places.
