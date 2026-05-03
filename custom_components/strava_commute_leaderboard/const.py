"""Constants for the Strava Commute Leaderboard integration."""
from __future__ import annotations

DOMAIN = "strava_commute_leaderboard"

OAUTH2_AUTHORIZE = "https://www.strava.com/oauth/authorize"
OAUTH2_TOKEN = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"

DEFAULT_SCOPE = "read,activity:read_all"

REFRESH_HOUR = 18
REFRESH_MINUTE = 0

SERVICE_REFRESH = "refresh"

CONF_ATHLETE_NAME = "athlete_name"
CONF_CO2_PER_KM = "co2_per_km"
CONF_FUEL_EFFICIENCY_KM_PER_L = "fuel_efficiency_km_per_l"
CONF_FUEL_PRICE_PER_L = "fuel_price_per_l"
CONF_USE_LIVE_FUEL_PRICE = "use_live_fuel_price"
CONF_CURRENCY = "currency"
CONF_STREAK_TOLERANCE = "streak_tolerance_days"

DEFAULT_CO2_PER_KM = 0.192
DEFAULT_FUEL_EFFICIENCY_KM_PER_L = 11.0
DEFAULT_FUEL_PRICE_PER_L = 14.0
DEFAULT_USE_LIVE_FUEL_PRICE = True
DEFAULT_CURRENCY = "DKK"
DEFAULT_STREAK_TOLERANCE = 3

RIDE_TYPES = {
    "Ride",
    "EBikeRide",
    "VirtualRide",
    "MountainBikeRide",
    "GravelRide",
    "EMountainBikeRide",
}

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "strava_commute_{athlete_id}"
