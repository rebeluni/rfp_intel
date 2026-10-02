"""
FastAPI Server for RFP Intelligence Platform.
Exposes /index, /search, /ask, and /health endpoints.
"""

from api.server import app

__all__ = ["app"]
