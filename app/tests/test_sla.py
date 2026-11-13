"""Comprehensive tests for SLA calculation rules and report endpoint."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models import EventItem, RequestItem, Site, Staff
from app.store import DataStore, store


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the global store before each test."""
    store.sites.clear()
    store.holidays.clear()
    store.staff.clear()
    store.requests.clear()
    store.events.clear()
    store.ready = True

    # Setup Singapore site
    sg_site = Site(
        id=11,
        name="Robusttechhouse Tower Singapore",
        timezone="Asia/Singapore",
        business_hours={
            "mon": {"open": "08:00", "close": "18:00"},
            "tue": {"open": "08:00", "close": "18:00"},
            "wed": {"open": "08:00", "close": "18:00"},
            "thu": {"open": "08:00", "close": "18:00"},
            "fri": {"open": "08:00", "close": "18:00"},
            "sat": None,
            "sun": None,
        },
    )
    store.upsert_site(sg_site)
    store.upsert_staff(Staff(id=304, name="Benjamin Tan"))
    store.upsert_staff(Staff(id=347, name="Elaine Ng"))
    yield store


client = TestClient(app)


def test_sla_report_parameter_validation():
    # Missing parameters
    res = client.get("/api/sla-report")
    assert res.status_code == 400

    res = client.get("/api/sla-report?from=2026-10-01")
    assert res.status_code == 400

    # Invalid format
    res = client.get("/api/sla-report?from=01-10-2026&to=2026-10-31")
    assert res.status_code == 400

    # from after to
    res = client.get("/api/sla-report?from=2026-10-31&to=2026-10-01")
    assert res.status_code == 400


def test_rule_1_eligibility_and_site_local_date():
    # Singapore is UTC+8
    # Request created at 2026-09-30 22:00:00 UTC -> 2026-10-01 06:00:00 SGT (in October!)
    store.upsert_request(
        RequestItem(
            id=101,
            site_id=11,
            status="pending",
            priority="High",
            created_at="2026-09-30T22:00:00Z",
        )
    )

    # Excluded: canceled
    store.upsert_request(
        RequestItem(
            id=102,
            site_id=11,
            status="canceled",
            priority="High",
            created_at="2026-10-05T02:00:00Z",
        )
    )

    # Excluded: deleted_at set
    store.upsert_request(
        RequestItem(
            id=103,
            site_id=11,
            status="complete",
            priority="High",
            created_at="2026-10-05T02:00:00Z",
            deleted_at="2026-10-06T02:00:00Z",
        )
    )

    # Excluded: merged_into_id set
    store.upsert_request(
        RequestItem(
            id=104,
            site_id=11,
            status="complete",
            priority="High",
            created_at="2026-10-05T02:00:00Z",
            merged_into_id=101,
        )
    )

    res = client.get("/api/sla-report?from=2026-10-01&to=2026-10-31")
    assert res.status_code == 200
    data = res.json()
    assert len(data["requests"]) == 1
    assert data["requests"][0]["id"] == 101


def test_rule_2_and_3_reverts_and_staff_name():
    # Request created Monday 2026-10-05 08:00 SGT (00:00 UTC)
    store.upsert_request(
        RequestItem(
            id=201,
            site_id=11,
            status="complete",
            priority="High",
            created_at="2026-10-05T00:00:00Z",
        )
    )

    # Event 1: System event (actor_id=None) -> should be ignored for responder
    store.upsert_event(
        EventItem(
            id=501,
            request_id=201,
            status="pending",
            at=1791158400,  # 00:00 UTC
            actor_id=None,
            actor_name="System",
        )
    )

    # Event 2: Processing by Elaine Ng at 00:30 UTC
    store.upsert_event(
        EventItem(
            id=502,
            request_id=201,
            status="processing",
            at=1791160200,  # 00:30 UTC
            actor_id=347,
            actor_name="Old Elaine Name",
        )
    )

    # Event 3: Reverts event 2! Both event 2 and event 3 must be ignored
    store.upsert_event(
        EventItem(
            id=503,
            request_id=201,
            status="pending",
            at=1791160500,
            actor_id=347,
            reverts_id=502,
        )
    )

    # Event 4: Processing by Benjamin Tan at 00:45 UTC
    store.upsert_event(
        EventItem(
            id=504,
            request_id=201,
            status="processing",
            at=1791161100,  # 00:45 UTC (45 min after creation)
            actor_id=304,
            actor_name="Ben (Old)",
            due_at="05/10/2026 12:00",
        )
    )

    # Event 5: Completed at 02:00 UTC (10:00 SGT) -> before 12:00 SGT deadline
    store.upsert_event(
        EventItem(
            id=505,
            request_id=201,
            status="complete",
            at=1791165600,
            actor_id=304,
        )
    )

    res = client.get("/api/sla-report?from=2026-10-01&to=2026-10-31")
    assert res.status_code == 200
    data = res.json()
    req = data["requests"][0]

    # Rule 3: Responder is Benjamin Tan (from staff table, not event actor_name)
    assert req["responder_id"] == 304
    assert req["responder"] == "Benjamin Tan"

    # Rule 4 & 5: Response time is 45 minutes, High priority target <= 60 mins -> within_target=True
    assert req["response_business_minutes"] == 45
    assert req["within_target"] is True

    # Rule 6: Completed at 10:00 SGT, deadline was 12:00 SGT -> completed_late=False
    assert req["completed_late"] is False


def test_rule_6_completed_late():
    store.upsert_request(
        RequestItem(
            id=301,
            site_id=11,
            status="complete",
            priority="Low",
            created_at="2026-10-05T00:00:00Z",
        )
    )

    # Deadline set to 10:00 SGT (02:00 UTC)
    store.upsert_event(
        EventItem(
            id=601,
            request_id=301,
            status="processing",
            at=1791158400,
            actor_id=304,
            due_at="05/10/2026 10:00",
        )
    )

    # Completed at 11:00 SGT (03:00 UTC, Unix 1791169200) -> after 10:00 deadline!
    store.upsert_event(
        EventItem(
            id=602,
            request_id=301,
            status="complete",
            at=1791169200,
            actor_id=304,
        )
    )

    res = client.get("/api/sla-report?from=2026-10-01&to=2026-10-31")
    assert res.status_code == 200
    req = res.json()["requests"][0]
    assert req["completed_late"] is True


def test_rule_7_null_semantics():
    # Request never processed and never completed
    store.upsert_request(
        RequestItem(
            id=401,
            site_id=11,
            status="pending",
            priority="Medium",
            created_at="2026-10-05T00:00:00Z",
        )
    )

    res = client.get("/api/sla-report?from=2026-10-01&to=2026-10-31")
    assert res.status_code == 200
    req = res.json()["requests"][0]
    assert req["responder_id"] is None
    assert req["responder"] is None
    assert req["response_business_minutes"] is None
    assert req["within_target"] is None
    assert req["completed_late"] is None

    # Responders aggregation should be empty since no responder handled it
    assert res.json()["responders"] == []

