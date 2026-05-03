"""Pytest configuration.

Tests target the stand-alone helper module `fuel_price` directly, bypassing
the `custom_components.strava_commute_leaderboard` package init (which imports
homeassistant and isn't available in plain CI). We add the integration's
own directory to sys.path so `from fuel_price import ...` resolves.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(
    0, str(ROOT / "custom_components" / "strava_commute_leaderboard")
)
