"""Tests for GET /api/requests (Level 4 Browse endpoint)."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models import EventItem, RequestItem, Site, Staff
from app.store import store

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_browse_store():
    store.sites.clear()
    store.holidays.clear()
    store.staff.clear()
    store.requests.clear()
    store.events.clear()
    store.ready = True

    # Setup Singapore site (id=11) and Sydney site (id=12)
    sg_site = Site(
        id=11,
        name="Singapore Tower",
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
    syd_site = Site(
        id=12,
        name="Sydney Court",
        timezone="Australia/Sydney",
        business_hours={
            "mon": {"open": "07:30", "close": "17:00"},
            "tue": {"open": "07:30", "close": "17:00"},
            "wed": {"open": "07:30", "close": "17:00"},
            "thu": {"open": "07:30", "close": "17:00"},
            "fri": {"open": "07:30", "close": "17:00"},
            "sat": None,
            "sun": None,
        },
    )
    store.upsert_site(sg_site)
    store.upsert_site(syd_site)
    store.upsert_staff(Staff(id=301, name="Alice"))
    store.upsert_staff(Staff(id=302, name="Bob"))

    # Seed 5 requests with various combinations
    # Req 1: site 11, responder Alice, 30 mins, within target, not late
    store.upsert_request(
        RequestItem(id=1, site_id=11, status="complete", priority="High", created_at="2026-10-05T00:00:00Z")
    )
    store.upsert_event(
        EventItem(id=101, request_id=1, status="processing", at=1791158400 + 1800, actor_id=301, due_at="05/10/2026 18:00")
    )
    store.upsert_event(
        EventItem(id=102, request_id=1, status="complete", at=1791158400 + 3600, actor_id=301)
    )

    # Req 2: site 11, responder Bob, 90 mins (High priority -> not within target), late
    store.upsert_request(
        RequestItem(id=2, site_id=11, status="complete", priority="High", created_at="2026-10-05T00:00:00Z")
    )
    store.upsert_event(
        EventItem(id=201, request_id=2, status="processing", at=1791158400 + 5400, actor_id=302, due_at="05/10/2026 09:00")
    )
    store.upsert_event(
        EventItem(id=202, request_id=2, status="complete", at=1791158400 + 7200, actor_id=302)
    )

    # Req 3: site 12, responder Alice, 20 mins, within target, not late
    store.upsert_request(
        RequestItem(id=3, site_id=12, status="complete", priority="Medium", created_at="2026-10-05T00:00:00Z")
    )
    store.upsert_event(
        EventItem(id=301, request_id=3, status="processing", at=1791158400 + 1200, actor_id=301, due_at="05/10/2026 18:00")
    )
    store.upsert_event(
        EventItem(id=302, request_id=3, status="complete", at=1791158400 + 2400, actor_id=301)
    )

    # Req 4: site 12, unresponded (null responder, null mins)
    store.upsert_request(
        RequestItem(id=4, site_id=12, status="pending", priority="Low", created_at="2026-10-05T00:00:00Z")
    )

    # Req 5: site 11, responder Bob, 15 mins, within target
    store.upsert_request(
        RequestItem(id=5, site_id=11, status="complete", priority="Low", created_at="2026-10-05T00:00:00Z")
    )
    store.upsert_event(
        EventItem(id=501, request_id=5, status="processing", at=1791158400 + 900, actor_id=302, due_at="05/10/2026 18:00")
    )
    store.upsert_event(
        EventItem(id=502, request_id=5, status="complete", at=1791158400 + 1800, actor_id=302)
    )


def test_browse_validation():
    # Missing from/to
    assert client.get("/api/requests").status_code == 400
    assert client.get("/api/requests?from=2026-10-01").status_code == 400

    # Invalid integers or booleans
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&site_id=abc").status_code == 400
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&late=maybe").status_code == 400
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&within_target=foo").status_code == 400
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&sort=bad_sort").status_code == 400
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&limit=0").status_code == 400
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&limit=201").status_code == 400

    # Forged / invalid cursor
    assert client.get("/api/requests?from=2026-10-01&to=2026-10-31&cursor=fake-cursor").status_code == 400


def test_browse_filtering():
    # Filter site_id=12 -> req 3 and 4
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&site_id=12")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [3, 4]

    # Filter responder_id=301 (Alice) -> req 1 and 3
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&responder_id=301")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [1, 3]

    # Filter late=true -> only req 2
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&late=true")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [2]

    # Filter within_target=false -> only req 2
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&within_target=false")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [2]


def test_browse_sorting_and_nulls_last():
    # Default sort is id ascending
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31")
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [1, 2, 3, 4, 5]

    # Sort by -id
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&sort=-id")
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [5, 4, 3, 2, 1]

    # Sort by response_business_minutes ascending (nulls last)
    # Req 5: 15m, Req 3: 20m, Req 1: 30m, Req 2: 90m, Req 4: None
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&sort=response_business_minutes")
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [5, 3, 1, 2, 4]

    # Sort by -response_business_minutes (nulls last)
    # Req 2: 90m, Req 1: 30m, Req 3: 20m, Req 5: 15m, Req 4: None
    res = client.get("/api/requests?from=2026-10-01&to=2026-10-31&sort=-response_business_minutes")
    ids = [r["id"] for r in res.json()["data"]]
    assert ids == [2, 1, 3, 5, 4]


def test_browse_cursor_pagination_walk():
    # Page size 2 across 5 items -> 3 pages (2, 2, 1)
    all_seen = []
    cursor = None

    while True:
        url = "/api/requests?from=2026-10-01&to=2026-10-31&limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        res = client.get(url)
        assert res.status_code == 200
        body = res.json()
        page_items = body["data"]
        all_seen.extend([r["id"] for r in page_items])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    # Every item visited exactly once in order
    assert all_seen == [1, 2, 3, 4, 5]

