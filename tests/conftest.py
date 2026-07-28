import os

# Must be set before `app.config` is imported anywhere, since Settings()
# is instantiated at import time.
os.environ.setdefault("ALPACA_API_KEY_ID", "test-key-id")
os.environ.setdefault("ALPACA_SECRET_KEY", "test-secret-key")

import httpx
import pytest


@pytest.fixture
def deterministic_sample(monkeypatch):
    """Make ticker sampling deterministic: always take the first `k` rows."""

    def fake_sample(population, k):
        return list(population)[:k]

    monkeypatch.setattr("app.routers.feed.random.sample", fake_sample)


@pytest.fixture
async def client(deterministic_sample):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
