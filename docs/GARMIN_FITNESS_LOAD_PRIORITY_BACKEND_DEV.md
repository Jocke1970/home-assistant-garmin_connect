# Garmin Fitness — Load Priority backend (`dev`)

Status: **development only, not beta-validated**. `main` and `beta` remain untouched.

## What is live in `dev`

The integration manifest uses `3.0.35-dev.1` and pins `Jocke1970/ha-garmin` to commit `4480e4bb60f8c5cc303c1427a89824d0d4951063`.

The normal Insights refresh calls `build_priority_aware_daily_budget` and exposes its output on `sensor.garmin_fitness_garmin_daily_load_budget`. This is NOT merely a read-only preview: the planning budget changes when the installed integration uses this branch. Canonical training history, recorded statistics and normal Fitness metrics remain unchanged.

The budget applies fixed, per-sport source-priority defaults to classify today's activity intensity. Clearly low-intensity activities are excluded in full from the synthetic *planning* day's TRIMP consumption; their actual TRIMP remains in canonical training history. This is an experimental policy decision, not a claim that exercise has no physiological load. Power TSS, pace proxy and Garmin Load are NOT summed or relabeled as TRIMP. The independent ACWR ceiling of 1.30 remains in force, so excluding easy walks can still result in zero remaining budget.

Inspect these sensor attributes: `planning_mode: load_priority`, `planning_policy_version: 2`, `canonical_current_load`, `budget_consuming_load`, `excluded_low_intensity_load`, `low_intensity_activity_count`, `training_activity_count`, `unknown_intensity_activity_count`, `activity_decisions`. Per-activity decisions cover **today only**. Priorities are defaults and cannot yet be persisted through a per-sport settings UI. Power classification requires normalized power and FTP; otherwise the preview attempts the next available source.

## Read-only diagnostic action

Use Home Assistant **Developer Tools → Actions** (enable response display) and call `garmin_connect.fitness_load_priority_preview` with:

```yaml
sport: walking
limit: 10
```

Optional `entity_id` targets a particular Garmin Connect account and is required for multiple accounts. Only that account's cached Fitness context is used, with no extra Garmin API fetch. If it is unavailable the action fails explicitly.

Optional parameters: `sport` (`walking`, `cycling`, `running`, `rowing`, `strength`, `other`); `priority` (ordered list of unique `power`, `hr`, `pace`, `garmin`; requires `sport`); `override` (one method without fallback; requires `sport`); `ftp_watts` (1–2500); `threshold_speed_mps` (0.1–20); `limit` (1–30, default 10). Overrides affect only this diagnostic request, are not stored, and do not alter the live budget policy. Each returned activity includes the selected source, load unit and fallback attempts. Different load units must never be summed.

## Gates before promoting `dev → beta`

1. Verify CI on both the integration repository and `ha-garmin`: tests, formatting, lint, type checks, package build, HACS and Hassfest as applicable.
2. Replay a real easy walking day with high ACWR, a power-based hard cycling day with valid FTP, HR fallback without FTP, mixed easy/hard activities on the same day, missing metrics, and duplicate/shadow-activity scenarios. Verify actual-versus-budget load and whether the hard ACWR cutoff still results in zero.
3. Confirm that excluding *all* clearly easy TRIMP, rather than discounting it, is the intended budget policy. Agree a separate policy for a high pre-existing ACWR if necessary. Do not claim that Load Priority alone solves a zero budget.
4. Reconcile the histories of `dev` and `beta` in BOTH repositories before merging; they currently have diverged. Preserve beta-only changes rather than replacing the beta branch blindly. Check and update the pinned `ha-garmin` commit after dependency changes.
5. Only then merge/reconcile into `beta`, set a distinct `-beta.1` version, and publish a beta pre-release for live HA testing. Promote `beta → main` after real beta validation, not merely green unit tests.

The Garmin Fitness graph card is a separate Lovelace resource. The original `www/garmin_fitness_card/garmin-fitness-card.js` v0.1.5 was restored by correcting the registered `/local/garmin_fitness_card/garmin-fitness-card.js?v=0.1.5` resource; this backend does not deliver that JS file.
