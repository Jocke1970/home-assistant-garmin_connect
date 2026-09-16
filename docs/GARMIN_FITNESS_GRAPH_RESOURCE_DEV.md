# Garmin Fitness graph resource — dev troubleshooting

The approved Lovelace block already has `custom:garmin-fitness-card` between latest activity and daily budget. The red `Konfigurationsfel` in this position means that the graph component has not rendered. It does **not** identify the precise cause. The currently committed integration `www` directory does not contain `garmin-fitness-card.js`; integration assets are not automatically the HA `/local/` route.

## Deliverable

The conversation attachment `garmin_fitness_grafer_v0.1.6_dev_bundle.zip` contains the complete graph source (`garmin-fitness-card.js`), unchanged-layout complete Lovelace YAML, optional resource diagnostic card, and installation instructions. The full JS source is distributed in that package; this document by itself is **not** a working frontend resource.

## Install the real file

Copy its `garmin-fitness-card.js` to the Home Assistant **configuration directory**'s `www/garmin-fitness-card.js` (usually `/config/www/`, sometimes `/homeassistant/www/`). It must be HA config's `www/`, not `custom_components/garmin_connect/www/` or a GitHub checkout. In Settings → Dashboards → Resources, update the **existing** JavaScript module resource to `/local/garmin-fitness-card.js?v=0.1.6-dev.1`; do not create duplicates. Force reload/close and reopen mobile app. Existing Lovelace graph YAML needs just `type: custom:garmin-fitness-card`, `days: 90`, `show_title: true`.

On the same HA host, opening `/local/garmin-fitness-card.js?v=0.1.6-dev.1` should show raw JavaScript, starting with `Garmin Fitness Card v0.1.6-dev.1`. A dashboard, login, 404 or HTML instead of JS means the asset response needs investigation; simply editing the YAML cannot fix missing JavaScript.

## Distinguish versions from errors

The v0.1.6-dev.1 card displays its *actual* JS version on loading and in the footer. The independently rendered example `examples/garmin_fitness_resource_diagnostic_dev.yaml` displays whether a card class is registered and the loaded version. In desktop browser console, `customElements.get('garmin-fitness-card')?.prototype.cardVersion` must return `0.1.6-dev.1` after the new script is loaded. If undefined, inspect the Network response/status/content-type for the `/local/...` resource. If version matches but the red error remains, capture the actual Lovelace error / first browser console exception; **do not** claim the route was the root cause without that evidence.

When rendered, the card contains ACWR/Ramp, period selection 7/28/42/90 days, and three expandable charts: Strain, Träningsbelastning and Formbalans (TSB). Missing Recorder history produces a visible status message, not a separate Lovelace `Konfigurationsfel`.

This is dev-only and changes no Training formulas, beta or main branches. Validate in real HA before promotion.
