import httpx
import respx

from app.services.alpaca_client import BARS_URL

BARS = {
    "t": "2025-01-06T05:00:00Z",
    "c": 100.0,
    "o": 99.0,
    "h": 101.0,
    "l": 98.0,
    "v": 1000,
}
BARS_LATER = {
    "t": "2025-01-13T05:00:00Z",
    "c": 105.0,
    "o": 100.0,
    "h": 106.0,
    "l": 99.0,
    "v": 1200,
}


def _bars_response(symbols):
    return {
        "bars": {symbol: [BARS, BARS_LATER] for symbol in symbols},
        "next_page_token": None,
    }


@respx.mock
async def test_feed_returns_ten_stocks_with_history(client):
    def handler(request):
        symbols = request.url.params["symbols"].split(",")
        return httpx.Response(200, json=_bars_response(symbols))

    respx.get(BARS_URL).mock(side_effect=handler)

    response = await client.get("/feed")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    for item in data:
        assert item["history"] == [
            {"date": "2025-01-06", "close": 100.0},
            {"date": "2025-01-13", "close": 105.0},
        ]
        assert item["current_price"] == 105.0
        assert item["company_name"]


@respx.mock
async def test_feed_skips_ticker_missing_from_response(client):
    def handler(request):
        symbols = request.url.params["symbols"].split(",")
        payload = _bars_response(symbols)
        del payload["bars"][symbols[0]]
        return httpx.Response(200, json=payload)

    respx.get(BARS_URL).mock(side_effect=handler)

    response = await client.get("/feed")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 9


@respx.mock
async def test_feed_returns_error_when_alpaca_rate_limits(client):
    respx.get(BARS_URL).mock(return_value=httpx.Response(429, json={"message": "rate limited"}))

    response = await client.get("/feed")

    assert response.status_code == 503


@respx.mock
async def test_feed_returns_error_when_alpaca_auth_fails(client):
    respx.get(BARS_URL).mock(return_value=httpx.Response(401, json={"message": "unauthorized"}))

    response = await client.get("/feed")

    assert response.status_code == 502
