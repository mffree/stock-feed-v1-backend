from pydantic import BaseModel


class PricePoint(BaseModel):
    date: str
    close: float


class StockFeedItem(BaseModel):
    ticker: str
    company_name: str
    current_price: float
    history: list[PricePoint]
