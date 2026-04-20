"""The Strava Commute Leaderboard integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.event import async_track_time_change

from .const import (
    CONF_ATHLETE_NAME,
    DOMAIN,
    REFRESH_HOUR,
    REFRESH_MINUTE,
    SERVICE_REFRESH,
)
from .coordinator import StravaCommuteCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

UNSUB_DAILY_KEY = "_daily_refresh_unsub"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Strava athlete from a config entry."""
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    athlete_id = entry.data.get("athlete_id")
    if athlete_id is None:
        athlete = (entry.data.get("token") or {}).get("athlete") or {}
        athlete_id = athlete.get("id")
    if athlete_id is None:
        _LOGGER.error("Config entry missing athlete_id; cannot set up")
        return False

    athlete_name = entry.data.get(CONF_ATHLETE_NAME) or entry.title

    coordinator = StravaCommuteCoordinator(
        hass=hass,
        oauth_session=oauth_session,
        athlete_id=int(athlete_id),
        athlete_name=athlete_name,
        options=dict(entry.options),
    )
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _ensure_daily_trigger(hass)
    _ensure_refresh_service(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down one athlete entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not _any_coordinator_left(hass):
        unsub = hass.data[DOMAIN].pop(UNSUB_DAILY_KEY, None)
        if unsub is not None:
            unsub()
        if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
        hass.data.pop(DOMAIN, None)

    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change so new thresholds propagate."""
    await hass.config_entries.async_reload(entry.entry_id)


def _any_coordinator_left(hass: HomeAssistant) -> bool:
    bucket = hass.data.get(DOMAIN, {})
    return any(isinstance(v, StravaCommuteCoordinator) for v in bucket.values())


def _ensure_daily_trigger(hass: HomeAssistant) -> None:
    """Register a once-a-day trigger at REFRESH_HOUR:REFRESH_MINUTE local time."""
    if UNSUB_DAILY_KEY in hass.data.get(DOMAIN, {}):
        return

    async def _fire(_now) -> None:
        await _refresh_all(hass)

    unsub = async_track_time_change(
        hass, _fire, hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0
    )
    hass.data[DOMAIN][UNSUB_DAILY_KEY] = unsub


def _ensure_refresh_service(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def _handle_refresh(_call: ServiceCall) -> None:
        await _refresh_all(hass)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _handle_refresh)


async def _refresh_all(hass: HomeAssistant) -> None:
    for value in list(hass.data.get(DOMAIN, {}).values()):
        if isinstance(value, StravaCommuteCoordinator):
            await value.async_request_refresh()
