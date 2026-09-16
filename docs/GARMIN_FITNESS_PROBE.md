# Garmin Fitness live probe

The `garmin_connect.fitness_probe` action is a temporary, read-only diagnostic for the Garmin Fitness project.

It reuses the Garmin Connect integration's existing authenticated `GarminClient`. It does not create a second Garmin login, write to Garmin Connect, or write to Home Assistant Recorder/statistics.

## Run the probe

In Home Assistant, open **Developer Tools → Actions** and select **Garmin Connect: Fitness probe**.

Use the default 90-day window unless a shorter diagnostic window is needed.

The action returns response data directly in Home Assistant.

## What to inspect

The response includes:

- total activities and activity days in the selected window;
- Garmin `activityTrainingLoad` coverage;
- TRIMP input readiness based on average heart rate plus duration;
- coverage grouped by Garmin activity type;
- complete versus incomplete Garmin-load activity days;
- the latest activity and up to ten recent activities using training-relevant fields only.

The compact activity output intentionally excludes GPS coordinates, routes, polylines, and location fields.

For the first live validation, confirm that the newest indoor rowing activity appears as `latest_activity` and inspect:

- `garmin_training_load`;
- `average_hr`;
- `max_hr`;
- `duration_minutes`;
- `aerobic_training_effect`;
- `anaerobic_training_effect`;
- `trimp_activity_inputs_ready`.

## How the result will be used

The probe does not select a canonical training-load source. Its purpose is to provide real-account evidence before choosing between Garmin Training Load and Banister TRIMP for the permanent Fitness pipeline.

A genuine rest day may later be represented as zero daily load. An activity day where the selected load source lacks required data must remain incomplete rather than being silently converted to zero.

After the source decision is validated, the temporary probe will be replaced or absorbed by the permanent `FitnessCoordinator`, sensor, and long-term-statistics implementation.
