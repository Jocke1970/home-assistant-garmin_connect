# Garmin Fitness graph card — dev restore

The complete Load Priority Lovelace example at `examples/garmin_fitness_budget_load_priority_dev.yaml` only contains the standalone budget card. The separate **complete** Lovelace stack distributed for UI testing contains `custom:garmin-fitness-card` (days 90; show_title true) between Latest Activity and Daily Budget. This is an independent JavaScript custom card; the budget YAML cannot implement or fix its graphs.

The reference frontend supplied for this work is `garmin-fitness-card.js` v0.1.5, containing the ACWR/Ramp overview, 7/28/42/90-day selection, and three native expanders: Strain, Träningsbelastning (Daily Load + CTL/ATL) and Formbalans (TSB). The full JS file is distributed as a separate UI attachment with the Lovelace stack; this repository does **not** yet contain that JS source. Do not claim that installing the HA integration deploys this card automatically.

To install for an individual HA dev test, place that JS file at the actual HA configuration directory's `www/garmin-fitness-card.js`. The corresponding browser URL is `/local/garmin-fitness-card.js`. Ensure exactly one JavaScript resource in Home Assistant Dashboards → Resources and use `/local/garmin-fitness-card.js?v=0.1.5` (JavaScript module). Retain the original YAML card:

```yaml
- type: custom:garmin-fitness-card
  days: 90
  show_title: true
```

Verify directly by opening the `/local/...` URL: it must display JavaScript text, not a 404, HA dashboard, or login redirect. Reload HA frontend. If the red configuration error remains, check browser Console and Network for script errors. This is a frontend loading/registration problem until an exact error proves otherwise; missing Fitness entities would normally show the custom card's own warning instead of HA's configuration-error placeholder.

Checks run against the original v0.1.5 file: `node --check` succeeded and a mock HA browser test successfully registered and rendered headings/expanders for Strain, Träningsbelastning, Formbalans and all four time intervals. This is **not** proof of successful installation in the user's browser or valid Recorder statistics.

No changes to Fitness algorithms, beta or main are part of this fix.