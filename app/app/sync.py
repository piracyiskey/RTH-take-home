"""Background synchronization service for Helpdesk API data."""

import asyncio
import logging
from typing import Any

import httpx

from app.business_hours import parse_holiday_date
from app.helpdesk import HelpdeskClient
from app.models import EventItem, RequestItem, Site, Staff
from app.store import store

logger = logging.getLogger("sync")


async def initial_metadata_sync(client: HelpdeskClient) -> None:
    """Fetch sites, holidays, and staff members."""
    # 1. Fetch sites
    sites_res = await client.async_get("/v1/sites")
    for site_data in sites_res.get("data", []):
        site = Site.from_dict(site_data)
        store.upsert_site(site)

        # Fetch holidays for site
        holidays_res = await client.async_get(f"/v1/sites/{site.id}/holidays")
        holiday_dates = {
            parse_holiday_date(h["date"])
            for h in holidays_res.get("data", [])
            if "date" in h
        }
        store.set_holidays(site.id, holiday_dates)

    # 2. Fetch staff
    staff_res = await client.async_get("/v1/staff")
    for s_data in staff_res.get("data", []):
        store.upsert_staff(Staff.from_dict(s_data))


def apply_change_item(item: dict[str, Any]) -> None:
    """Apply a single change item from /v1/changes to the in-memory store."""
    if "request" in item and item["request"]:
        store.upsert_request(RequestItem.from_dict(item["request"]))
    elif "event" in item and item["event"]:
        req_id = item.get("request_id") or item["event"].get("request_id")
        store.upsert_event(EventItem.from_dict(item["event"], request_id=req_id))
    elif "staff" in item and item["staff"]:
        store.upsert_staff(Staff.from_dict(item["staff"]))


async def sync_changes_feed(client: HelpdeskClient) -> None:
    """Consume /v1/changes until up to date."""
    cursor = store.last_cursor
    while True:
        params: dict[str, Any] = {"limit": 500}
        if cursor:
            params["cursor"] = cursor

        try:
            res = await client.async_get("/v1/changes", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 410:
                # Cursor expired after 15 minutes; restart from beginning
                cursor = None
                store.last_cursor = None
                continue
            raise

        data = res.get("data", [])
        for item in data:
            apply_change_item(item)

        cursor = res.get("next_cursor")
        store.last_cursor = cursor
        has_more = res.get("has_more", False)

        if not has_more:
            if not store.ready:
                store.ready = True
                logger.info("Initial change feed sync complete. App is ready.")
            break

        await asyncio.sleep(0.001)


async def run_sync_loop() -> None:
    """Continuous background loop for initial load and ongoing live updates."""
    client = HelpdeskClient()
    try:
        await initial_metadata_sync(client)
    except Exception as e:
        logger.error(f"Failed initial metadata sync: {e}")

    while True:
        try:
            await sync_changes_feed(client)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in sync loop: {e}")

        # Poll every 10 seconds for live updates (Level 3 requirement: updates within 60s)
        await asyncio.sleep(10)

