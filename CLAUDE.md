# Stock Feed v1 — Backend

FastAPI backend with one job: serve a JSON feed of 10 randomly-selected S&P 500
stocks with 1-year weekly price history, for a SwiftUI client. It also provides
optional Sign in with Apple accounts, backed by Postgres (SQLAlchemy async +
Alembic). There's no Redis or caching layer.

- Auth design, product rules, and env/database safety rules: `../CLAUDE.md`.
- Auth endpoint contract: `API.md`. Keep it in sync with the code in the same commit.
- `/feed` and `/health` never require auth.

## Structure

```
app/
├── main.py              # FastAPI app instance, mounts routers
├── config.py             # pydantic-settings; reads all env vars from .env
├── data/sp500.csv         # Symbol + Security columns, used to sample tickers and look up company names
├── routers/
│   ├── feed.py            # GET /feed
│   └── health.py           # GET /health
├── services/
│   └── alpaca_client.py    # All Alpaca Market Data API calls live here
└── schemas.py             # Pydantic response models
tests/
└── test_feed.py, test_health.py
```

Auth adds `db.py`, `models.py`, `auth/`, `routers/auth.py`,
`routers/users.py`, and `alembic/`. The planned layout is in `../CLAUDE.md`.
Update this tree as those files land.

Env vars: `ALPACA_API_KEY_ID`, `ALPACA_SECRET_KEY`, `DATABASE_URL`,
`JWT_SECRET`, `APPLE_BUNDLE_ID`.

## Conventions

- **Async/await throughout.** All I/O (HTTP calls, request handlers, database)
  is async: `httpx.AsyncClient` for HTTP, SQLAlchemy `AsyncSession` (asyncpg) for
  the DB. Don't introduce sync HTTP calls (e.g. `requests`) or sync DB sessions.
- **`DATABASE_URL` is production.** There's no local DB. Ask the user before
  running migrations or any write against it. Tests use in-memory SQLite
  (`aiosqlite`) through a dependency override, never `DATABASE_URL`.
- **New endpoints always come with tests.** Mock external HTTP calls with
  `respx` — never hit the real Alpaca API or Apple's JWKS endpoint in tests. See `tests/conftest.py` for
  the shared async test client fixture and deterministic ticker sampling.
- **Credentials only via config.py / .env.** Never hardcode API keys. `.env` is
  gitignored; `.env.example` documents the required vars.

## Alpaca Market Data API

- **Auth is two headers, not a bearer token:** `APCA-API-KEY-ID` and
  `APCA-API-SECRET-KEY`, set on every request. This is the Market Data API
  (`https://data.alpaca.markets`), distinct from the Trading API.
- **Free tier requires `feed=iex`** as a query param on every request.
- **Bars are fetched at weekly resolution** (`timeframe=1Week`) and **batched
  across all 10 symbols in a single request** (comma-separated `symbols` param)
  rather than one call per ticker.
- **`current_price` is the `close` of the last bar** in each ticker's history —
  there is no separate snapshot/quote call for the latest price.
- Pagination (`next_page_token`) is handled defensively in
  `alpaca_client.get_weekly_bars`, even though weekly data for 10 tickers is
  well under the default page size and rarely pages in practice.
- A ticker missing from the Alpaca response (delisted, no data) is skipped —
  `/feed` still returns the rest. A failure of the whole bars call (429, 401,
  network error) surfaces as a 502/503 to the caller instead of a silent empty
  array.
