"""Sensor platform for Strava Commute Leaderboard."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfMass, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CURRENCY, DEFAULT_CURRENCY, DOMAIN
from .coordinator import CommuteStats, StravaCommuteCoordinator


@dataclass(frozen=True, kw_only=True)
class CommuteSensorDescription(SensorEntityDescription):
    """Describes one per-athlete commute sensor."""

    value_fn: Callable[[CommuteStats], Any]


SENSORS: tuple[CommuteSensorDescription, ...] = (
    CommuteSensorDescription(
        key="distance_ytd",
        translation_key="distance_ytd",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=lambda s: s.distance_km_ytd,
    ),
    CommuteSensorDescription(
        key="rides_ytd",
        translation_key="rides_ytd",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.rides_ytd,
    ),
    CommuteSensorDescription(
        key="time_ytd",
        translation_key="time_ytd",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=lambda s: s.moving_time_hours_ytd,
    ),
    CommuteSensorDescription(
        key="elevation_ytd",
        translation_key="elevation_ytd",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda s: s.elevation_m_ytd,
    ),
    CommuteSensorDescription(
        key="avg_speed",
        translation_key="avg_speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.avg_speed_kmh,
    ),
    CommuteSensorDescription(
        key="streak_current",
        translation_key="streak_current",
        icon="mdi:fire",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.streak_current,
    ),
    CommuteSensorDescription(
        key="streak_longest",
        translation_key="streak_longest",
        icon="mdi:trophy",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.streak_longest,
    ),
    CommuteSensorDescription(
        key="days_this_month",
        translation_key="days_this_month",
        icon="mdi:calendar-check",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.days_this_month,
    ),
    CommuteSensorDescription(
        key="last_ride",
        translation_key="last_ride",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_ride,
    ),
    CommuteSensorDescription(
        key="co2_saved",
        translation_key="co2_saved",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:leaf",
        suggested_display_precision=1,
        value_fn=lambda s: s.co2_saved_kg,
    ),
    CommuteSensorDescription(
        key="money_saved",
        translation_key="money_saved",
        icon="mdi:cash-multiple",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda s: s.money_saved,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for one athlete and the household comparison set."""
    coordinator: StravaCommuteCoordinator = hass.data[DOMAIN][entry.entry_id]

    currency = entry.options.get(CONF_CURRENCY, DEFAULT_CURRENCY)

    entities: list[SensorEntity] = [
        CommuteSensor(coordinator, description, currency)
        for description in SENSORS
    ]

    all_coordinators: dict[str, StravaCommuteCoordinator] = {
        eid: hass.data[DOMAIN][eid]
        for eid in hass.data[DOMAIN]
        if isinstance(hass.data[DOMAIN][eid], StravaCommuteCoordinator)
    }
    if len(all_coordinators) >= 2:
        entities.extend(
            _build_comparison_sensors(list(all_coordinators.values()))
        )

    async_add_entities(entities)


class CommuteSensor(CoordinatorEntity[StravaCommuteCoordinator], SensorEntity):
    """One per-athlete commute sensor."""

    _attr_has_entity_name = True
    entity_description: CommuteSensorDescription

    def __init__(
        self,
        coordinator: StravaCommuteCoordinator,
        description: CommuteSensorDescription,
        currency: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.athlete_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.athlete_id))},
            name=coordinator.athlete_name,
            manufacturer="Strava",
            model="Athlete",
        )
        if description.key == "money_saved":
            self._attr_native_unit_of_measurement = currency

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


def _build_comparison_sensors(
    coordinators: list[StravaCommuteCoordinator],
) -> list[SensorEntity]:
    """Build household-level comparison sensors."""
    return [
        LeaderSensor(coordinators),
        MarginKmSensor(coordinators),
        MarginPercentSensor(coordinators),
        WeeklyWinnerSensor(coordinators, index=0),
        WeeklyWinnerSensor(coordinators, index=1),
    ]


class _ComparisonBase(SensorEntity):
    """Shared wiring for comparison sensors — listens to all coordinators."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinators: list[StravaCommuteCoordinator]) -> None:
        self._coordinators = coordinators
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "household")},
            name="Commute Leaderboard",
            manufacturer="Strava Commute Leaderboard",
        )

    async def async_added_to_hass(self) -> None:
        for coord in self._coordinators:
            self.async_on_remove(coord.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return any(c.data is not None for c in self._coordinators)

    def _stats(self) -> list[CommuteStats]:
        return [c.data for c in self._coordinators if c.data is not None]


class LeaderSensor(_ComparisonBase):
    _attr_translation_key = "leader"
    _attr_icon = "mdi:trophy-variant"

    def __init__(self, coordinators: list[StravaCommuteCoordinator]) -> None:
        super().__init__(coordinators)
        self._attr_unique_id = f"{DOMAIN}_leader"

    @property
    def native_value(self) -> str | None:
        stats = self._stats()
        if not stats:
            return None
        leader = max(stats, key=lambda s: s.distance_km_ytd)
        return leader.athlete_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            s.athlete_name: s.distance_km_ytd for s in self._stats()
        }


class MarginKmSensor(_ComparisonBase):
    _attr_translation_key = "margin_km"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinators: list[StravaCommuteCoordinator]) -> None:
        super().__init__(coordinators)
        self._attr_unique_id = f"{DOMAIN}_margin_km"

    @property
    def native_value(self) -> float | None:
        stats = self._stats()
        if len(stats) < 2:
            return None
        sorted_stats = sorted(stats, key=lambda s: s.distance_km_ytd, reverse=True)
        return round(sorted_stats[0].distance_km_ytd - sorted_stats[1].distance_km_ytd, 1)


class MarginPercentSensor(_ComparisonBase):
    _attr_translation_key = "margin_percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinators: list[StravaCommuteCoordinator]) -> None:
        super().__init__(coordinators)
        self._attr_unique_id = f"{DOMAIN}_margin_percent"

    @property
    def native_value(self) -> float | None:
        stats = self._stats()
        if len(stats) < 2:
            return None
        sorted_stats = sorted(stats, key=lambda s: s.distance_km_ytd, reverse=True)
        leader = sorted_stats[0].distance_km_ytd
        second = sorted_stats[1].distance_km_ytd
        if second <= 0:
            return None
        return round(((leader - second) / second) * 100, 1)


class WeeklyWinnerSensor(_ComparisonBase):
    _attr_icon = "mdi:medal"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = False

    def __init__(
        self, coordinators: list[StravaCommuteCoordinator], index: int
    ) -> None:
        super().__init__(coordinators)
        self._index = index
        athlete = coordinators[index]
        self._attr_unique_id = f"{DOMAIN}_weekly_wins_{athlete.athlete_id}"
        self._attr_name = f"Weekly wins {athlete.athlete_name}"

    @property
    def native_value(self) -> int | None:
        stats = self._stats()
        if len(stats) < 2:
            return None
        week_keys = set()
        for s in stats:
            week_keys.update(s.per_week_km.keys())
        wins = 0
        target_name = self._coordinators[self._index].athlete_name
        for week in week_keys:
            totals = {s.athlete_name: s.per_week_km.get(week, 0.0) for s in stats}
            winner = max(totals, key=totals.get)
            if totals[winner] > 0 and winner == target_name:
                wins += 1
        return wins
