"""Strava REST API client."""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

MAX_PER_PAGE = 200


class StravaApiError(Exception):
    """Raised when the Strava API returns an error we cannot recover from."""


class StravaRateLimitError(StravaApiError):
    """Raised when Strava returns HTTP 429."""


class StravaApi:
    """Thin async wrapper over the Strava v3 REST API."""

    def __init__(self, session: ClientSession, access_token_getter) -> None:
        self._session = session
        self._get_token = access_token_getter

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{API_BASE}{path}"
        async with self._session.get(url, headers=headers, params=params) as resp:
            if resp.status == 429:
                raise StravaRateLimitError("Strava rate limit exceeded")
            try:
                resp.raise_for_status()
            except ClientResponseError as err:
                body = await resp.text()
                raise StravaApiError(f"{err.status} {err.message}: {body}") from err
            return await resp.json()

    async def get_athlete(self) -> dict[str, Any]:
        """Return the authenticated athlete profile."""
        return await self._get("/athlete")

    async def get_activities_since(self, after_epoch: int) -> list[dict[str, Any]]:
        """Return all activities newer than the given epoch timestamp.

        Paginates until an empty page is returned.
        """
        activities: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = await self._get(
                "/athlete/activities",
                params={
                    "after": after_epoch,
                    "page": page,
                    "per_page": MAX_PER_PAGE,
                },
            )
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < MAX_PER_PAGE:
                break
            page += 1
        return activities
