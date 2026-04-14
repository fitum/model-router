"""Starlette application factory."""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from model_router.router import ModelRouter
from model_router.tracker import UsageTracker
from server.routes import make_routes

STATIC_DIR = Path(__file__).parent / "static"


def create_app(tracker: UsageTracker, router: ModelRouter) -> Starlette:
    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]
    return Starlette(
        routes=[
            *make_routes(tracker, router),
            Mount("/", app=StaticFiles(directory=str(STATIC_DIR), html=True)),
        ],
        middleware=middleware,
    )
