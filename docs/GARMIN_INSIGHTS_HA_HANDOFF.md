# Garmin Insights — Home Assistant handoff

**Status:** V1 runtime + presentation merged into `feature/garmin-fitness`  
**Updated:** 2026-09-14  
**Scope:** exact-date snapshot orchestration, one overview sensor, localized presentation, and Daily Load Budget handoff

The old `feature/garmin-insights-v1` implementation branch has been merged and
removed. `feature/garmin-fitness` is the active integrated line.

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
  ├─ Daily Load Budget V1
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

## Daily Load Budget V1

Insights also calculates the current advisory Daily Load Budget from the same
canonical Fitness context. The HA budget sensor exposes remaining recommended
TRIMP plus transparent structural/recovery attributes.

Budget V1 uses the most conservative simulated structural ceiling across:

```text
ACWR
Strain
TSB
Ramp Rate
```

The normal ACWR hard limit is `1.30`. If today's zero/additional-load state is
already beyond that limit, V1 can legitimately return zero remaining capacity.
Live observation has shown that this can remain overly binary when ACWR is high
because the chronic baseline is still low while TSB, Ramp, and Strain have
otherwise normalized.

That finding is being handled as a **budget-policy** question. The canonical
Fitness formulas remain unchanged.

## V2 re-entry preview

An isolated policy experiment exists in `ha-garmin` on
`experiment/daily-budget-v2-preview`. It is not wired into HA.

The preview considers a small re-entry budget only when V1 is blocked solely by
already-high ACWR and the other current signals are calm:

- TSB >= 0
- Ramp <= 0
- no `recovery_caution`
- no `insufficient_or_stale_data`

It then applies a light Strain ceiling (`4.0`), the existing TSB/Ramp constraints,
and a projected-ACWR guard of at most +5% from the already-high current value.

V1 remains authoritative until the preview has enough live validation and is
explicitly promoted through the library and HA dependency pin.

## Fitness handoff cache

`FitnessCoordinator` exposes two read-only runtime properties:

```python
fitness.insight_context
fitness.insight_personal_trimp_max
```

They are updated only after a canonical Fitness context has been fetched and its
Strain calibration resolved. No Fitness formula or entity contract is changed.

## Scope guard

Insights V1 / Budget V1 changes do not redefine:

- TRIMP / CTL / ATL / TSB / ACWR formulas
- existing Fitness entity IDs
- Garmin authentication/session behavior
- Garmin Gear identity/category policy

The current validation focus is natural rule combinations, explicit data-quality
presentation, and the separate Daily Load Budget V2 policy experiment.
