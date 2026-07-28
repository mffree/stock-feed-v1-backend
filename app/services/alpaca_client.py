from datetime import date, timedelta

import httpx

from app.config import settings

BASE_URL = "https://data.alpaca.markets"
BARS_URL = f"{BASE_URL}/v2/stocks/bars"


class AlpacaAPIError(Exception):
    """Raised when the Alpaca Market Data API call fails entirely."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key_id,
        "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
    }


async def get_weekly_bars(
    client: httpx.AsyncClient, symbols: list[str]
) -> dict[str, list[dict]]:
    """Fetch 1-year weekly bars for the given symbols, merging paginated results.

    Raises AlpacaAPIError if the call fails outright (auth error, rate limit,
    network failure, etc). A symbol simply absent from the response is not an
    error here — callers decide how to handle missing tickers.
    """
    end = date.today()
    start = end - timedelta(days=365)

    params = {
        "symbols": ",".join(symbols),
        "timeframe": "1Week",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "feed": "iex",
    }

    bars: dict[str, list[dict]] = {}
    page_token: str | None = None

    while True:
        request_params = dict(params)
        if page_token:
            request_params["page_token"] = page_token

        try:
            response = await client.get(BARS_URL, headers=_headers(), params=request_params)
        except httpx.RequestError as exc:
            raise AlpacaAPIError(502, f"Failed to reach Alpaca API: {exc}") from exc

        if response.status_code == 429:
            raise AlpacaAPIError(503, "Alpaca API rate limit exceeded")
        if response.status_code != 200:
            raise AlpacaAPIError(
                502, f"Alpaca API returned {response.status_code}: {response.text}"
            )

        payload = response.json()
        for symbol, symbol_bars in payload.get("bars", {}).items():
            bars.setdefault(symbol, []).extend(symbol_bars)

        page_token = payload.get("next_page_token")
        if not page_token:
            break

    return bars
