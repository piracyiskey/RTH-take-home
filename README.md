# SLA Response-Time Report

A FastAPI web service that calculates response-time metrics and SLA compliance across properties in Singapore, Sydney, and Jakarta, powered by an in-memory replica synchronized with the Helpdesk API.

---

## Quick Start (Docker - Recommended)

The application and tests are containerized and evaluated via Docker Compose.

### 1. Clone the repository
```bash
git clone https://github.com/piracyiskey/RTH-take-home.git
cd RTH-take-home
```

### 2. Configure environment
Create a `.env` file in the project root:
```bash
cp .env.example .env
```
Fill in your test Helpdesk credentials:
```env
HELPDESK_URL=https://hiring.robusttechhouse.com/practice-api/...
HELPDESK_TOKEN=your_token_here
```

### 3. Run the application
```bash
docker compose up --build
```
- **Web UI:** [http://localhost:8080](http://localhost:8080)
- **Readiness check:** [http://localhost:8080/ready](http://localhost:8080/ready) *(returns `200 {"ready": true}` once initial sync completes in ~40–50s)*
- **Health check:** [http://localhost:8080/health](http://localhost:8080/health)

### 4. Run automated tests
```bash
docker compose run --rm app test
```

---

## Local Development (Without Docker)

If developing outside Docker with Python 3.12+:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r app/requirements.txt

# Run test suite
pytest

# Start development server
cd app
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## API Endpoints

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/` | `GET` | Clean tabular web report interface |
| `/health` | `GET` | Liveness check (`200 {"ok": true}`) |
| `/ready` | `GET` | Readiness check (`200 {"ready": true}` or `503`) |
| `/api/sla-report` | `GET` | SLA report and responder aggregates (`?from=YYYY-MM-DD&to=YYYY-MM-DD`) |
| `/api/requests` | `GET` | Filtered, sorted, and cursor-paginated request list |
| `/api/requests.csv` | `GET` | Downloadable CSV export of filtered and sorted requests |

---

## Project Structure

```text
app/
├── app/
│   ├── main.py              # FastAPI routes, lifespan worker, validation, CSV export
│   ├── sla.py               # SLA rule engine (Rules 2–7) & responder aggregations
│   ├── business_hours.py    # Calendar business-minutes calculator (timezones, holidays, partial days)
│   ├── store.py             # In-memory data replica (requests, events, sites, staff)
│   ├── sync.py              # Change feed consumer (/v1/changes bulk load + 10s live poll)
│   ├── browse.py            # Nulls-last sorting and HMAC-signed cursor pagination
│   ├── helpdesk.py          # Async/sync API client with HTTP 429 Retry-After backoff
│   └── models.py            # Dataclasses with slots for low memory footprint
├── static/                  # Single-page frontend dashboard (index.html, styles.css, app.js)
├── tests/                   # Unit & integration tests for all business rules and endpoints
├── Dockerfile               # Container build definition for Python 3.12-slim
└── requirements.txt         # Pinned application dependencies
```

---

## Documentation & Decisions

- **[DECISIONS.md](DECISIONS.md):** Detailed rationale on architecture, API discoveries, edge-case handling, AI tool usage, and trade-offs.
- **[README-starter-kit.md](README-starter-kit.md):** Original instructions and starter kit requirements.
- **[`docs/`](docs/):** Original problem brief, contract specification, rules, and API reference.
