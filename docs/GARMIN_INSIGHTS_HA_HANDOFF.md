# Garmin Insights — Home Assistant handoff

**Status:** active beta runtime in `2026.10.0b2`  
**Updated:** 2026-10-07  
**Scope:** exact-date snapshot orchestration, one overview sensor, localized presentation, and priority-aware Daily Load Budget handoff

Canonical development now follows `dev → beta → main`. Historical Insights
feature branches are not release lines.

## Runtime flow

```text
Garmin API
  ↓
ha-garmin strict exact-date recovery history
  ↓
FitnessCoordinator cached canonical TrimpTrainingContext
  ↓
ha-garmin build_insight_snapshot()
  ↓
ha-garmin evaluate_insights()
  ↓
InsightsCoordinator
  ├─ priority-aware Daily Load Budget (planning policy v2)
  ↓
HA presentation adapter
  ↓
sensor.garmin_insights_overview + Garmin Daily Load Budget sensor
```

Home Assistant does not recalculate TRIMP, CTL, ATL, TSB, ACWR, Ramp Rate,
Strain, Load Focus, or Insights rule logic. The Fitness coordinator keeps the
exact canonical `TrimpTrainingContext` and paired personal TRIMP calibration in
memory so Insights and the budget policy reuse the same Fitness inputs without a
second 180-day Garmin history fetch.

## Recovery semantics

Insights fetches the requested current HA-local calendar day through
`GarminHistoryClient.fetch_daily_recovery_metrics()`. This is the strict history
path: adjacent-day presentation fallbacks are not allowed.

Garmin can expose exact-date Morning / `AFTER_WAKEUP_RESET` Training Readiness
without a regular Training Readiness record. The normalized model keeps both
sources separate. Snapshot completeness accepts either exact-date readiness
source, and Rules V1 prefers regular readiness but falls back to Morning
Readiness with explicit evidence provenance.

The Insights coordinator refreshes hourly. A successful Fitness update also
schedules an Insights refresh so a newly recorded activity can affect the current
snapshot without waiting for the next independent Insights interval.

## Data-quality contract

A recovery `*_available` flag means the exact-date Garmin source responded. It
does **not** mean every desired field in that response is populated.

Snapshot completeness currently requires:

- current-date recovery data
- Garmin summary source
- sleep source
- HRV source
- either regular or Morning Training Readiness source
- `recovery.resting_hr`
- `recovery.hrv_last_night_avg`
- `recovery.sleep_score`
- either `recovery.training_readiness` or
  `recovery.morning_training_readiness`
- complete canonical Training fields
- complete Load Focus fields

The authoritative explanation for an incomplete snapshot is:

```text
data_quality.missing_sources
data_quality.missing_fields
data_quality.stale_fields
```

This means an exact-date sleep endpoint can be available while `sleep_score` is
still `None`, for example when Garmin Connect itself has not produced the night's
sleep record. That is a source-data gap, not automatically an integration error.

A planned UI polish item is to show the concrete `missing_fields` labels (for
example Nightly HRV or Sleep Score) instead of only a generic incomplete-data
message. This is not implemented yet.

## Overview sensor

The integration exposes one stable Insights entity contract with unique ID:

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
- canonical Training snapshot
- Load Focus snapshot
- compact seven-day activity context without location data
- presentation language (`sv` or `en`)
- localized status label/icon
- localized primary title/message/icon
- localized `presented_results` with human-readable evidence labels
- current `daily_load_budget` payload

The raw result payload is preserved unchanged. The HA presentation adapter maps
stable IDs/codes to Swedish or English labels/messages but does not change rule
priority, severity, confidence, thresholds, or conflicts.

## Daily Load Budget — current runtime

The structural budget still evaluates ACWR, Strain, TSB and Ramp Rate from the
canonical Fitness context.

Home Assistant then applies priority-aware planning policy v2. Load Priority
selects a source per activity for intensity classification; clearly low-intensity
activity can be excluded from today's **planning** consumption while its actual
Banister TRIMP remains in canonical Training history.

The budget sensor therefore distinguishes:

```text
canonical_current_load
budget_consuming_load
excluded_low_intensity_load
```

and exposes transparent per-activity `activity_decisions`.

The canonical series remains TRIMP. Power TSS, Garmin Load and pace proxy are
not summed into the Training history.

The ACWR hard ceiling can still be the limiting factor. A zero remaining budget
means zero additional **modelled training budget**, not a prohibition on normal
movement.

## Fitness handoff cache

`FitnessCoordinator` exposes two read-only runtime properties:

```python
fitness.insight_context
fitness.insight_personal_trimp_max
```

They are updated only after a canonical Fitness context has been fetched and its
Strain calibration resolved. No Fitness formula or entity contract is changed.

## Scope guard

Insights V1 / planning-budget changes do not redefine:

- TRIMP / CTL / ATL / TSB / ACWR formulas
- existing Fitness entity IDs
- Garmin authentication/session behavior
- Garmin Gear identity/category policy

The current validation focus is natural rule combinations, explicit data-quality
presentation, priority-aware budget behavior, and real Home Assistant regression
testing through the normal `dev → beta → main` release path.
