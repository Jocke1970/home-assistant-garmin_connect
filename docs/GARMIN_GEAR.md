# Garmin Gear metadata pipeline

This document describes the current Garmin Gear architecture used by the Garmin Connect Home Assistant integration and the `ha-garmin` client.

The design goal is to keep Garmin source identities intact while presenting one useful physical item in Home Assistant when two source records are known to represent the same device.

## Current status

Live-verified on 2026-09-13/14:

- Home Assistant integration: `3.0.33-gear-links-v1`
- canonical HA development branch: `feature/garmin-fitness`
- frontend card: `0.3.0-dev.16`
- overview entity: `sensor.garmin_gear_overview_2`
- schema: `1.0`
- live snapshot after confirmed sensor linking:
  - 51 Garmin source records
  - 41 Garmin Gear records
  - 6 registered Garmin-device records
  - 4 recent ANT+/BLE sensor records
  - 47 backend physical items after confirmed Gear <-> sensor linking
  - 43 frontend physical cards after additional presentation-only grouping

The integration currently pins `ha-garmin` by exact Git commit. `ha-garmin` remains a separate runtime dependency and owns Garmin API access/normalization and shared Fitness/Insights logic; Home Assistant owns coordinators, entities, Gear presentation canonicalization and services.

## Scope

The Gear flow covers:

- Garmin Gear inventory and usage statistics
- default activity types for each Gear item
- dynamic Garmin activity type metadata (`typeId`, `typeKey`, `parentTypeId`)
- latest recent activity associated with Gear
- registered Garmin devices
- recently seen ANT+/BLE sensors and battery metadata
- a canonical Gear overview for downstream Lovelace presentation
- shared product-picture storage for Garmin Gear and other cards

It does **not** add a second Garmin login or a separate Gear polling service. Gear enrichment reuses the existing Garmin Connect session and the normal Activity/Gear coordinators.

## Source model

Garmin exposes several identity domains that can describe the same physical device:

```text
Garmin Gear registry     -> source = garmin_gear
Registered Garmin device -> source = garmin_device
Recent ANT+/BLE sensor   -> source = garmin_sensor
```

These source records are intentionally kept separate in normalized data. A source record is not discarded just because Home Assistant later presents it together with another source.

Important rule: **never identify or merge a physical device from display name alone**.

Garmin's recent-sensor `deviceName` is not a trustworthy physical identity. Controlled testing showed that a sensor can be renamed/reported unexpectedly while its stable identity and sensor fingerprint remain unchanged. Source linking therefore uses stable IDs/fingerprints and explicit compatibility checks, not fuzzy name matching.

## Data flow

```text
Garmin Connect
    |
    | activities / gear / devices / sensors
    v
ha-garmin
    |- normalizes Gear records
    |- normalizes registered Garmin devices
    |- normalizes recent ANT+/BLE sensors
    |- learns activity type metadata
    |- keeps bounded recent activity -> Gear linkage
    `- preserves source identities
    |
    v
Home Assistant GearCoordinator
    |
    v
gear_engine.py
    |- validates GearSourceRecord objects
    |- classifies source records
    |- applies only explicitly confirmed physical sensor links
    |- preserves both original records under `sources`
    `- publishes canonical GearItem objects
    |
    v
sensor.garmin_gear_overview_2
    |
    v
Sportaffären / garmin-gear-card.js
    `- presentation-only grouping, filtering, images and details
```

## Confirmed physical sensor links

The backend currently contains explicit confirmed links for four physical devices. These links were established from controlled live tests and are intentionally narrow.

### Garmin Varia 511

Garmin's recent-sensors endpoint currently exposes the Varia source with an unexpected `sensorType: HEART_RATE`. The stable sensor identity plus controlled Varia-only activity testing confirmed that this source belongs to the Varia.

The physical item therefore combines:

```text
Garmin Gear: Garmin Varia 511
ANT+/BLE source: stable Varia sensor identity
Observed sensor metadata: HEART_RATE, 75 %, software 0.3
```

The incorrect Garmin sensor type is retained as raw source metadata; it is not rewritten to a fabricated type.

### Garmin Speed Sensor 2

Controlled testing confirmed the source fingerprint:

```text
sensor_type: BIKE_SPEED
manufacturer: GARMIN
product_id: 9
part_number: 9
software_version: 2.3
```

This source is linked to the Garmin Speed Sensor 2 Gear record.

### Morpheus M7

Controlled testing with the Morpheus worn during the activity identified the actual heart-rate source as:

```text
sensor_type: HEART_RATE
manufacturer: FITCARE
product_id: 5
software_version: 0.3
```

The live verification showed `100 % / NEW` battery metadata on the merged Morpheus M7 card.

### Bontrager Ion 200 RT Flare

The previously confirmed `BIKE_LIGHT_MAIN` sensor source remains linked to the Bontrager Ion 200 RT Flare Gear record.

### Stages Power L

Stages remains **Gear-only**. Garmin associates the Stages Gear item with cycling activities, but the recent-sensors endpoint did not expose a corresponding `POWER`/`BIKE_POWER` source during controlled tests.

Do not invent a Stages sensor link until Garmin exposes a source that can be identified confidently.

## Backend link semantics

Confirmed Gear <-> sensor links are implemented in `custom_components/garmin_connect/gear_engine.py`.

When a confirmed link matches:

- the canonical item uses the Gear record as the primary identity
- both original source records are retained in `sources`
- Gear lifecycle/status semantics win (`active`, usage/activity count)
- sensor `last_seen_at`, battery, sensor type and related metadata are carried onto the physical item
- `metadata.physical_link` is set to `confirmed`
- `metadata.linked_sensor_source_id` records the linked sensor source
- source counts remain source-based
- item count becomes physical-item based

There is an explicit regression test that two same-name records without a confirmed link remain separate.

## Frontend contract

The frontend should present the canonical backend data rather than reimplement sensor identity rules.

`0.3.0-dev.16` removed the older hard-coded Bontrager/Morpheus sensor-association block from JavaScript. This fixed the case where the Varia sensor source was incorrectly relabelled as Morpheus in the UI after the real sensor identities had been established.

The frontend may still perform conservative **presentation-only** grouping for other high-confidence physical relationships, for example a Garmin Gear record plus a registered Garmin device record representing the same Edge/Fenix hardware. Backend source traceability remains intact.

For activity presentation:

1. use `typeKey` for activity identity and translation
2. use exact icon mapping where available
3. fall back through `parentTypeId` to the broader activity family
4. use a neutral fallback for unknown future Garmin types

For `last_activity`, Gear with historical usage but no cached recent activity should be presented as **latest activity unavailable**, not as **never used**.

## Activity Type Registry

Garmin Gear defaults can expose numeric activity IDs such as `25`, `32` or `152`. `ha-garmin` maintains a dynamic Activity Type Registry so downstream UI does not have to display opaque values such as `type_25`.

Example:

```yaml
25:
  typeId: 25
  typeKey: indoor_cycling
  parentTypeId: 2
```

The registry is populated through normal recent activity data and a best-effort cached Garmin hierarchy bootstrap.

Gear output exposes both a convenient string list and hierarchy-preserving details:

```yaml
default_for_activity:
  - indoor_cycling
  - virtual_ride

default_for_activity_details:
  - typeId: 25
    typeKey: indoor_cycling
    parentTypeId: 2
  - typeId: 152
    typeKey: virtual_ride
    parentTypeId: 2
```

A transient auxiliary endpoint failure must not erase a previously good registry or fail the main coordinator.

## Latest activity per Gear

Latest Gear use is derived from the Activity flow rather than by polling every Gear item.

For activities in the bounded recent window, `ha-garmin` asks Garmin which Gear records are associated with each activity. The newest matching activity becomes the latest activity for that Gear UUID.

Compact payload:

```yaml
last_activity:
  activity_id: 123456789
  name: Stockholm Gång
  type: walking
  type_id: 9
  parent_type_id: 1
  start: "2026-08-13T18:19:00+00:00"
  distance_m: 2100.0
  duration_s: 1380.0
```

Only available values are included.

The recent activity window is intentionally bounded. Missing `last_activity` therefore means no recent linkage was found, not necessarily that the Gear has never been used.

## Cache and request behaviour

The implementation is conservative with Garmin API calls:

- activity-to-Gear lookup results are cached by `activity_id`
- after priming, normal operation is approximately one additional Gear lookup when a new activity appears, not one lookup per Gear item per poll
- the newest activity may be retried when Garmin exposes the activity before its Gear association has propagated
- older empty historical results are treated as stable
- caches are bounded to the recent window
- auxiliary lookup failure does not make the primary coordinator unavailable

## Shared card picture backend

The picture upload/storage implementation lives in `custom_components/garmin_connect/gear_picture.py` and is collection-based so multiple cards can reuse one validated storage implementation.

Reusable WebSocket commands:

```text
garmin_connect/card_picture/upload
garmin_connect/card_picture/remove
```

Canonical directories:

```text
garmin_gear        -> /config/www/garmin_gear_card/pictures/
device_maintenance -> /config/www/device_maintenance_card/pictures/
```

The retired `/config/www/gear_pictures/` path is no longer used.

Validation rules remain:

- JPEG, PNG and WebP only
- maximum 5 MB decoded image size
- image signature validation
- deterministic safe filename slugging
- atomic temporary-file replace
- stale-extension cleanup when a picture is replaced
- admin requirement on WebSocket commands

Product images were live-verified after the sensor-link update and can be assigned to the newly resolved physical devices.

## Current implementation references

`ha-garmin`:

- `src/ha_garmin/client.py`
- `src/ha_garmin/gear.py`
- `src/ha_garmin/activity_types.py`

Home Assistant integration:

- `custom_components/garmin_connect/coordinator.py`
- `custom_components/garmin_connect/gear_engine.py`
- `custom_components/garmin_connect/gear_sensor.py`
- `custom_components/garmin_connect/gear_picture.py`
- `tests/test_gear_engine.py`
- `tests/test_gear_picture.py`

Frontend:

- `Jocke1970/HA_Garaget`
- `homeassistant/www/garmin_gear_card/garmin-gear-card.js`

Current validation line:

- Home Assistant integration `3.0.33-gear-links-v1`
- frontend `0.3.0-dev.16`
- `ha-garmin` pinned by exact commit from the integration manifest

## Branch policy

For the Home Assistant integration, `feature/garmin-fitness` is the canonical development line. Short-lived `fix/*` and feature branches should be merged back and removed when complete. `feature/garmin-insights-audit` remains intentionally separate while audit work is active.

The Gear sensor-link fix must therefore land on `feature/garmin-fitness` before a test release is created. This policy was reinforced after an earlier Gear-link change was temporarily merged only into a side branch and was therefore absent from later Fitness releases.

## Next milestone: supervised sensor linking

The current explicit links are safe but do not scale well: each newly discovered physical relationship currently requires a code change and release.

The planned next Gear milestone is **supervised sensor linking**:

```text
new Garmin sensor source
        |
        v
unlinked sensor in UI
        |
        v
backend proposes likely Gear matches
        |
        v
user confirms the physical link
        |
        v
association is persisted locally in Home Assistant
        |
        v
future refreshes build one physical item without another code release
```

Expected matching evidence includes stable sensor identity, compatible sensor type/manufacturer/product metadata, and activity-time correlation. `deviceName` alone must never be sufficient.

The system should also support a standalone physical sensor when no matching Garmin Gear record exists, and allow a persisted link to be removed/replaced explicitly.

This is a planned milestone, not current functionality.

## Design decisions

The following decisions are intentional:

- preserve Garmin source identities even when presenting one physical item
- never auto-merge by display name alone
- explicit/confirmed identity evidence wins over mutable `deviceName`
- Gear semantics win lifecycle/activity state for Gear <-> sensor physical items
- Swedish/localized labels and icons belong to presentation, not the Garmin API client
- latest Gear use is activity-driven instead of Gear-polled
- auxiliary enrichment failures must not break primary Garmin data
- bounded bootstrap/backfill is preferred over exhaustive history polling
- card picture persistence is implemented once in `gear_picture.py`
- future unknown physical links should move toward supervised persisted linking rather than more hard-coded account-specific rules
