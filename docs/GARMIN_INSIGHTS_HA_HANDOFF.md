# Garmin Insights — Home Assistant handoff

**Status:** V1 runtime handoff  
**Branch:** `feature/garmin-insights-v1`  
**Scope:** current snapshot orchestration + one native overview sensor

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

The state is the strongest active severity:

```text
clear | positive | info | caution | warning
```

Before a snapshot can be built the state may instead be:

```text
unconfigured | waiting_for_fitness
```

Attributes include:

- Rules V1 results in deterministic priority order
- primary rule ID / severity / confidence
- ruleset version
- snapshot timestamp/date
- explicit data-quality metadata
- normalized recovery snapshot
- canonical Training V4 snapshot
- Load Focus snapshot
- compact seven-day activity context without location data

The rule result payload keeps stable `title_key` / `message_key` values from
ha-garmin. User-facing Swedish/English prose is intentionally deferred until live
validation has shown that the V1 thresholds and result combinations behave well.

## Fitness handoff cache

`FitnessCoordinator` exposes two read-only runtime properties:

```python
fitness.insight_context
fitness.insight_personal_trimp_max
```

They are updated only after a canonical Fitness context has been fetched and its
Strain calibration has been resolved. No Fitness formula or entity contract is
changed.

## Live-validation checklist

Before locking Rules V1 thresholds, inspect the overview sensor on real Garmin
data and verify:

1. current date and recovery source availability
2. Training Readiness / sleep / HRV values against Garmin Connect
3. current Training V4 metrics against the existing Fitness sensors
4. recent Training Effect coverage
5. emitted rule IDs, severity, confidence and evidence
6. missing/stale-data behavior on incomplete Garmin days

Only after this validation should thresholds or user-facing prose be treated as
stable.

## Scope guard

This handoff changes no:

- Fitness formula
- Fitness entity ID
- Garmin Gear identity/category logic
- Garmin authentication/session behavior
- Lovelace card

The next stage is live account validation, followed by threshold tuning if the
observed V1 results justify it.
