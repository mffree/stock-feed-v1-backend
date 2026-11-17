import os

# Must be set before `app.config` is imported anywhere, since Settings()
# is instantiated at import time.
os.environ.setdefault("ALPACA_API_KEY_ID", "test-key-id")
os.environ.setdefault("ALPACA_SECRET_KEY", "test-secret-key")
# Forced (not setdefault): DATABASE_URL in .env is the production database,
# and tests must never touch it.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

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
