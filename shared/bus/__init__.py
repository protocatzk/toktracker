import threading
from typing import Optional

from shared.bus.base import BaseBus
from shared.bus.memory_bus import MemoryBus
from shared.config import config

_bus_instance: Optional[BaseBus] = None
_bus_lock = threading.Lock()


def get_bus() -> BaseBus:
    """Liefert die konfigurierte Bus-Instanz (RedisBus oder MemoryBus als Singleton)."""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                if config.has_redis:
                    from shared.bus.redis_bus import RedisBus
                    _bus_instance = RedisBus(config.redis_url)
                else:
                    _bus_instance = MemoryBus()
    return _bus_instance


__all__ = ["BaseBus", "get_bus"]
