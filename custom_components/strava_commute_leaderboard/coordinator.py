"""DataUpdateCoordinator for a single Strava athlete."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StravaApi, StravaApiError, StravaRateLimitError
from .const import (
    CONF_CO2_PER_KM,
    CONF_COST_PER_KM,
    CONF_STREAK_TOLERANCE,
    DEFAULT_CO2_PER_KM,
    DEFAULT_COST_PER_KM,
    DEFAULT_STREAK_TOLERANCE,
    DOMAIN,
    RIDE_TYPES,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class CommuteStats:
    """Aggregated commute stats for one athlete."""

    athlete_id: int
    athlete_name: str
    distance_km_ytd: float = 0.0
    rides_ytd: int = 0
    moving_time_hours_ytd: float = 0.0
    elevation_m_ytd: float = 0.0
    avg_speed_kmh: float = 0.0
    streak_current: int = 0
    streak_longest: int = 0
    days_this_month: int = 0
    last_ride: datetime | None = None
    co2_saved_kg: float = 0.0
    money_saved: float = 0.0
    per_week_km: dict[str, float] = field(default_factory=dict)


class StravaCommuteCoordinator(DataUpdateCoordinator[CommuteStats]):
    """Fetches and aggregates commute activities for a single athlete.

    Not driven by update_interval — refreshed externally by a daily time trigger
    and by the manual refresh service.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        oauth_session: OAuth2Session,
        athlete_id: int,
        athlete_name: str,
        options: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{athlete_id}",
            update_interval=None,
        )
        self._oauth_session = oauth_session
        self.athlete_id = athlete_id
        self.athlete_name = athlete_name
        self._options = options
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(athlete_id=athlete_id)
        )
        self._cached_activities: list[dict[str, Any]] = []
        self._last_fetched_epoch: int = 0
        self._api = StravaApi(async_get_clientsession(hass), self._async_get_token)

    async def _async_get_token(self) -> str:
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token["access_token"]

    async def async_load_cache(self) -> None:
        """Load persisted activity cache from disk."""
        data = await self._store.async_load()
        if data is None:
            return
        cached_year = data.get("year")
        if cached_year != _start_of_year().year:
            _LOGGER.debug("Cache for athlete %s is from a prior year — discarding", self.athlete_id)
            return
        self._cached_activities = data.get("activities", [])
        self._last_fetched_epoch = data.get("last_fetched_epoch", 0)

    async def _async_save_cache(self) -> None:
        await self._store.async_save(
            {
                "year": _start_of_year().year,
                "activities": self._cached_activities,
                "last_fetched_epoch": self._last_fetched_epoch,
            }
        )

    async def _async_update_data(self) -> CommuteStats:
        after = self._last_fetched_epoch or int(_start_of_year().timestamp())
        try:
            new_activities = await self._api.get_activities_since(after)
        except StravaRateLimitError:
            _LOGGER.warning(
                "Strava rate limit hit for athlete %s; reusing cached data", self.athlete_id
            )
            return self._aggregate()
        except StravaApiError as err:
            raise UpdateFailed(f"Strava API error: {err}") from err

        if new_activities:
            existing_ids = {a["id"] for a in self._cached_activities}
            for activity in new_activities:
                if activity["id"] not in existing_ids:
                    self._cached_activities.append(activity)
            self._last_fetched_epoch = max(
                self._last_fetched_epoch,
                int(datetime.now(tz=timezone.utc).timestamp()),
            )
            await self._async_save_cache()

        return self._aggregate()

    def _aggregate(self) -> CommuteStats:
        stats = CommuteStats(athlete_id=self.athlete_id, athlete_name=self.athlete_name)

        commutes = [
            a
            for a in self._cached_activities
            if a.get("commute") is True and a.get("type") in RIDE_TYPES
        ]
        commutes.sort(key=lambda a: a["start_date"])

        total_distance_m = 0.0
        total_moving_s = 0
        total_elev = 0.0
        days_commuted: set[date] = set()
        today = date.today()
        this_month = (today.year, today.month)
        week_totals: dict[str, float] = {}

        for activity in commutes:
            distance_m = float(activity.get("distance") or 0)
            moving_s = int(activity.get("moving_time") or 0)
            elev = float(activity.get("total_elevation_gain") or 0)
            total_distance_m += distance_m
            total_moving_s += moving_s
            total_elev += elev
            started = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
            local_day = started.astimezone().date()
            days_commuted.add(local_day)
            iso_year, iso_week, _ = local_day.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            week_totals[key] = week_totals.get(key, 0.0) + distance_m / 1000.0
            stats.last_ride = started

        stats.rides_ytd = len(commutes)
        stats.distance_km_ytd = round(total_distance_m / 1000.0, 1)
        stats.moving_time_hours_ytd = round(total_moving_s / 3600.0, 2)
        stats.elevation_m_ytd = round(total_elev, 0)
        if total_moving_s > 0:
            stats.avg_speed_kmh = round((total_distance_m / total_moving_s) * 3.6, 1)
        stats.days_this_month = sum(
            1 for d in days_commuted if (d.year, d.month) == this_month
        )

        tolerance = self._options.get(CONF_STREAK_TOLERANCE, DEFAULT_STREAK_TOLERANCE)
        stats.streak_current, stats.streak_longest = _compute_streaks(
            days_commuted, today, tolerance
        )

        co2_per_km = self._options.get(CONF_CO2_PER_KM, DEFAULT_CO2_PER_KM)
        cost_per_km = self._options.get(CONF_COST_PER_KM, DEFAULT_COST_PER_KM)
        stats.co2_saved_kg = round(stats.distance_km_ytd * co2_per_km, 1)
        stats.money_saved = round(stats.distance_km_ytd * cost_per_km, 2)
        stats.per_week_km = {k: round(v, 1) for k, v in week_totals.items()}

        return stats


def _start_of_year() -> datetime:
    now = datetime.now(tz=timezone.utc).astimezone()
    return datetime(now.year, 1, 1, tzinfo=now.tzinfo)


def _compute_streaks(
    commute_days: set[date], today: date, tolerance_days: int
) -> tuple[int, int]:
    """Compute current and longest streak based on workdays.

    A streak counts one per workday with a commute. It breaks only after
    `tolerance_days` consecutive workdays without a commute.
    """
    if not commute_days:
        return 0, 0

    workdays: list[date] = []
    cursor = min(commute_days)
    while cursor <= today:
        if cursor.weekday() < 5:
            workdays.append(cursor)
        cursor += timedelta(days=1)

    longest = 0
    current_run = 0
    missing_in_a_row = 0
    current_streak_at_end = 0
    for day in workdays:
        if day in commute_days:
            current_run += 1
            missing_in_a_row = 0
        else:
            missing_in_a_row += 1
            if missing_in_a_row >= tolerance_days:
                longest = max(longest, current_run)
                current_run = 0
    longest = max(longest, current_run)
    current_streak_at_end = current_run
    return current_streak_at_end, longest
