"""Compatibility entry point: ``uvicorn backend.main:app --reload``."""

from .app.main import app

__all__ = ["app"]
