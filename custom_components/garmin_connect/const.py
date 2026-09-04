"""Constants for Garmin Connect integration."""

from typing import Final

DOMAIN: Final = "garmin_connect"
FITNESS_DATA_KEY: Final = f"{DOMAIN}_fitness"

# Config entry keys
CONF_TOKEN: Final = "token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_CLIENT_ID: Final = "client_id"

# Options
CONF_IS_CN: Final = "is_cn"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_FITNESS_MAX_HR: Final = "fitness_max_hr"
CONF_FITNESS_SEX: Final = "fitness_sex"
DEFAULT_SCAN_INTERVAL: Final = 300  # 5 minutes
MIN_SCAN_INTERVAL: Final = 60  # 1 minute
MAX_SCAN_INTERVAL: Final = 3600  # 1 hour
FITNESS_HISTORY_DAYS: Final = 90
FITNESS_WARMUP_DAYS: Final = 90
FITNESS_CALCULATION_DAYS: Final = FITNESS_HISTORY_DAYS + FITNESS_WARMUP_DAYS
# A recovered CTL/ATL series may restart after an incomplete warm-up day only when
# at least this many complete days remain before the visible 90-day window. With
# the v1 42-day CTL EMA this leaves roughly 2% seed influence at the boundary.
FITNESS_RECOVERY_MIN_WARMUP_DAYS: Final = 80
FITNESS_ACWR_ACUTE_DAYS: Final = 7
FITNESS_ACWR_CHRONIC_DAYS: Final = 28
FITNESS_RAMP_PERIOD_DAYS: Final = 7
FITNESS_MAX_HR_MIN: Final = 100
FITNESS_MAX_HR_MAX: Final = 250
FITNESS_SEX_OPTIONS: Final = ("male", "female")
