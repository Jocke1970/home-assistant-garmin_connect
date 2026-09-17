# Garmin Fitness – JS dashboard (frontend dev)

Status: The frontend was tested alongside the existing dashboard in a real Home Assistant installation on September 17, 2026. This code is added only to `dev`; it is not a HACS release and must not affect `beta` or `main`. Backend `3.0.35-beta.1` is separate.

## Architecture

- `www/garmin_fitness_card/garmin-fitness-dashboard-card.js`: unified presentation of insights, data quality, recent activity, budget, and activity evaluation. Version `0.1.1-dev.2`.
- `www/garmin_fitness_card/garmin-fitness-card.js`: independently mounted, persistent graph card for Recorder/LTS, the 7/28/42/90-day ranges, and three expandable sections. Version `0.1.6-dev.2`.
- Calculations remain exclusively in the backend. The dashboard reads Home Assistant entities and does not call the Garmin API directly.
- The graph card is mounted once. HA state updates must not recreate it or reset the selected range or expanded sections.

**The repository's `www/` directory is a source-code copy. It is not automatically Home Assistant's `/config/www/`, and HACS does not automatically distribute these files as Lovelace resources.** Installation remains manual until a distribution mechanism is implemented.

## Install in HA for parallel testing

1. Keep the existing working Garmin view and a way to restore it. Replace only the two JS files in the actual HA directory, `/config/www/garmin_fitness_card/` (or `/homeassistant/www/garmin_fitness_card/`), when you deliberately choose to test these frontend versions. Keep the existing banner image in the same directory; it is not included in this source package.
2. Under Settings → Dashboards → Resources, configure exactly one JavaScript module resource per file. Edit existing resources instead of adding duplicates:

   ```text
   /local/garmin_fitness_card/garmin-fitness-card.js?v=0.1.6-dev.2
   /local/garmin_fitness_card/garmin-fitness-dashboard-card.js?v=0.1.1-dev.2
   ```

3. Hard-reload the HA view using `Ctrl+Shift+R`, and create a new card from `examples/garmin_fitness_dashboard_dev.yaml` in a dedicated test view. Retain the older YAML stack until all features are verified.
4. Check all four graph ranges, all three expandable sections, the activity selector, data-quality messages, the budget explanation, and footer contrast.

## Observed in Home Assistant

- Actual TRIMP 63.4, budget-consuming TRIMP 0.0, and excluded low-intensity TRIMP 63.4 were displayed together. This confirms the observed breakdown; it does not mean training history was rewritten.
- Actual ACWR 2.48 and planning ACWR 1.81 use different inputs: 63.4 TRIMP is excluded from planning. Present them as separate measurements, not as an automatic synchronization error. Do not guess the explanation if the supporting data is unavailable.
- The 0 TRIMP training budget is limited here by the ACWR threshold; the text must not claim that the budget has already been consumed.
- Version footers use a readable HA theme text color and 12 px text.
- In-HA testing confirmed rendering of the graph, working 7/28/42/90-day ranges and expandable sections, and visible insights, budget, and activity evaluation.

## Limitations and next steps

- Frontend and backend data can update at different times. Explain a difference as expected only when its underlying cause is displayed and verified; investigate unexplained differences further.
- This frontend commit does not change the calculation model, `ha-garmin`, the integration manifest, or the published beta.
- Review and test frontend distribution and version handling separately before promoting `dev` to `beta`.

## Local checks

From the repository root, with Node.js installed:

```bash
node --check www/garmin_fitness_card/garmin-fitness-card.js
node --check www/garmin_fitness_card/garmin-fitness-dashboard-card.js
node www/garmin_fitness_card/tests/dashboard.test.cjs
```

The smoke tests cover budget messaging, ACWR explanations, HTML escaping, insights, activity evaluation, and a persistent graph instance. They do not replace complete browser or integration tests.
