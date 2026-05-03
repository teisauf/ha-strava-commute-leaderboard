"""Live diesel listepris lookup for Denmark.

Since 1 Jan 2026 every Danish fuel provider must expose a public price API.
We try Q8 first (unauthenticated, well-structured) and fall back to Shell
if Q8 is unreachable. The reported price is the median across stations,
which is robust against typos or single-station outliers.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

Q8_URL = "https://beta.q8.dk/Station/GetStationPrices?page=1&pageSize=2000"
Q8_DIESEL_PRODUCT_IDS = {"6"}

SHELL_URL = "https://shellpumpepriser.geoapp.me/v1/prices"
SHELL_DIESEL_FUEL_TYPES = {"autodiesel"}

REQUEST_TIMEOUT = ClientTimeout(total=15)
MIN_PLAUSIBLE_DKK_PER_L = 5.0
MAX_PLAUSIBLE_DKK_PER_L = 40.0


@dataclass(frozen=True)
class FuelPriceResult:
    price_per_l: float
    fetched_on: date
    source: str
    station_count: int


async def fetch_diesel_price(session: ClientSession) -> FuelPriceResult | None:
    """Return median DK diesel price (DKK/L). Tries Q8 then Shell."""
    payload = await _get_json(session, Q8_URL)
    if payload is not None:
        result = _summarize(_q8_diesel_prices(payload), "q8")
        if result is not None:
            return result
        _LOGGER.warning("Q8 returned no plausible diesel prices; trying Shell")

    payload = await _get_json(session, SHELL_URL)
    if payload is not None:
        result = _summarize(_shell_diesel_prices(payload), "shell")
        if result is not None:
            return result
        _LOGGER.warning("Shell returned no plausible diesel prices either")

    return None


async def _get_json(session: ClientSession, url: str) -> Any | None:
    try:
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.json()
    except (ClientError, asyncio.TimeoutError) as err:
        _LOGGER.warning("Fuel price fetch failed for %s: %s", url, err)
    except ValueError as err:
        _LOGGER.warning("Fuel price response was not valid JSON (%s): %s", url, err)
    return None


def _summarize(prices: list[float], source: str) -> FuelPriceResult | None:
    if not prices:
        return None
    return FuelPriceResult(
        price_per_l=round(median(prices), 2),
        fetched_on=date.today(),
        source=source,
        station_count=len(prices),
    )


def _q8_diesel_prices(payload: Any) -> list[float]:
    """Extract plausible diesel prices (DKK/L) from a Q8 API payload."""
    prices: list[float] = []
    for station in _q8_stations(payload):
        if not isinstance(station, dict):
            continue
        for product in station.get("products") or []:
            if not isinstance(product, dict):
                continue
            if str(product.get("productId")) not in Q8_DIESEL_PRODUCT_IDS:
                continue
            price = _coerce_price(product.get("price"))
            if price is not None:
                prices.append(price)
    return prices


def _shell_diesel_prices(payload: Any) -> list[float]:
    """Extract plausible diesel prices (DKK/L) from a Shell API payload."""
    prices: list[float] = []
    stations = payload if isinstance(payload, list) else []
    for station in stations:
        if not isinstance(station, dict):
            continue
        for entry in station.get("prices") or []:
            if not isinstance(entry, dict):
                continue
            fuel_type = str(entry.get("fuelType", "")).strip().lower()
            if fuel_type not in SHELL_DIESEL_FUEL_TYPES:
                continue
            price = _coerce_price(entry.get("price"))
            if price is not None:
                prices.append(price)
    return prices


def _q8_stations(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("stationsPrices", "stations", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    if isinstance(data, list):
        return data
    return []


def _coerce_price(raw: Any) -> float | None:
    """Parse a numeric price (string or float) and clamp to plausible range."""
    if raw is None:
        return None
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return None
    if MIN_PLAUSIBLE_DKK_PER_L <= price <= MAX_PLAUSIBLE_DKK_PER_L:
        return price
    return None
