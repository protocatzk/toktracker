"""
TokTracker - Config Re-export & Abwärtskompatibilität
Ermöglicht Importe wie `from config import config, BASE_DIR` sowie `from shared.config import config`.
"""

from shared.config import (
    BASE_DIR,
    ENV_PATH,
    PROJECT_ROOT,
    AppConfig,
    _mask_secret,
    _parse_csv_list,
    config,
)

__all__ = [
    "BASE_DIR",
    "PROJECT_ROOT",
    "ENV_PATH",
    "AppConfig",
    "config",
    "_mask_secret",
    "_parse_csv_list",
]
