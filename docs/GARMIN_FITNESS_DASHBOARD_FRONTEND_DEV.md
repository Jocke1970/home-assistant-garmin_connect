# Garmin Fitness – JS dashboard (frontend dev)

Status: The frontend was tested alongside the existing dashboard in a real Home Assistant installation on September 17, 2026. This code is added only to `dev`; it is not a HACS release and must not affect `beta` or `main`. Backend `3.0.35-beta.1` is separate.

## Architecture

- `www/garmin_fitness_card/garmin-fitness-dashboard-card.js`: unified presentation of insights, data quality, recent activity, budget, and activity evaluation. Version `0.1.1-dev.2`.
- `www/garmin_fitness_card/garmin-fitness-card.js`: independently mounted, persistent graph card for Recorder/LTS, the 7/28/42/90-day ranges, and three expandable sections. Version `0.1.6-dev.2`.
- Calculations remain exclusively in the backend. The dashboard reads Home Assistant entities and does not call the Garmin API directly.
- The graph card is mounted once. HA state updates must not recreate it or reset the selected range or expanded sections.

**The repository's `www/` directory is a reviewed source copy.** HACS only installs
files below `custom_components/garmin_connect/`, so both JS assets are also shipped
inside `custom_components/garmin_connect/frontend/`. The integration serves this
folder with Home Assistant's asynchronous static-path API. HACS upgrades replace
the packaged files; no copying into `/config/www/` is needed. The static route is
registered without modifying the user's Lovelace resource registry.

## Install in HA for parallel testing

1. Install the integration version that includes the packaged frontend. Restart
   Home Assistant so the updated integration registers its HTTP route.
2. Open `/garmin_connect/frontend/garmin-fitness-card.js` and
   `/garmin_connect/frontend/garmin-fitness-dashboard-card.js` on the HA server.
   Both URLs must return JavaScript, not HTTP 404.
3. Under Settings → Dashboards → Resources, **edit** the two old `/local/`
   entries to the following URLs; do not create duplicate resources:

   ```text
   /garmin_connect/frontend/garmin-fitness-card.js
   /garmin_connect/frontend/garmin-fitness-dashboard-card.js
   ```

   Keep each resource's type as JavaScript module. These routes disable HTTP
   cache headers, so their paths stay stable across HACS updates. Restart HA
   and hard-reload the browser after an upgrade; JavaScript custom elements
   cannot be hot-replaced inside an already-open tab.
4. Add `examples/garmin_fitness_dashboard_dev.yaml` in a separate test view.
   Retain the older YAML stack for rollback. The banner image remains a local,
   user-managed asset at `/local/garmin_fitness_card/garmin_fitness_banner.png`.
   Set `show_banner: false` if this image is unavailable.
5. Verify the graph's four ranges, three expandable sections, the selector,
   insights, ACWR explanation, data quality, and footer contrast.

Rollback: switch the two resource URLs back to the previous `/local/` paths,
then hard-reload. Do not delete the previous working JS files during testing.

## Observed in Home Assistant

- Actual TRIMP 63.4, budget-consuming TRIMP 0.0, and excluded low-intensity TRIMP 63.4 were displayed together. This confirms the observed breakdown; it does not mean training history was rewritten.
- Actual ACWR 2.48 and planning ACWR 1.81 use different inputs: 63.4 TRIMP is excluded from planning. Present them as separate measurements, not as an automatic synchronization error. Do not guess the explanation if the supporting data is unavailable.
- The 0 TRIMP training budget is limited here by the ACWR threshold; the text must not claim that the budget has already been consumed.
- Version footers use a readable HA theme text color and 12 px text.
- In-HA testing confirmed rendering of the graph, working 7/28/42/90-day ranges and expandable sections, and visible insights, budget, and activity evaluation.

## Limitations and next steps

- Frontend and backend data can update at different times. Explain a difference as expected only when its underlying cause is displayed and verified; investigate unexplained differences further.
- This distribution change adds an HTTP dependency and bumps only dev's integration manifest. It does not change the calculation model, `ha-garmin`, or the published beta.
- Test packaged HTTP URLs, resource migration, and rollback in HA before promoting `dev` to `beta`.

## Local checks

From the repository root, with Node.js installed:

```bash
node --check www/garmin_fitness_card/garmin-fitness-card.js
node --check www/garmin_fitness_card/garmin-fitness-dashboard-card.js
node www/garmin_fitness_card/tests/dashboard.test.cjs
```

The smoke tests cover budget messaging, ACWR explanations, HTML escaping, insights, activity evaluation, and a persistent graph instance. They do not replace complete browser or integration tests.
