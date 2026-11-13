"""Domain models for helpdesk entities."""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Site:
    id: int
    name: str
    timezone: str
    business_hours: dict[str, dict[str, str] | None]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Site":
        return cls(
            id=data["id"],
            name=data["name"],
            timezone=data["timezone"],
            business_hours=data.get("business_hours", {}),
        )


@dataclass(slots=True)
class Staff:
    id: int
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Staff":
        return cls(id=data["id"], name=data["name"])


@dataclass(slots=True)
class RequestItem:
    id: int
    site_id: int
    status: str
    priority: str | None
    created_at: str  # ISO-8601 UTC string (e.g. "2026-10-06T02:15:07Z")
    deleted_at: str | None = None
    merged_into_id: int | None = None
    ref: str | None = None
    title: str | None = None
    updated_at: str | None = None
    due_on: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RequestItem":
        return cls(
            id=data["id"],
            site_id=data["site_id"],
            status=data.get("status", "pending"),
            priority=data.get("priority"),
            created_at=data["created_at"],
            deleted_at=data.get("deleted_at"),
            merged_into_id=data.get("merged_into_id"),
            ref=data.get("ref"),
            title=data.get("title"),
            updated_at=data.get("updated_at"),
            due_on=data.get("due_on"),
        )


@dataclass(slots=True)
class EventItem:
    id: int
    request_id: int
    status: str
    at: int  # Unix epoch seconds
    actor_id: int | None = None
    actor_name: str | None = None
    due_at: str | None = None  # DD/MM/YYYY HH:mm site-local string
    note: str | None = None
    reverts_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], request_id: int | None = None) -> "EventItem":
        req_id = request_id if request_id is not None else data.get("request_id", 0)
        return cls(
            id=data["id"],
            request_id=req_id,
            status=data.get("status", ""),
            at=data["at"],
            actor_id=data.get("actor_id"),
            actor_name=data.get("actor_name"),
            due_at=data.get("due_at"),
            note=data.get("note"),
            reverts_id=data.get("reverts_id"),
        )

