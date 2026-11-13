"""In-memory data store for sites, holidays, staff, requests, and events."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import EventItem, RequestItem, Site, Staff


class DataStore:
    def __init__(self):
        self.sites: dict[int, Site] = {}
        self.holidays: dict[int, set[str]] = {}  # site_id -> set of "YYYY-MM-DD"
        self.staff: dict[int, Staff] = {}
        self.requests: dict[int, RequestItem] = {}
        self.events: dict[int, dict[int, EventItem]] = {}  # req_id -> {event_id: EventItem}
        self.ready: bool = False
        self.last_cursor: str | None = None

    def upsert_site(self, site: Site) -> None:
        self.sites[site.id] = site

    def set_holidays(self, site_id: int, holidays: set[str]) -> None:
        self.holidays[site_id] = holidays

    def upsert_staff(self, staff: Staff) -> None:
        self.staff[staff.id] = staff

    def upsert_request(self, req: RequestItem) -> None:
        self.requests[req.id] = req

    def upsert_event(self, event: EventItem) -> None:
        if event.request_id not in self.events:
            self.events[event.request_id] = {}
        self.events[event.request_id][event.id] = event

    def get_events(self, request_id: int) -> list[EventItem]:
        return list(self.events.get(request_id, {}).values())

    def get_eligible_requests(self, from_date_str: str, to_date_str: str) -> list[RequestItem]:
        """Filter requests matching Rule 1:
        - created_at converted to site-local date in [from_date_str, to_date_str]
        - status != 'canceled'
        - deleted_at is None
        - merged_into_id is None
        """
        result = []
        for req in self.requests.values():
            if req.status == "canceled" or req.deleted_at is not None or req.merged_into_id is not None:
                continue

            site = self.sites.get(req.site_id)
            if not site:
                continue

            created_utc = datetime.fromisoformat(req.created_at.replace("Z", "+00:00"))
            tz = ZoneInfo(site.timezone)
            local_date = created_utc.astimezone(tz).strftime("%Y-%m-%d")

            if from_date_str <= local_date <= to_date_str:
                result.append(req)

        return result


# Global in-memory store instance
store = DataStore()

