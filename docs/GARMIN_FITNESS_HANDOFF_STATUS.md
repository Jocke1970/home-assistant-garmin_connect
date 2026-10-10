# Garmin Fitness handoff status

> Status: active beta runtime  
> Updated: 2026-10-08  
> Home Assistant beta: `2026.10.0b3`  
> `ha-garmin` beta pin: `0703c4cf1df52d5c23d0a34696e4715c497a3e0d`  
> Release flow: `dev → beta → main`

## Source of truth

Garmin Fitness calculations live in `ha-garmin`.

`home-assistant-garmin_connect` owns Home Assistant orchestration:

- config/options
- coordinator lifecycle
- current-state sensors
- Recorder / long-term-statistics import
- warm-up recovery policy
- localized presentation/provenance
- HACS-packaged frontend resources

The Home Assistant integration must not maintain independent implementations of
TRIMP, CTL, ATL, TSB, ACWR, ramp rate, strain, Load Focus, Activity Evaluation,
or the base Daily Load Budget math.

## Canonical Training runtime

Current canonical load source: **Banister TRIMP**.

The installed runtime reports:

- Fitness `algorithm_version: 2`
- 90-day displayed history
- 180-day calculation window with warm-up support
- CTL 42 days / ATL 7 days
- ACWR 7 / 28 days
- Ramp Rate 7 days
- Strain calibration from real historical sessions

Algorithm v2 corrects Banister TRIMP by applying the sex-specific multiplicative
coefficient in addition to the exponential constant:

- male: `0.64 × exp(1.92 × HRR)`
- female: `0.86 × exp(1.67 × HRR)`

The correction was live-verified in Home Assistant: a male-profile day that had
previously reported 84.0 TRIMP recalculated to 53.8 TRIMP.

Canonical history remains homogeneous TRIMP. Garmin Load, power TSS and pace
proxy values are not silently mixed into CTL/ATL/TSB/ACWR history.

## Insights and Daily Load Budget

Insights Rules V1 remain deterministic and presentation-neutral in
`ha-garmin`.

The current Home Assistant budget uses planning policy v2:

```text
planning_mode: load_priority
planning_policy_version: 2
```

Load Priority selects a source per sport for **intensity classification**.
Clearly low-intensity activity may be excluded from the synthetic planning
day's budget consumption. Its real TRIMP remains in canonical history.

Important budget attributes include:

- `canonical_current_load`
- `budget_consuming_load`
- `excluded_low_intensity_load`
- `low_intensity_activity_count`
- `training_activity_count`
- `unknown_intensity_activity_count`
- `activity_decisions`

This is a planning model, not a medical recommendation and not a rewrite of the
actual training history.

## Activity evaluation

Activity Evaluation is local and deterministic. The HA selector exposes recent
activities while the backend evaluates the selected activity without a new
Garmin login or a second training-history database.

The presentation text "after the activity" must be interpreted carefully:
historical ACWR/Strain/TSB values are daily analytical values, not necessarily a
stored intra-day snapshot immediately after each individual activity.

## Activity-linked Gear

`ha-garmin` owns the canonical activity/Gear cache.

The latest activity can expose:

```yaml
linked_gear_count: 2
linked_gear:
  - gear_uuid: ...
    name: ...
    gear_type: ...
    brand: ...
    model: ...
    custom_make_model: ...
```

This path was live-verified with `2026.10.0b2` in Home Assistant. The old
`feature/garmin-insights-activity-load` branch is therefore superseded by the
normal `dev → beta` line and can be removed after verification.

## Frontend distribution

The Garmin Fitness graph and dashboard JavaScript files are packaged below:

```text
custom_components/garmin_connect/frontend/
```

and served by the integration under:

```text
/garmin_connect/frontend/
```

Manual copies of those JS files into `/config/www` are legacy troubleshooting
material, not the normal HACS installation path.

The Garmin Fitness banner is still a user-managed local asset at:

```text
/local/garmin_fitness_card/garmin_fitness_banner.png
```

until it is deliberately packaged or replaced by a different asset strategy.

## Home Assistant 2026.10

Home Assistant 2026.10 changed config/service schema typing to `probatio`.
The integration's schema imports were migrated accordingly and validated by
HACS, Hassfest, pre-commit and Pytest before `2026.10.0b2`.

## Branch and release hygiene

Only these long-lived branches are canonical:

```text
dev
beta
main
```

Release procedure:

1. implement and test on `dev`
2. sync/reconcile `beta` history back into `dev`
3. promote `dev → beta`
4. require green CI
5. publish `YYYY.MM.0bN` as a GitHub pre-release
6. install that pre-release through HACS and verify in real Home Assistant
7. promote `beta → main` only after real beta validation
8. stable version is `YYYY.MM.0`

Feature branches are temporary and should be deleted after their useful work is
present in the canonical release line.

## Current next steps

No Training formula change is required.

Practical remaining polish:

- soak-test `2026.10.0b3` before any stable promotion
- optionally normalize cosmetic whitespace/generic Garmin Gear names
- decide whether to package the Garmin Fitness banner
- continue supervised Gear sensor-linking work only through `dev`

## Upcoming development (not released)

The active `dev` branch is being hardened ahead of a future beta. The
`upload_activity` service now restricts input paths to files within the HA
configuration directory or paths permitted by `allowlist_external_dirs`.
Symlinks are resolved before checking permission and only FIT, GPX and TCX
extensions are accepted. Blocking file checks run in Home Assistant's executor.
Coverage includes allowed files, external paths, symlink escape, unsupported
extensions and missing files. The installed `2026.10.0b3` beta is unchanged.

Further planned work: token refresh durability, frontend cache-busting and
selective upstream integration. These are not part of this hardening change.

## Next gig: Activity Evaluation linked Gear presentation (planned, unreleased)

The activity-linked Gear backend is already canonical in `ha-garmin`, and
`linked_gear` / `linked_gear_count` were live-verified on **Last Activity**
with beta `2026.10.0b2`. However, the **Activity Evaluation** sensor does not
currently expose linked Gear for its selected activity, and the dashboard
`garmin-fitness-dashboard-card.js` does not render Gear inside Passutvärdering.

Implementation requirements:

1. Resolve Gear against the **selected activity ID** (one of the recent
   selectable activities), using the existing canonical `ha-garmin` cache.
   Never reuse Last Activity's Gear unconditionally for historical selections.
2. Add `linked_gear` and `linked_gear_count` for the selected activity to
   Activity Evaluation's HA sensor attributes. Do not build a second Gear cache
   or trigger extra Garmin API requests on every selection.
3. Render a compact, light/theme-aware premium section **Utrustning som användes**
   within Passutvärdering, with Gear name, optional custom make/model, and a
   suitable equipment icon. Escape dynamic strings in JavaScript.
4. Show an understated empty state where the selected activity genuinely has no
   linked Gear; distinguish absent/unavailable linkage from confirmed empty Gear
   when the backend can make that distinction.
5. Regression-test activity switching (different Gear per activity), historical
   activity selection, missing metadata, XSS escaping, and no new API/cache work.
   Keep the existing graph card instance persistent on HA state refreshes.
6. Rename or clarify **Efter passet (faktisk belastning)**: historical ACWR,
   Strain and TSB come from an activity-day snapshot, not necessarily a value
   measured immediately after the selected workout.

Boundaries: presentation and a narrow data handoff only; no changes to
canonical TRIMP, Load Priority calculations, or Gear history. Keep the
packaged frontend and `www/garmin_fitness_card/` source copies synchronized.
Implement on `dev`; verify tests/CI, then promote through `dev → beta → main`.
Current `2026.10.0b3` remains the HA soak-test baseline.

## ACWR comparison investigation (2026-10-10, dev-only)

HA beta `2026.10.0b3` showed canonical ACWR 1.15 and projected budget ACWR 1.30 while today's canonical, budget-consuming and excluded low-intensity TRIMP all showed zero. The reason is **not yet confirmed**. The budget backend reconstructs a planning history; the canonical ACWR is read from Fitness data. Compare their dates, refresh times, history windows and source values before treating the numbers as an algorithm defect. Do not silently suppress the discrepancy.

On `dev` the dashboard explanatory warning is clarified for the no-exclusions case. The packaged JS and `www` source copy, plus dashboard smoke assertion, are synchronized. This UI text change does not alter TRIMP, ACWR or budget calculations. CI and an actual HA test remain required before a new beta.

## Selected-activity Gear UI: implementation in dev (unreleased)

The dashboard now has a compact `Utrustning som användes` section driven by
`sensor.garmin_activity_evaluation.linked_gear`. The HA evaluation adapter
only copies Gear from an existing Activity coordinator record whose
`activityId` matches the selected pass. It checks `lastActivity` and
`lastActivities` already in memory and makes **no additional Garmin API
request**. Missing Gear metadata remains `null` (unknown, section hidden);
a known empty `linked_gear: []` displays an explicit empty state. The
historic ACWR/Strain/TSB section is now labeled `Belastning för passets
kalenderdag`.

Limitations to verify in real HA: Garmin may only populate `linked_gear`
for `lastActivity`, not all `lastActivities`. In that case older selected
activities will correctly show no Gear rather than borrowing Gear from
another workout. Expanding the canonical ha-garmin activity/Gear cache for
older activity IDs is a separate follow-up and must not duplicate caches.

Packaged/source JS copies and smoke assertions have been updated. CI,
end-to-end HA verification, and any future promotion to beta are pending.
The installed `2026.10.0b3` remains unchanged.
