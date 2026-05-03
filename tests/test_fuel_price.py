"""Unit tests for the fuel_price module.

The pure parsers (`_q8_diesel_prices`, `_shell_diesel_prices`) cover most of
the risky logic — outlier filtering, type coercion, defensive shape handling.
A small set of orchestration tests with a fake aiohttp session verifies the
Q8 → Shell fallback flow.
"""
from __future__ import annotations

import pytest

from fuel_price import (
    FuelPriceResult,
    _q8_diesel_prices,
    _shell_diesel_prices,
    fetch_diesel_price,
)


# ---------------- Q8 parser ----------------

def test_q8_extracts_diesel_prices_from_wrapped_payload():
    payload = {
        "data": {
            "stationsPrices": [
                {"products": [
                    {"productId": "6", "price": 13.49},
                    {"productId": "5", "price": 12.99},  # not diesel
                ]},
                {"products": [{"productId": "6", "price": 13.59}]},
            ]
        },
        "success": True,
    }
    assert sorted(_q8_diesel_prices(payload)) == [13.49, 13.59]


def test_q8_filters_out_of_range_prices():
    payload = {"data": {"stationsPrices": [
        {"products": [
            {"productId": "6", "price": 0.0},    # below floor
            {"productId": "6", "price": 13.49},  # ok
            {"productId": "6", "price": 99.0},   # above ceiling
        ]},
    ]}}
    assert _q8_diesel_prices(payload) == [13.49]


def test_q8_skips_non_diesel_products():
    payload = {"data": {"stationsPrices": [
        {"products": [
            {"productId": "14", "price": 11.29},
            {"productId": "1", "price": 14.99},
        ]},
    ]}}
    assert _q8_diesel_prices(payload) == []


def test_q8_handles_string_prices():
    payload = {"data": {"stationsPrices": [
        {"products": [{"productId": "6", "price": "13.49"}]},
    ]}}
    assert _q8_diesel_prices(payload) == [13.49]


def test_q8_handles_unparseable_prices():
    payload = {"data": {"stationsPrices": [
        {"products": [
            {"productId": "6", "price": "not a number"},
            {"productId": "6", "price": None},
            {"productId": "6"},  # missing entirely
            {"productId": "6", "price": 13.49},
        ]},
    ]}}
    assert _q8_diesel_prices(payload) == [13.49]


def test_q8_handles_top_level_list():
    payload = [{"products": [{"productId": "6", "price": 13.49}]}]
    assert _q8_diesel_prices(payload) == [13.49]


@pytest.mark.parametrize("payload", [None, [], {}, "nope", 42, {"data": "wrong"}])
def test_q8_handles_garbage_input(payload):
    assert _q8_diesel_prices(payload) == []


def test_q8_tolerates_non_dict_stations_and_products():
    payload = {"data": {"stationsPrices": [
        "broken",
        None,
        {"products": ["not a dict", {"productId": "6", "price": 13.49}]},
    ]}}
    assert _q8_diesel_prices(payload) == [13.49]


# ---------------- Shell parser ----------------

def test_shell_extracts_diesel_prices():
    payload = [
        {"prices": [
            {"fuelType": "Autodiesel", "price": "13.49"},
            {"fuelType": "Gasoline", "price": "14.99"},
        ]},
        {"prices": [{"fuelType": "Autodiesel", "price": "13.59"}]},
    ]
    assert sorted(_shell_diesel_prices(payload)) == [13.49, 13.59]


def test_shell_fuel_type_match_is_case_insensitive():
    payload = [{"prices": [
        {"fuelType": "AUTODIESEL", "price": "13.49"},
        {"fuelType": "autodiesel", "price": "13.59"},
    ]}]
    assert sorted(_shell_diesel_prices(payload)) == [13.49, 13.59]


def test_shell_filters_outliers():
    payload = [{"prices": [
        {"fuelType": "Autodiesel", "price": "0.5"},
        {"fuelType": "Autodiesel", "price": "13.49"},
        {"fuelType": "Autodiesel", "price": "999.0"},
    ]}]
    assert _shell_diesel_prices(payload) == [13.49]


@pytest.mark.parametrize("payload", [None, {}, "nope", 42])
def test_shell_handles_garbage_input(payload):
    assert _shell_diesel_prices(payload) == []


# ---------------- Orchestration ----------------

class _FakeResponse:
    def __init__(self, json_data, raise_exc=None):
        self._json = json_data
        self._raise_exc = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    async def json(self):
        return self._json


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requested_urls = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        if not self._responses:
            raise AssertionError(f"Unexpected extra request to {url}")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _FakeResponse(nxt)


@pytest.mark.asyncio
async def test_fetch_diesel_price_uses_q8_when_available():
    q8_payload = {"data": {"stationsPrices": [
        {"products": [{"productId": "6", "price": 13.40}]},
        {"products": [{"productId": "6", "price": 13.50}]},
        {"products": [{"productId": "6", "price": 13.60}]},
    ]}}
    session = _FakeSession([q8_payload])

    result = await fetch_diesel_price(session)

    assert isinstance(result, FuelPriceResult)
    assert result.source == "q8"
    assert result.price_per_l == 13.50  # median
    assert result.station_count == 3
    assert len(session.requested_urls) == 1


@pytest.mark.asyncio
async def test_fetch_diesel_price_falls_back_to_shell_when_q8_empty():
    q8_empty = {"data": {"stationsPrices": []}}
    shell_payload = [
        {"prices": [{"fuelType": "Autodiesel", "price": "13.10"}]},
        {"prices": [{"fuelType": "Autodiesel", "price": "13.30"}]},
    ]
    session = _FakeSession([q8_empty, shell_payload])

    result = await fetch_diesel_price(session)

    assert result is not None
    assert result.source == "shell"
    assert result.price_per_l == 13.20  # median of two
    assert len(session.requested_urls) == 2


@pytest.mark.asyncio
async def test_fetch_diesel_price_returns_none_when_both_sources_fail():
    session = _FakeSession([{"data": {"stationsPrices": []}}, []])
    assert await fetch_diesel_price(session) is None
