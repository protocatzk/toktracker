"""
TokTracker - API & Web Service Entrypoint
"""

import logging

from app import app

logger = logging.getLogger("toktracker.api")

__all__ = ["app"]
