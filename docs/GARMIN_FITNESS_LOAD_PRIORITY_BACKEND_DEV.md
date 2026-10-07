# Garmin Fitness — Load Priority backend

> Status: beta-validated in Garmin Connect `2026.10.0b2`  
> Updated: 2026-10-07  
> Planning policy: `planning_mode: load_priority`, `planning_policy_version: 2`

The filename retains its historical `_DEV` suffix, but the behavior described
here is no longer dev-only.

## Production behavior

The normal Insights refresh calls `build_priority_aware_daily_budget` and
exposes the result on the Garmin Daily Load Budget sensor.

Canonical Fitness history is **not** modified. Actual CTL/ATL/TSB/ACWR/Strain
continue to use the homogeneous Banister TRIMP series.

For today's synthetic planning day, Load Priority selects one source per
activity for intensity classification. Clearly low-intensity activities can be
excluded from finite budget consumption. Any excluded amount is calculated on
the canonical TRIMP scale before it is subtracted.

This prevents Power TSS, Garmin Load and pace proxy values from being summed or
relabeled as TRIMP.

Current fixed low-intensity thresholds:

- power IF <= 0.75
- heart-rate reserve <= 0.60
- pace ratio <= 0.80
- Garmin Training Effect <= 2.0

The base structural budget still applies ACWR, Strain, TSB and Ramp constraints.
Load Priority does not guarantee a non-zero budget.

## Sensor contract

Important attributes:

- `planning_mode`
- `planning_policy_version`
- `canonical_history_modified`
- `canonical_current_load`
- `budget_consuming_load`
- `excluded_low_intensity_load`
- `low_intensity_activity_count`
- `training_activity_count`
- `unknown_intensity_activity_count`
- `activity_decisions`
- `low_intensity_thresholds`

Per-activity decisions cover **today only**.

## Read-only diagnostic action

`garmin_connect.fitness_load_priority_preview` remains a separate diagnostic
action. It can compare source selection for cached activities without changing
the live budget or canonical history.

Example:

```yaml
sport: walking
limit: 10
```

Optional inputs include `sport`, `priority`, `override`, `ftp_watts`,
`threshold_speed_mps`, `limit`, and account `entity_id` when required.

The diagnostic may return different load units; those values must never be
summed.

## Verified behavior

Real Home Assistant checks confirmed:

- low-intensity walking can remain part of actual TRIMP while being excluded
  from budget consumption
- actual and budget ACWR can therefore differ by design
- TRIMP algorithm v2 corrected the canonical scale before budget classification
- `algorithm_version: 2` and `planning_policy_version: 2` coexist by design

## Release policy

All future changes follow:

```text
dev → beta → main
```

A policy change that affects persisted canonical Training history requires an
explicit Fitness algorithm-version decision. A presentation-only or planning
policy change does not silently rewrite Recorder history.
