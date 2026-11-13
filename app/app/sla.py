"""SLA report calculation implementing all 7 rules."""

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.business_hours import calc_business_minutes
from app.models import EventItem, RequestItem
from app.store import DataStore


def parse_deadline(due_at_str: str, tz_name: str) -> float:
    """Parse 'DD/MM/YYYY HH:mm' wall-clock string in site timezone to Unix timestamp."""
    dt_naive = datetime.strptime(due_at_str.strip(), "%d/%m/%Y %H:%M")
    tz = ZoneInfo(tz_name)
    dt_aware = dt_naive.replace(tzinfo=tz)
    return dt_aware.timestamp()


def process_request_sla(
    req: RequestItem,
    events: list[EventItem],
    store: DataStore,
) -> dict[str, Any]:
    """Apply Rules 2 through 7 to compute SLA metrics for a single request."""
    # Rule 2: Undone events (reverts_id)
    reverted_ids = {e.reverts_id for e in events if e.reverts_id is not None}
    reverting_ids = {e.id for e in events if e.reverts_id is not None}
    ignored_ids = reverted_ids | reverting_ids
    valid_events = [e for e in events if e.id not in ignored_ids]

    site = store.sites.get(req.site_id)
    holidays = store.holidays.get(req.site_id, set())

    # Rule 3: First response and responder
    # Earliest event by `at` with status "processing" and non-null actor_id
    processing_events = [
        e for e in valid_events
        if e.status == "processing" and e.actor_id is not None
    ]

    responder_id: int | None = None
    responder_name: str | None = None
    response_business_minutes: int | None = None
    within_target: bool | None = None

    if processing_events:
        first_resp = min(processing_events, key=lambda e: (e.at, e.id))
        responder_id = first_resp.actor_id

        # Name from current /v1/staff
        staff_member = store.staff.get(responder_id)
        responder_name = staff_member.name if staff_member else first_resp.actor_name

        # Rule 4: Response minutes
        if site:
            start_utc = datetime.fromisoformat(req.created_at.replace("Z", "+00:00"))
            end_utc = datetime.fromtimestamp(first_resp.at, tz=timezone.utc)
            response_business_minutes = calc_business_minutes(site, holidays, start_utc, end_utc)

            # Rule 5: Within target
            # <= 60 for High, 240 for Medium, 480 for Low or null
            if req.priority == "High":
                within_target = response_business_minutes <= 60
            elif req.priority == "Medium":
                within_target = response_business_minutes <= 240
            else:
                within_target = response_business_minutes <= 480

    # Rule 6: Completed late
    # The last event with status "complete"
    complete_events = [e for e in valid_events if e.status == "complete"]
    # Latest event that has due_at
    deadline_events = [
        e for e in valid_events
        if e.due_at is not None and e.due_at.strip() != ""
    ]

    completed_late: bool | None = None
    if complete_events and deadline_events and site:
        last_complete = max(complete_events, key=lambda e: (e.at, e.id))
        latest_deadline_event = max(deadline_events, key=lambda e: (e.at, e.id))
        deadline_ts = parse_deadline(latest_deadline_event.due_at, site.timezone)
        # Strictly after deadline
        completed_late = last_complete.at > deadline_ts

    return {
        "id": req.id,
        "site_id": req.site_id,
        "responder_id": responder_id,
        "responder": responder_name,
        "response_business_minutes": response_business_minutes,
        "within_target": within_target,
        "completed_late": completed_late,
    }


def compute_sla_report(
    store: DataStore,
    from_date_str: str,
    to_date_str: str,
) -> dict[str, Any]:
    """Compute the full SLA report for the date range [from_date, to_date]."""
    # Rule 1: Which requests count
    eligible_requests = store.get_eligible_requests(from_date_str, to_date_str)

    processed_requests = []
    responders_map: dict[int, dict[str, Any]] = {}

    for req in eligible_requests:
        events = store.get_events(req.id)
        row = process_request_sla(req, events, store)
        processed_requests.append(row)

        resp_id = row["responder_id"]
        if resp_id is not None:
            if resp_id not in responders_map:
                responders_map[resp_id] = {
                    "id": resp_id,
                    "name": row["responder"],
                    "requests": 0,
                    "within_target": 0,
                    "completed_late": 0,
                }
            r_stat = responders_map[resp_id]
            r_stat["requests"] += 1
            if row["within_target"] is True:
                r_stat["within_target"] += 1
            if row["completed_late"] is True:
                r_stat["completed_late"] += 1

    # Sort requests by id ascending for determinism
    processed_requests.sort(key=lambda r: r["id"])
    responders_list = sorted(responders_map.values(), key=lambda r: r["id"])

    return {
        "from": from_date_str,
        "to": to_date_str,
        "requests": processed_requests,
        "responders": responders_list,
    }

