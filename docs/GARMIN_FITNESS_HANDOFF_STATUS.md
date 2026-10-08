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

- soak-test `2026.10.0b2` before stable promotion
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
