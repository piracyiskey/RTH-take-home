"""Browse endpoint implementation for GET /api/requests (Level 4)."""

import base64
import hashlib
import hmac
import json
from typing import Any

CURSOR_SECRET = b"sla-report-v2-secure-cursor-token"


def make_cursor(sort_type: str, cursor_tuple: list[Any]) -> str:
    """Encode a sort position into an authenticated opaque cursor token."""
    payload = json.dumps({"s": sort_type, "t": cursor_tuple}, separators=(",", ":"))
    sig = hmac.new(CURSOR_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    token_str = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(token_str.encode("utf-8")).decode("utf-8")


def parse_cursor(cursor_str: str, expected_sort: str) -> list[Any]:
    """Decode and authenticate a cursor token. Raises ValueError on any invalid or forged token."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        payload, sig = raw.rsplit("|", 1)
        expected_sig = hmac.new(CURSOR_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Forged or invalid cursor signature")

        data = json.loads(payload)
        if data.get("s") != expected_sort or not isinstance(data.get("t"), list):
            raise ValueError("Mismatched cursor sort or invalid shape")
        return data["t"]
    except Exception as e:
        raise ValueError(f"Invalid cursor: {e}") from e


def get_sort_tuple(row: dict[str, Any], sort_type: str) -> tuple:
    """Generate the comparison key tuple matching:
    - Nulls last
    - Ties broken by id ascending
    """
    row_id = row["id"]
    if sort_type == "id":
        return (row_id,)
    elif sort_type == "-id":
        return (-row_id,)
    elif sort_type == "response_business_minutes":
        val = row["response_business_minutes"]
        if val is None:
            return (1, 0, row_id)
        return (0, val, row_id)
    elif sort_type == "-response_business_minutes":
        val = row["response_business_minutes"]
        if val is None:
            return (1, 0, row_id)
        return (0, -val, row_id)
    raise ValueError(f"Unknown sort type: {sort_type}")

