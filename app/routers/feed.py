import csv
import random
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from app.schemas import PricePoint, StockFeedItem
from app.services.alpaca_client import AlpacaAPIError, get_weekly_bars

router = APIRouter()

SP500_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "sp500.csv"
SAMPLE_SIZE = 10


@lru_cache
def _load_sp500() -> list[tuple[str, str]]:
    with SP500_CSV_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        return [(row["Symbol"], row["Security"]) for row in reader]


@router.get("/feed", response_model=list[StockFeedItem])
async def get_feed() -> list[StockFeedItem]:
    sample = random.sample(_load_sp500(), SAMPLE_SIZE)
    company_names = dict(sample)
    tickers = list(company_names)

    async with httpx.AsyncClient() as client:
        try:
            bars = await get_weekly_bars(client, tickers)
        except AlpacaAPIError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    feed: list[StockFeedItem] = []
    for ticker in tickers:
        ticker_bars = bars.get(ticker)
        if not ticker_bars:
            continue

        history = [
            PricePoint(date=bar["t"][:10], close=bar["c"]) for bar in ticker_bars
        ]
        history.sort(key=lambda point: point.date)

        feed.append(
            StockFeedItem(
                ticker=ticker,
                company_name=company_names[ticker],
                current_price=history[-1].close,
                history=history,
            )
        )

    return feed
