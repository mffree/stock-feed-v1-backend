# Stock Feed v1 — Backend

FastAPI backend with one job: serve a JSON feed of 10 randomly-selected S&P 500
stocks with 1-year weekly price history, for a SwiftUI client. v1 is intentionally
minimal — no database, no auth, no Redis, no caching layer.

## Structure

```
app/
├── main.py              # FastAPI app instance, mounts routers
├── config.py             # pydantic-settings; reads ALPACA_API_KEY_ID / ALPACA_SECRET_KEY from .env
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

## Conventions

- **Async/await throughout.** All I/O (HTTP calls, request handlers) is async,
  using `httpx.AsyncClient`. Don't introduce sync HTTP calls (e.g. `requests`).
- **New endpoints always come with tests.** Mock external HTTP calls with
  `respx` — never hit the real Alpaca API in tests. See `tests/conftest.py` for
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
