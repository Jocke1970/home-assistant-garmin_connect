# Garmin Fitness handoff status

> Status: Training runtime boundary finalized on `feature/garmin-fitness-handoff`.

## Source of truth

Garmin Fitness calculations live in `ha-garmin`.

`home-assistant-garmin_connect` owns Home Assistant orchestration only:

- config/options
- coordinator lifecycle
- current-state sensors
- Recorder / long-term-statistics import
- warm-up recovery policy
- presentation provenance

The Home Assistant coordinator must not maintain independent implementations of
TRIMP, CTL, ATL, TSB, ACWR, ramp rate, strain, or Training Effect load-focus
math.

## Runtime boundary

The permanent runtime uses the existing authenticated `GarminClient` through:

```python
GarminHistoryClient(client).fetch_trimp_training_context(...)
```

The returned context contains:

- normalized activities
- strict resting-HR history
- canonical TRIMP training history

This lets the HA adapter reuse the same fetched input for strain calibration and
load-focus presentation without a second Garmin login or a duplicate 180-day
activity fetch.

## Training v1 behavior

- canonical load source: TRIMP
- calculation window: 180 days
- visible / persisted history window: final 90 days
- CTL: 42-day EMA
- ATL: 7-day EMA
- TSB: CTL - ATL
- ACWR: 7 / 28 days
- ramp rate: CTL today - CTL 7 days ago
- strain: bounded 0-21 presentation metric from canonical TRIMP
- load focus: transparent Garmin Training Effect heuristic
  - aerobic TE < 3.0 -> low aerobic
  - aerobic TE >= 3.0 -> high aerobic
  - anaerobic TE -> anaerobic bucket

Missing source data remains explicit. Rest days are real zero-load days; an
activity day with incomplete canonical inputs is not silently converted to zero.

## Warm-up recovery

A blocker inside the visible 90-day window blocks the canonical series.

An older blocker may be bypassed only when restarting after the blocker still
leaves the configured minimum complete warm-up period before the visible window.
This keeps the EMA seed influence bounded instead of treating missing load as
zero.

## Home Assistant persistence

Current-state Fitness sensors retain stable unique IDs. Completed historical
calendar days are imported to Recorder long-term statistics using the actual
registered sensor entity IDs. The current day remains owned by the live sensor.

The current implementation stores the daily imported statistic sample at 23:00
local time. This document records the implementation as source of truth; older
design notes mentioning UTC midnight are superseded.

## Diagnostic probe

`fitness_probe.py` and the `garmin_connect.fitness_probe` service remain useful
as read-only diagnostics. They are no longer the calculation boundary for the
permanent Fitness coordinator.

## Dependency during development

The integration temporarily pins an exact commit from the dedicated `ha-garmin`
Fitness handoff branch. Replace that git SHA with a released package version once
the library changes are published.

## Scope guard

This handoff does not modify Garmin Gear behavior or the separate activity
`deviceId` preservation work.

## Next Fitness milestone

With the Training runtime boundary frozen, the next independent Garmin Fitness
milestone is the deterministic Insights layer. Insights should consume the
stable derived metrics rather than introduce another training-load calculation
path.
