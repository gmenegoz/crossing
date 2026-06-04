from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.router import router

BASE = Path(__file__).parent.parent

app = FastAPI()

# API routes first — must be registered before catch-all static mounts
app.include_router(router, prefix="/api")

# Serve asset PNGs at /assets/{layer}/{file}
app.mount("/assets", StaticFiles(directory=BASE / "assets"), name="assets")

# Catch-all: serve static/index.html for all other paths
app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
