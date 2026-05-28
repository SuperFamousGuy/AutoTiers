# AutoTiers

Generates fantasy football draft tier lists from your league settings and a configurable set of heuristic rules. You configure scoring format, league type, and which rules to weight; AutoTiers fetches current player data and projections, applies the rules as score modifiers, clusters players into tiers per position using Jenks Natural Breaks, merges them into an overall draft board, and produces a downloadable CSV.

---

## Project Status

| Layer | Status | Notes |
|---|---|---|
| Backend (FastAPI) | In review ([PR #1](https://github.com/SuperFamousGuy/AutoTiers/pull/1)) | Full engine + API; data fetchers are stubs |
| Data Pipeline | Not started | Real scrapers for nfl_data_py, FantasyPros, ESPN, Sleeper |
| Frontend (React) | Not started | Three-panel UI: Settings / Rules / Tiers |

---

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, APScheduler
- **Database:** PostgreSQL (Supabase-hosted in production)
- **Frontend:** React 18, TypeScript, Vite, TanStack Query, Tailwind CSS *(planned)*
- **Deployment:** Railway (backend + frontend), Supabase (PostgreSQL)

---

## Run with Docker or Podman (recommended)

The fastest way to get a working local environment is `docker compose` (or its Podman equivalent). Spins up a Postgres container, runs migrations, seeds ~10 sample players, and starts the API with hot reload.

```bash
docker compose up --build         # Docker
podman compose up --build         # Podman 4.4+ (recommended for Podman users)
podman-compose up --build         # older podman-compose
```

**Podman on macOS:** initialize and start the machine first if you haven't already:
```bash
podman machine init && podman machine start
```

The entrypoint script explicitly waits for Postgres to accept connections before running migrations, so any of the above command variants behave the same — even older `podman-compose` versions that don't honor `depends_on.condition: service_healthy`.

Then open:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Try a request against the seeded data:
```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"scoring_format":"ppr","league_type":"standard","league_size":12,"qb_td_points":4.0,"bonus_100yd_rushing":false,"bonus_100yd_receiving":false,"bonus_first_downs":false,"weight_prior_year":0.30,"weight_espn":0.0,"weight_consensus":0.70,"rules":[]}'
```

Override defaults by copying `.env.example` to `.env` (port mappings, postgres credentials, whether to seed). To skip seeding on first start, set `SEED_DEV_DATA=false`. To reset the database completely:

```bash
docker compose down -v   # -v also removes the postgres volume
docker compose up --build
```

Code in `backend/app/`, `backend/alembic/`, `backend/scripts/`, and `backend/tests/` is mounted into the container — edits trigger hot reload.

## Frontend

The React frontend lives in `web/`. With docker-compose, it comes up automatically alongside the backend at http://localhost:5173.

To run the frontend without Docker (against a containerized backend):

```bash
cd web
npm install
npm run dev
# → opens http://localhost:5173
```

The frontend reads `VITE_API_URL` from its environment. In Docker it's set to `http://localhost:8000`; for host-side dev override via `web/.env.local`:

```
VITE_API_URL=http://localhost:8000
```

### Frontend tests

```bash
cd web
npm test            # one-shot
npm run test:watch  # watch mode
```

## Backend — Local Setup (without Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set your database URL:

```
DATABASE_URL=postgresql+asyncpg://localhost/autotiers
DATABASE_URL_SYNC=postgresql+psycopg2://localhost/autotiers
```

Run migrations:

```bash
alembic upgrade head
```

Optionally seed sample data:

```bash
python -m scripts.seed_dev
```

Start the server:

```bash
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://localhost/autotiers` | Async DB URL for the app |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://localhost/autotiers` | Sync URL for Alembic migrations |
| `RUN_SCHEDULER` | `false` | Set `true` on one worker to enable cron jobs |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins (tighten in production) |
| `ADMIN_API_KEY` | `""` | If set, required as `X-Api-Key` header on `POST /api/data/refresh` |

### Tests

```bash
pytest -v
```

40 tests (unit + integration), using SQLite in-memory — no PostgreSQL required to run tests.

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/generate` | Generate tier list; returns ranked JSON |
| `POST` | `/api/generate/csv` | Same as above, returns downloadable CSV |
| `GET` | `/api/rules` | All built-in rules with defaults |
| `GET` | `/api/players` | All cached players |
| `GET` | `/api/data/status` | Data freshness per source |
| `POST` | `/api/data/refresh` | Trigger manual data refresh (admin-gated) |
| `GET` | `/health` | Health check |

### Example request

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "scoring_format": "ppr",
    "league_type": "standard",
    "league_size": 12,
    "qb_td_points": 4.0,
    "bonus_100yd_rushing": false,
    "bonus_100yd_receiving": false,
    "bonus_first_downs": false,
    "weight_prior_year": 0.30,
    "weight_espn": 0.0,
    "weight_consensus": 0.70,
    "rules": []
  }'
```

---

## Accounts

Anonymous use is the default. Optional account creation gives users up to **5 saved profiles**, each capturing the full Settings + Rules configuration.

### Auth endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/signup` | Email + password signup; optionally migrates anonymous state to a first profile |
| `POST` | `/api/auth/login` | Email + password login; rate-limited 5 / 15min per email |
| `POST` | `/api/auth/logout` | Clears session cookie |
| `GET`  | `/api/auth/me` | Returns the current user + profiles, or 401 |
| `GET`  | `/api/auth/yahoo/authorize` | Starts Yahoo OAuth |
| `GET`  | `/api/auth/yahoo/callback` | Yahoo OAuth return URL |

### Profile endpoints

| Method | Path | Description |
|---|---|---|
| `GET`    | `/api/profiles` | List user's profiles + active id |
| `POST`   | `/api/profiles` | Create profile (409 when at 5) |
| `PATCH`  | `/api/profiles/{id}` | Partial update (name, settings_json, rules_json) |
| `DELETE` | `/api/profiles/{id}` | Delete |
| `POST`   | `/api/profiles/{id}/activate` | Set as last-active |

### Env vars

- `JWT_SECRET` — 32+ byte secret for signing session JWTs (required in prod; dev default is a placeholder)
- `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REDIRECT_URI` — Yahoo OAuth app credentials (optional)
- `FRONTEND_URL` — where Yahoo OAuth callback redirects after login (default `http://localhost:5173`)

Email verification, password reset, and account linking are deferred for v1 — see the [design spec](docs/superpowers/specs/2026-05-26-accounts-and-profiles-design.md).

---

## Engines

### Scoring Engine

Produces one `projected_score` per player from a configurable weighted blend:

| Source | Default Weight | Configurable? |
|---|---|---|
| Prior year actuals | 30% | Yes — linked sliders, must sum to 100% |
| Consensus projection (FantasyPros + ESPN + others averaged) | 70% | Yes |

The UI exposes exactly two sliders ("Prior year actuals" and "Consensus projection"). ESPN data is rolled into the consensus average and is no longer a separate user-facing input. The API also accepts `weight_espn` for advanced clients (default `0.0`); the UI no longer exposes it.

Supports Standard, Half-PPR, and Full PPR.

### Rules Engine

16 built-in rules across five categories:

| Category | Examples |
|---|---|
| Age / Longevity | RB age penalty (28+), WR age penalty (31+), Dynasty youth premium (<25) |
| Usage | RB committee discount, target share premium, declining snap% |
| Situation | New team, new head coach, sophomore leap, contract year flag |
| Regression | Injury history discount |
| Flags | Handcuff, injury designation, availability risk |

Each rule has a weight slider (0.5× / 1× / 2×) and can be toggled on/off. Custom rules can be added via JSON:

```json
{
  "name": "My Rule",
  "conditions": [{ "field": "age", "operator": ">", "value": 34 }],
  "effect": { "type": "multiplier", "value": 0.80 }
}
```

Supported condition fields: `age`, `position`, `snap_pct`, `carry_share`, `target_share`, `games_played`, `years_exp`, `adp`, `projected_score`, `new_team`, `new_coach`.

### Tier Engine

1. Runs Jenks Natural Breaks clustering per position — finds natural score gaps without requiring a preset tier count
2. Assigns positional labels: QB1/QB2/QB3, RB1–RB5, WR1–WR5, TE1–TE3, etc. (caps scale with league size)
3. Merges all positions and runs a second Jenks pass for overall tier numbers
4. Sorts by adjusted score; ADP serves as tiebreaker (format-appropriate: dynasty/PPR/standard)

---

## Data Sources *(Plan 2 — not yet implemented)*

| Source | Data | Auth |
|---|---|---|
| nfl_data_py | Historical stats, rosters | None (free) |
| FantasyPros | Consensus projections, ADP | Scraped public pages |
| ESPN | Projections | Unofficial API |
| Sleeper | Dynasty ADP, player metadata | None (free) |

Data refresh runs automatically — weekly June–July, daily August–September — via APScheduler. Manual refresh available via `POST /api/data/refresh`.

---

## Repository Layout

```
AutoTiers/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (generate, rules, players, data)
│   │   ├── data/         # DataFetcher (stub; real scrapers in Plan 2)
│   │   ├── engine/       # scoring.py, rules.py, tiers.py, builtin_rules.py
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── config.py     # pydantic-settings
│   │   ├── database.py   # async engine + session factory
│   │   ├── main.py       # FastAPI app + lifespan
│   │   └── scheduler.py  # APScheduler jobs
│   ├── alembic/          # Migrations
│   ├── tests/            # pytest suite (40 tests)
│   └── pyproject.toml
└── docs/
    └── superpowers/
        ├── specs/        # Design spec
        └── plans/        # Implementation plans
```
