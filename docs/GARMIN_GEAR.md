# Garmin Gear metadata pipeline

This document describes the Gear metadata flow used by the Garmin Connect Home Assistant integration and the `ha-garmin` client.

The goal is to enrich Garmin Gear with useful, current metadata without polling every gear item separately.

## Scope

The Gear flow covers:

- Garmin Gear inventory and usage statistics
- default activity types for each gear item
- dynamic Garmin activity type metadata (`typeId`, `typeKey`, `parentTypeId`)
- the latest recent activity associated with each gear item
- Home Assistant sensor attributes used by downstream templates and Lovelace cards

It does **not** add a second Garmin login or a separate Gear polling service. Gear enrichment reuses the existing Garmin Connect session and the normal Activity/Gear coordinators.

## Data flow

```text
Garmin Connect
    |
    | normal recent activity fetch
    v
ha-garmin Activity flow
    |- learns activity type metadata from activityType
    |- keeps the current recent-activity window
    |- looks up gear attached to activities in that window
    `- caches activity -> gear results
    |
    v
ha-garmin Gear flow
    |- fetches gear/stats/defaults
    |- resolves numeric default activity IDs through the registry
    `- attaches cached latest activity metadata per gear UUID
    |
    v
Home Assistant Gear sensors
    |- default_for_activity
    |- default_for_activity_details
    `- last_activity
    |
    v
Templates / Lovelace
```

## Activity Type Registry

Garmin Gear defaults can expose numeric activity IDs such as `25`, `32` or `152`. Showing these as `type_25`, `type_32`, etc. is not useful in the UI.

`ha-garmin` therefore maintains a dynamic Activity Type Registry.

Each entry contains only the stable fields needed downstream:

```yaml
25:
  typeId: 25
  typeKey: indoor_cycling
  parentTypeId: 2
```

The registry is populated in two ways:

1. **Free learning from normal activity data.** Recent Garmin activities already contain `activityType`, so the client learns `typeId`, `typeKey` and `parentTypeId` without an additional request.
2. **Lazy Garmin hierarchy bootstrap.** When Gear data is fetched, the canonical Garmin activity type hierarchy is loaded as a best-effort auxiliary request. It is cached for 24 hours so old/default activity types can still be resolved even if they have not appeared in recent activities.

A transient empty/error response from the auxiliary activity-type endpoint does not erase a previously good registry and does not fail the primary Activity or Gear coordinator.

### Gear default output

The raw numeric/default representation is converted into two downstream fields:

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

`default_for_activity` is convenient for simple consumers. `default_for_activity_details` preserves the Garmin hierarchy for richer UI behaviour such as labels, parent-family fallback and icons.

## Latest activity per Gear

The latest Gear activity is derived from the **Activity flow**, not by polling each Gear item.

For every activity in the currently fetched recent-activity window, `ha-garmin` asks Garmin which Gear items are associated with that activity. The scan runs newest to oldest, so the first/newest matching activity becomes the latest activity for that Gear UUID.

The compact stored payload is:

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

### Why the Activity flow owns this

A Gear item's "latest use" changes when an activity is uploaded or edited. The Activity coordinator is therefore the natural trigger.

This avoids a design where every Gear item performs its own historical lookup on every refresh.

## Cache and request behaviour

The implementation is deliberately conservative with Garmin API calls.

- Activity-to-Gear lookup results are cached by `activity_id`.
- After the recent window has been primed, normal operation is approximately one additional Gear lookup when a **new activity** appears, not one lookup per Gear item per poll.
- The newest activity is allowed up to **3 empty-result retries** because Garmin can expose the activity before its Gear association has propagated.
- Older historical activities with an empty Gear result are treated as stable after the first lookup.
- The per-activity cache is bounded to the same rolling recent-activity window being scanned.
- A failed auxiliary Gear lookup does not make the Activity coordinator unavailable.

## Recent-window backfill

At startup/reload, the current implementation scans the recent Garmin activity window from newest to oldest and fills `last_activity` for Gear items found in that window.

The current Activity fetch uses a **10-activity recent window**. This is intentionally a bounded bootstrap rather than an unbounded history scan.

Consequences:

- Gear used in one of the recent activities can receive an immediate historical `last_activity` after restart.
- Gear whose last use is older than the current recent window will remain without `last_activity` until it is used again, unless a future controlled historical backfill is added.
- This is not the same as "the Gear has never been used"; consumers should distinguish missing recent linkage from zero total activities.

## Home Assistant Gear attributes

Each dynamic Gear sensor exposes the existing Garmin metadata plus the enriched fields:

```yaml
gear_uuid: ...
total_activities: 320
gear_make_name: ...
gear_model_name: ...
gear_status_name: active
custom_make_model: ...
maximum_meters: 500000
default_for_activity:
  - indoor_rowing
default_for_activity_details:
  - typeId: 32
    typeKey: indoor_rowing
    parentTypeId: 29
last_activity:
  activity_id: 123456789
  name: Rodd
  type: indoor_rowing
  type_id: 32
  parent_type_id: 29
  start: "2026-09-03T17:41:00+00:00"
  distance_m: 700.0
  duration_s: 300.0
```

`last_activity` is omitted/`None` when no matching activity has been found in the current cache/window.

## Frontend contract

Presentation should be based on stable semantic fields, not Garmin's numeric IDs.

Recommended order:

1. Use `typeKey` for activity identity and translation.
2. Use an exact MDI icon mapping where a good match exists.
3. Fall back through `parentTypeId` to the broader activity family.
4. Use a neutral fallback for unknown future Garmin types.

The UI should never need to display raw strings such as `type_25` when `default_for_activity_details` is available.

For `last_activity`, a Gear item with historical usage but no cached recent activity should be presented as something like **"Latest activity not available"**, not **"No activity registered"**.

## Current implementation references

`ha-garmin`:

- `src/ha_garmin/activity_types.py`
- `tests/test_activity_types.py`

Home Assistant integration:

- `custom_components/garmin_connect/coordinator.py`
- `custom_components/garmin_connect/sensor.py`

Release line used while this work is being validated:

- `ha-garmin` 0.1.38 code line
- Garmin Connect `3.0.18-fitness-probe.8`

## Design decisions

The following decisions are intentional:

- Activity types are learned dynamically instead of maintaining a static Garmin numeric-ID table.
- Swedish/localised labels and MDI icons belong to presentation, not the Garmin API client.
- Latest Gear use is activity-driven instead of Gear-polled.
- Auxiliary enrichment failures must not break primary Garmin data.
- Bootstrap/backfill is bounded; API friendliness is preferred over exhaustive historical scanning.
