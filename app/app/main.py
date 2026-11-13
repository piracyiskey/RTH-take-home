import asyncio
import bisect
import csv
import io
from contextlib import asynccontextmanager
from datetime import date
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.browse import get_sort_tuple, make_cursor, parse_cursor
from app.sla import compute_sla_report, process_request_sla
from app.store import store
from app.sync import run_sync_loop

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = None
    if not os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("DISABLE_SYNC") != "1":
        sync_task = asyncio.create_task(run_sync_loop())
    yield
    if sync_task and not sync_task.done():
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Response-time report", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/ready")
def ready():
    if store.ready:
        return {"ready": True}
    return JSONResponse(status_code=503, content={"ready": False})


@app.get("/api/sla-report")
def sla_report(request: Request):
    if not store.ready:
        return JSONResponse(status_code=503, content={"error": "App is syncing data, not ready yet"})

    from_date = request.query_params.get("from")
    to_date = request.query_params.get("to")

    if not from_date or not to_date:
        return JSONResponse(status_code=400, content={"error": "Missing required 'from' or 'to' query parameter"})

    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Parameters 'from' and 'to' must be formatted as YYYY-MM-DD"})

    if d_from > d_to:
        return JSONResponse(status_code=400, content={"error": "'from' date cannot be after 'to' date"})

    report = compute_sla_report(store, from_date, to_date)
    return report


def _parse_browse_params(params) -> tuple[JSONResponse | None, dict[str, Any]]:
    """Parse and validate shared query params for /api/requests and /api/requests.csv.

    Returns (error_response, parsed_dict). If error_response is not None, return it immediately.
    """
    from_date = params.get("from")
    to_date = params.get("to")

    if not from_date or not to_date:
        return JSONResponse(status_code=400, content={"error": "Missing required 'from' or 'to' query parameter"}), {}

    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Parameters 'from' and 'to' must be formatted as YYYY-MM-DD"}), {}

    if d_from > d_to:
        return JSONResponse(status_code=400, content={"error": "'from' date cannot be after 'to' date"}), {}

    site_id_val = None
    if "site_id" in params:
        try:
            site_id_val = int(params["site_id"])
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "site_id must be an integer"}), {}

    responder_id_val = None
    if "responder_id" in params:
        try:
            responder_id_val = int(params["responder_id"])
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "responder_id must be an integer"}), {}

    late_val = None
    if "late" in params:
        raw_late = params["late"].lower()
        if raw_late == "true":
            late_val = True
        elif raw_late == "false":
            late_val = False
        else:
            return JSONResponse(status_code=400, content={"error": "late must be 'true' or 'false'"}), {}

    within_target_val = None
    if "within_target" in params:
        raw_target = params["within_target"].lower()
        if raw_target == "true":
            within_target_val = True
        elif raw_target == "false":
            within_target_val = False
        else:
            return JSONResponse(status_code=400, content={"error": "within_target must be 'true' or 'false'"}), {}

    sort_type = params.get("sort", "id")
    if sort_type not in ("id", "-id", "response_business_minutes", "-response_business_minutes"):
        return JSONResponse(status_code=400, content={"error": f"Invalid sort parameter: {sort_type}"}), {}

    return None, {
        "from_date": from_date, "to_date": to_date,
        "site_id": site_id_val, "responder_id": responder_id_val,
        "late": late_val, "within_target": within_target_val,
        "sort": sort_type,
    }


def _get_filtered_sorted_rows(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all SLA rows matching the parsed browse parameters, sorted."""
    eligible = store.get_eligible_requests(p["from_date"], p["to_date"])
    filtered_rows = []

    for req in eligible:
        if p["site_id"] is not None and req.site_id != p["site_id"]:
            continue

        events = store.get_events(req.id)
        row = process_request_sla(req, events, store)

        if p["responder_id"] is not None and row["responder_id"] != p["responder_id"]:
            continue
        if p["late"] is not None and row["completed_late"] is not p["late"]:
            continue
        if p["within_target"] is not None and row["within_target"] is not p["within_target"]:
            continue

        filtered_rows.append(row)

    return sorted(filtered_rows, key=lambda r: get_sort_tuple(r, p["sort"]))


@app.get("/api/requests")
def browse(request: Request):
    if not store.ready:
        return JSONResponse(status_code=503, content={"error": "App is syncing data, not ready yet"})

    params = request.query_params
    err, p = _parse_browse_params(params)
    if err:
        return err

    # Limit parameter
    limit_str = params.get("limit", "50")
    try:
        limit = int(limit_str)
        if limit < 1 or limit > 200:
            return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 200"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "limit must be an integer"})

    # Cursor parameter
    cursor_str = params.get("cursor")
    cursor_tuple = None
    if cursor_str:
        try:
            cursor_tuple = tuple(parse_cursor(cursor_str, p["sort"]))
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    sorted_rows = _get_filtered_sorted_rows(p)
    keys = [get_sort_tuple(r, p["sort"]) for r in sorted_rows]

    start_idx = 0
    if cursor_tuple is not None:
        start_idx = bisect.bisect_right(keys, cursor_tuple)

    page = sorted_rows[start_idx : start_idx + limit]

    next_cursor = None
    if start_idx + limit < len(sorted_rows) and len(page) > 0:
        last_item_key = list(get_sort_tuple(page[-1], p["sort"]))
        next_cursor = make_cursor(p["sort"], last_item_key)

    return {"data": page, "next_cursor": next_cursor}


CSV_HEADER = ["id", "site_id", "responder_id", "responder", "response_business_minutes", "within_target", "completed_late"]


def _csv_value(val: Any) -> str:
    """Format a value for CSV output: booleans as true/false, None as empty string."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


@app.get("/api/requests.csv")
def browse_csv(request: Request):
    if not store.ready:
        return JSONResponse(status_code=503, content={"error": "App is syncing data, not ready yet"})

    err, p = _parse_browse_params(request.query_params)
    if err:
        return err

    sorted_rows = _get_filtered_sorted_rows(p)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for row in sorted_rows:
        writer.writerow([_csv_value(row.get(col)) for col in CSV_HEADER])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=requests.csv"},
    )
