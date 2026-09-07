# Garmin Insights — Home Assistant handoff

**Status:** V1 runtime + presentation handoff  
**Branch:** `feature/garmin-insights-v1`  
**Scope:** current snapshot orchestration + one native overview sensor + localized presentation attributes

## Runtime flow

```text
Garmin API
  ↓
ha-garmin strict recovery history
  ↓
FitnessCoordinator cached canonical TrimpTrainingContext
  ↓
ha-garmin build_insight_snapshot()
  ↓
ha-garmin evaluate_insights()
  ↓
InsightsCoordinator
  ↓
HA presentation adapter
  ↓
sensor.garmin_insights_overview
```

Home Assistant does not recalculate TRIMP, CTL, ATL, TSB, ACWR, Ramp Rate,
Strain or Load Focus. The existing Fitness coordinator keeps the exact canonical
`TrimpTrainingContext` and paired personal TRIMP calibration in memory so Insights
can reuse the same Fitness inputs without a second 180-day Garmin history fetch.

## Recovery semantics

Insights fetches the requested current HA-local calendar day through
`GarminHistoryClient.fetch_daily_recovery_metrics()`. This is the strict history
path: adjacent-day presentation fallbacks are not allowed.

Garmin can expose exact-date morning / `AFTER_WAKEUP_RESET` Training Readiness
without also exposing a regular Training Readiness record. The normalized model
keeps both sources separate. Snapshot completeness accepts either exact-date
readiness source, and Rules V1 prefers regular readiness but falls back to morning
readiness with explicit evidence provenance.

The Insights coordinator refreshes hourly. A successful Fitness update also
schedules an Insights refresh so a newly recorded activity can affect the current
snapshot without waiting for the next independent Insights interval.

## Overview sensor

The integration exposes one stable entity:

```text
sensor.garmin_insights_overview
```

The exact generated entity ID may retain an existing registry name, but the
unique ID contract is:

```text
<config_entry_id>_insights_overview
```

The state remains a stable machine-readable severity:

```text
clear | positive | info | caution | warning
```

Before a snapshot can be built the state may instead be:

```text
unconfigured | waiting_for_fitness
```

Attributes include:

- Rules V1 raw results in deterministic priority order
- primary rule ID / severity / confidence
- ruleset version
- snapshot timestamp/date
- explicit data-quality metadata
- normalized recovery snapshot
- canonical Training V4 snapshot
- Load Focus snapshot
- compact seven-day activity context without location data
- presentation language (`sv` or `en`)
- localized status label/icon
- localized primary title/message/icon
- localized `presented_results` with human-readable evidence labels

The raw result payload is preserved unchanged, including stable `title_key`,
`message_key`, evidence codes and provenance from ha-garmin. The HA presentation
adapter only maps those stable IDs/codes to Swedish or English labels and messages;
it does not change rule priority, severity, confidence, thresholds or conflicts.

Swedish is selected when Home Assistant's configured language starts with `sv`;
all other languages currently fall back to English.

## Fitness handoff cache

`FitnessCoordinator` exposes two read-only runtime properties:

```python
fitness.insight_context
fitness.insight_personal_trimp_max
```

They are updated only after a canonical Fitness context has been fetched and its
Strain calibration has been resolved. No Fitness formula or entity contract is
changed.

## Live-validation status

The first live account validation exposed one real Garmin shape: regular Training
Readiness was absent while exact-date Morning Training Readiness was available.
That provenance case is now covered in the library, HA handoff and tests.

The live snapshot subsequently validated as complete and emitted both
`low_recent_load` and `favourable_training_signal` with explicit morning-readiness
evidence.

Continue validating future natural account states before treating all V1
thresholds and message wording as final.

## Scope guard

This handoff changes no:

- Fitness formula
- Fitness entity ID
- Garmin Gear identity/category logic
- Garmin authentication/session behavior
- Lovelace card

The next stage after presentation validation is the Lovelace card / UI layer and
continued observation of natural rule combinations on real Garmin data.
