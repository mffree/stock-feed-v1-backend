from fastapi import FastAPI

from app.routers import feed, health

app = FastAPI(title="Stock Feed v1")

app.include_router(health.router)
app.include_router(feed.router)
