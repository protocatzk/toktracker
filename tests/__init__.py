import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Wichtig: Umgebung (isolierte DB, Secrets) vor allen App-Imports setzen.
try:
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover - Fallback für direkten Modulaufruf
    import _bootstrap  # noqa: F401
