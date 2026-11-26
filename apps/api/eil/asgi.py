"""ASGI entrypoint: uvicorn eil.asgi:app."""

from __future__ import annotations

from eil.main import create_app

app = create_app()
