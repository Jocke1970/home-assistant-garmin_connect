# Garmin Fitness — Load Priority backend (`dev`)

Status: **dev-only diagnostic action; not a new live training-load algorithm.**

This integration pins `Jocke1970/ha-garmin` at `4480e4bb60f8c5cc303c1427a89824d0d4951063` so the isolated source-priority engine is available at runtime. `main` is unchanged. Promote `dev` to `beta` only after review and passing tests/Hassfest/HACS, and `beta` to `main` only after validation with real activities.

## Backend action

Use Home Assistant **Developer Tools → Actions** (enable response display) and call `garmin_connect.fitness_load_priority_preview` with the following service data:

```yaml
sport: walking
limit: 10
```

Optional `entity_id` targets a specific Garmin Connect account, mandatory when multiple accounts exist. It selects the existing authenticated account using the integration's normal entity registry resolution. The action then uses **only that account's cached Garmin Fitness context**. If Fitness is not configured or the context is unavailable, the action errors rather than guessing from another account.

Optional parameters: `sport` (`walking`, `cycling`, `running`, `rowing`, `strength`, `other`); `priority` (ordered, unique list of `power`, `hr`, `pace`, `garmin`, requires `sport`); `override` (one method with *no fallback*, requires `sport`); `ftp_watts` (1–2500); `threshold_speed_mps` (0.1–20); and `limit` (1–30, default 10). Changes only affect the current request, are not stored and do not change the canonical data.

Example power preview:

```yaml
sport: cycling
priority:
  - power
  - hr
  - pace
  - garmin
ftp_watts: 200
limit: 5
```

The action returns per-activity `selected_source`, `load`, `unit`, priority and an `attempts` trail documenting missing inputs or fallback. It also returns `matched_activities`, `returned_activities`, and counts of methods selected in the returned subset. These counts **are not workload totals**.

## Safety constraints

* The current canonical pipeline stays Banister TRIMP. Existing Daily Load, CTL, ATL, TSB, ACWR, Ramp, Strain, budget and recorded long-term statistics are unmodified.
* TRIMP, Power TSS, Garmin Load and the experimental pace proxy have different scales. **Never sum them, relabel them as TRIMP, or pass them to the budget.** Pace is an unvalidated proxy.
* The action is read-only. It uses cached context and makes no additional Garmin API calls. Missing readings stay unavailable (`null`), not zero.
* `activity_id` is returned for inspection only, not automatically written to state history.
* Selecting HR for walking does not automatically fix V1's separate hard ACWR cutoff; budget policy requires its own replay tests and review.

## Release gates

1. On `dev`, validate code and service tests plus Hassfest and HACS. Verify an activity with normalized power + FTP, a walk with HR, a missing-FTP fallback, and an override without fallback.
2. Inspect real Garmin API power, resting-HR, FTP and threshold availability and determine a calibrated common workload scale (or maintain separate histories). Review explicit rules for historical recalculation.
3. Keep `beta` unchanged until the above review. Promote deliberately to `beta` and retest; do not promote to `main` without validation. Do not label this diagnostic preview as a completed budget fix.

The separate graph-card `Konfigurationsfel` is a frontend issue and not affected by this backend action.
