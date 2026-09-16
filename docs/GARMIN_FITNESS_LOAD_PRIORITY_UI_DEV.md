# Garmin Fitness — Load Priority UI (`dev`)

Status: **Lovelace UI work prepared for review, not deployed to the user's Home Assistant**. `beta` and `main` are unchanged. Preserve the last known Garmin Fitness stack and its banner → Insights → conditional data quality → latest activity → existing graph card v0.1.5 → daily budget → activity evaluation order.

## Complete budget card

Use [`examples/garmin_fitness_budget_load_priority_dev.yaml`](../examples/garmin_fitness_budget_load_priority_dev.yaml) as a complete replacement for **only** the existing `custom:button-card` budget card. The full preserved Cycling stack, including the pass-evaluation enhancement, is also delivered as a downloadable YAML artifact in the chat where this change was requested; do not substitute the budget-only example for that whole stack.

The budget card:

- Uses `budget_consuming_load` for the progress bar and its left-hand total; falls back to legacy `current_load` if the planning-policy data is not available.
- Shows a three-column breakdown **only** when `planning_mode: load_priority` and all three fields are valid numbers: `canonical_current_load` (actual TRIMP), `budget_consuming_load` (TRIMP charged against the planning budget), and `excluded_low_intensity_load` (canonical TRIMP excluded for clearly low-intensity activity).
- Keeps `remaining_load`, `recommended_max_load`, limiting-factor labels and projected ACWR / Strain / TSB / Ramp in their existing locations. A remaining capacity of zero is described as no further *training budget*, never a prohibition on all movement.
- Treats absent/unavailable/nonfinite values as missing, not numeric zero, so the headline and progress avoid `NaN`.
- Flags unknown intensity count as unclassified rather than falsely claiming an exclusion.

## Selected activity diagnostics

The full-stack UI patch adds an optional `source` field within the existing selected activity `custom:button-card`. It finds the currently selected evaluation using `sensor.garmin_activity_evaluation.attributes.selected_activity_id` and compares it with `activity_id` in `sensor.garmin_fitness_garmin_daily_load_budget.attributes.activity_decisions`. When they match, the row shows the selected source (HR, Power, Pace or Garmin), intensity lane, and whether this particular activity was excluded from the planning budget. Its display is hidden when no current-day decision matches. `triggers_update` includes both sensor entity IDs.

**The backend currently exposes decisions only for today's budget.** Selecting one of the five most recent activities from an earlier day must not cause the UI to invent a source or extrapolate an exclusion. Future per-activity history support is a separate backend task.

The backend's sport priorities are currently defaults, not persistent editable per-sport settings. This UI deliberately provides no pretend Settings controls. It also does not mix Power TSS, Garmin Load or Pace proxy values into the canonical TRIMP budget.

## Dependencies / verification

1. Check that installed `dev` exposes `planning_mode`, `canonical_current_load`, `budget_consuming_load`, `excluded_low_intensity_load`, `activity_decisions`, and the existing budget fields before testing new content. The UI falls back to legacy labels where possible.
2. Check that the existing `custom:garmin-fitness-card` JavaScript resource is actually served and registered. The red `Konfigurationsfel` seen in the graph-card location is a **separate unresolved problem**; this UI change neither removes nor fixes that card.
3. Validate layout on mobile and desktop and test normal backend, missing budget data, old backend, and selecting an activity from yesterday. Confirm the data-quality notice still only appears for missing/stale fields.
4. Promote changes **dev → beta → main** only after backend tests, HACS/Hassfest and real HA UI verification; no automatic promotion.

Source-of-truth separation: `ha-garmin` owns Fitness formulas. The HA integration owns orchestration/entity contracts. These Lovelace changes only display available attributes and never rewrite CTL, ATL, TSB, ACWR, Recorder data or training load history.
