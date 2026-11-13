# DECISIONS

Write in English. Short bullet points are fine. Reviewers read this file alongside your code.

## What I assumed

- **In-Memory Store Architecture:** With ~12,000 requests across 6 months, the entire dataset and event tree easily fits within ~50 MB of memory. Storing objects in memory eliminated the operational overhead and latency of an external database while keeping queries instantaneous.
- **Tied Sorting and Nulls-Last:** For `/api/requests`, when sorting by `response_business_minutes` (ascending or descending), rows with `null` values always sort to the end, and ties are broken deterministically by `id ASC`.
- **Completion Check on Reopened Tickets:** Per Rule 6, the completion timestamp is determined by the *last* event with status `complete`, even if intermediate or subsequent events reopened the ticket.
- **Deadline Resolution:** The deadline is evaluated from the latest event that specified a non-empty `due_at`, converted to a timezone-aware timestamp in the site's local timezone.
- **Staff Resolution by ID:** Responders are identified strictly by `actor_id` from the earliest processing event, and their current display name is resolved dynamically from `/v1/staff`.

## What I found in the API or data

- **Duplicate Staff Names:** Identified two distinct staff members with the same name "Marcus Lee" (ID 368 and ID 371). Kept all mappings and responder aggregations keyed by `id` rather than name to prevent collisions.
- **Jakarta Saturday Half-Day:** Robusttechhouse Plaza Jakarta operates on Saturdays from `08:00` to `12:00` (unlike Singapore and Sydney which are closed all weekend). Designed the business hours calculator to walk calendar days individually to count half-day intervals accurately.
- **Mixed Timestamp Formats:** The API presents timestamps in four different formats: ISO-8601 UTC for request `created_at`, Unix epoch seconds for event `at`, `"DD/MM/YYYY HH:mm"` site-local wall-clock time for event `due_at`, and `"DD/MM/YYYY"` for site holidays. Normalization routines were implemented for each format.
- **Rate Limits & Cursor Expiration:** The API enforces rate limiting (HTTP 429) with `Retry-After` headers and expires change-feed cursors after 15 minutes (HTTP 410). Implemented automatic backoff retry logic and cursor reset handling in the synchronization loop.

## How I used AI

- Used Google Antigravity assistant to systematically analyze the 7 SLA rules, job requirements, and API specifications into a structured multi-phase plan.
- Generated comprehensive unit test suites covering business hours calendar boundaries (weekend spans, public holidays, outside-hours submissions, and undone reverted events).
- Kept the implementation surgical and simple, verifying every step independently against Docker and pytest requirements.

## Trade-offs and what I would do next

- **Scale Beyond Memory Limits:** For 12,000 requests, in-memory dicts provide sub-millisecond query responses. If data grew to millions of requests, I would migrate the store to PostgreSQL or SQLite with composite indexes on `(site_id, created_at)` and pre-aggregated summary tables.
- **Pre-computed SLA Cache:** Currently, SLA metrics are calculated from event histories when queries arrive. Pre-computing SLA metrics during the change feed ingestion would make 6-month aggregations virtually instantaneous ($O(1)$ range lookup).
- **Frontend Polish:** Kept the frontend UI strictly simple and functional (semantic HTML, native CSS, vanilla JavaScript table rendering without external framework bloat). With more time, I would add quick-range presets ("Last 30 Days", "Current Month") and CSV report export.
