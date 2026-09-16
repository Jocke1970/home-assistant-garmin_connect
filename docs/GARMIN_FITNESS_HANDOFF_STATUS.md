# Garmin Fitness handoff status

> Status: active integrated runtime on `feature/garmin-fitness`  
> Updated: 2026-09-14  
> Current HA development build: `3.0.33-gear-links-v1`  
> Current `ha-garmin` pin: `c5c2d7e62bb7d9d311c11200ab325f435a2da5c9`

## Source of truth

Garmin Fitness calculations live in `ha-garmin`.

`home-assistant-garmin_connect` owns Home Assistant orchestration only:

- config/options
- coordinator lifecycle
- current-state sensors
- Recorder / long-term-statistics import
- warm-up recovery policy
- localized presentation/provenance
- Lovelace-facing entity contracts

The Home Assistant coordinator must not maintain independent implementations of
TRIMP, CTL, ATL, TSB, ACWR, ramp rate, strain, Load Focus, Activity Evaluation,
or Daily Load Budget policy math.

## Canonical Training runtime

The permanent runtime uses the existing authenticated `GarminClient` through
`GarminHistoryClient.fetch_trimp_training_context(...)`.

Canonical Training behavior is intentionally frozen while higher-level policy is
validated:

- canonical load source: TRIMP
- calculation window: 180 days
- visible / persisted history window: final 90 days
- CTL: 42-day EMA
- ATL: 7-day EMA
- TSB: CTL - ATL
- ACWR: 7 / 28 days
- ramp rate: CTL today - CTL 7 days ago
- strain: bounded 0-21 presentation metric from canonical TRIMP
- Load Focus: transparent Garmin Training Effect split

Missing source data remains explicit. A real rest day is zero load; an activity
day with incomplete canonical inputs is not silently converted to zero.

## Merged higher-level capabilities

### Insights V1

The deterministic Insights engine is merged and runs against the cached canonical
Fitness context. Recovery inputs are fetched for the exact current HA-local date.
Adjacent-day substitution is not used.

`sensor.garmin_insights_overview` exposes:

- stable result IDs / severity / confidence
- localized Swedish/English presentation
- raw evidence and provenance
- `data_quality`
- normalized recovery / Training / Load Focus snapshots
- compact recent-activity context
- the current Daily Load Budget payload

Regular Training Readiness and Morning Training Readiness remain separate source
fields. Snapshot completeness accepts either exact-date readiness source.

### Activity Evaluation

Recent Activity Evaluation is merged. The HA runtime evaluates the five newest
activities from the cached Fitness context and provides a local selector so the
user can switch activity without refetching Garmin.

For supported cycling/power activities it can cache detail samples and expose
best-power windows plus conservative estimated VO2max / FTP when the required
inputs and duration are present. These are estimates, not Garmin-native or lab
measurements.

The selected activity's `max_hr` is the pass maximum. Configured Fitness maximum
heart rate is exposed separately as `user_max_hr`.

### Daily Load Budget V1

Daily Load Budget V1 is merged as an advisory workload-planning heuristic. It
reuses the canonical Fitness history and simulates today's total TRIMP against
four structural constraints:

- ACWR, normal hard limit `1.30`
- Strain
- TSB floor
- Ramp Rate ceiling

Established adverse Insights states may reduce only the remaining capacity.
Favourable recovery never raises the structural ceiling.

V1 deliberately returns zero remaining capacity when the current state already
violates the active structural constraint. This behavior is now known to be too
binary in one live pattern: ACWR can remain above `1.30` while TSB, Ramp and
Strain have otherwise normalized. That is treated as a budget-policy limitation,
not as a reason to change the canonical Fitness formulas.

## Reliability fixes merged after the original handoff

The current Fitness line also includes:

- exact-current-day RHR fallback from Garmin daily summary when historical RHR
  has not propagated yet
- narrow cross-service shadow-activity suppression
- repeated shadow-session cluster suppression while preserving complete real
  overlapping activities
- Daily Load Budget exhausted-capacity rounding fix
- Activity Evaluation pass-max-HR vs configured-max-HR separation
- restored confirmed Garmin Gear ↔ sensor links on the current Fitness line

No TRIMP / CTL / ATL / TSB / ACWR formula was changed by those fixes.

## Daily Load Budget V2 preview

A V2 policy experiment exists only in `ha-garmin` on:

```text
experiment/daily-budget-v2-preview
```

It is intentionally not exported through the public Fitness API and is not wired
into Home Assistant. V1 remains authoritative in HA.

The preview introduces a conservative `reentry` mode only when V1 has zero
capacity solely because ACWR is already above its normal limit. Re-entry requires:

- TSB >= 0
- Ramp Rate <= 0
- no `recovery_caution`
- no `insufficient_or_stale_data`

When eligible, the preview keeps the existing TSB and Ramp constraints, applies
a light Strain ceiling of `4.0`, and guards projected ACWR to at most 5% above
its already-high current value.

The preview branch passed formatting, Ruff, mypy, Python 3.11/3.12/3.13 tests,
and package build. It remains observation-only until enough natural live states
have been compared with V1.

## Data-quality semantics

`*_available` on a recovery source means the exact-date source responded; it does
not guarantee that every desired field in that payload is populated.

Therefore `snapshot_complete` can be false while `sleep_available` or
`hrv_available` is true. `data_quality.missing_sources`, `missing_fields`, and
`stale_fields` are the authoritative explanation. Examples of required recovery
fields include `resting_hr`, `hrv_last_night_avg`, `sleep_score`, and at least
one exact-date Training Readiness value.

A future UI polish item is to surface those missing field names directly instead
of only showing the generic "incomplete insight data" message. That UI change is
not implemented yet.

## Warm-up recovery and persistence

A blocker inside the visible 90-day window blocks the canonical series. An older
blocker may be bypassed only when restarting after it still leaves the configured
minimum complete warm-up period before the visible window.

Current-state Fitness sensors retain stable unique IDs. Completed historical
calendar days are imported to Recorder long-term statistics using the registered
sensor entity IDs. The current day remains owned by the live sensor.

## Diagnostic probe

`fitness_probe.py` / `garmin_connect.fitness_probe` remains useful for raw,
read-only Garmin diagnostics. Probe output can intentionally show raw source
records that the canonical runtime later suppresses during normalization, so raw
probe blockers must not be treated as proof that runtime normalization failed.

## Branch hygiene

After the September cleanup, completed feature/fix branches were removed. Active
long-lived/reference branches in this repository are intentionally limited to:

```text
main
feature/garmin-fitness
feature/garmin-insights-activity-load
feature/garmin-insights-audit
```

The deleted PR branches remain recoverable through Git history / merged PRs.

## Next Fitness milestone

Do not change the canonical Training formulas.

The immediate milestone is continued live comparison of Daily Load Budget V1
against the isolated V2 re-entry preview. If V2 remains conservative and useful
across additional natural states, promote the policy deliberately in
`ha-garmin`, add regression vectors, then pin/wire it in Home Assistant in a
separate change.
