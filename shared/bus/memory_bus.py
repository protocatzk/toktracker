import asyncio
import fnmatch
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from shared.bus.base import BaseBus

logger = logging.getLogger("toktracker.memory_bus")


class MemoryBus(BaseBus):
    """
    In-Memory-Fallback für Standalone-Betrieb ohne Redis (z.B. lokale SQLite-Entwicklung).
    Simuliert PubSub, KV-Store mit TTL, Leases und RPC im selben Python-Prozess.
    """

    def __init__(self):
        self._kv: Dict[str, Tuple[str, Optional[float]]] = {}
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}
        self._leases: Dict[str, Tuple[str, float]] = {}
        self._rpc_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    # PubSub
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        handlers = list(self._subscribers.get(channel, []))
        for h in handlers:
            try:
                res = h(message)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as exc:
                logger.error("MemoryBus PubSub Handler Fehler auf %s: %s", channel, exc)

    def publish_sync(self, channel: str, message: Dict[str, Any]) -> None:
        handlers = list(self._subscribers.get(channel, []))
        for h in handlers:
            try:
                res = h(message)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as exc:
                logger.error("MemoryBus PubSub Handler Sync Fehler auf %s: %s", channel, exc)

    async def subscribe(self, channel: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._subscribers.setdefault(channel, []).append(handler)

    # Streams
    async def add_event(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        # In Memory: optional logger/noop
        pass

    def add_event_sync(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        pass

    # KV
    async def set_kv(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        self.set_kv_sync(key, value, ttl)

    def set_kv_sync(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        exp = (time.time() + ttl) if ttl else None
        self._kv[key] = (value, exp)

    async def get_kv(self, key: str) -> Optional[str]:
        return self.get_kv_sync(key)

    def get_kv_sync(self, key: str) -> Optional[str]:
        item = self._kv.get(key)
        if not item:
            return None
        val, exp = item
        if exp is not None and time.time() > exp:
            self._kv.pop(key, None)
            return None
        return val

    async def delete_kv(self, key: str) -> None:
        self.delete_kv_sync(key)

    def delete_kv_sync(self, key: str) -> None:
        self._kv.pop(key, None)

    async def scan_keys(self, pattern: str) -> List[str]:
        return self.scan_keys_sync(pattern)

    def scan_keys_sync(self, pattern: str) -> List[str]:
        now = time.time()
        res = []
        for k, (_, exp) in list(self._kv.items()):
            if exp is not None and now > exp:
                self._kv.pop(k, None)
                continue
            if fnmatch.fnmatch(k, pattern):
                res.append(k)
        return res

    # Leases
    async def acquire_lease(self, key: str, owner_id: str, ttl_seconds: int = 30, **kwargs) -> bool:
        actual_ttl = kwargs.get("ttl", ttl_seconds)
        now = time.time()
        item = self._leases.get(key)
        if item and now < item[1]:
            if item[0] == owner_id:
                self._leases[key] = (owner_id, now + actual_ttl)
                return True
            return False
        self._leases[key] = (owner_id, now + actual_ttl)
        return True

    async def renew_lease(self, key: str, owner_id: str, ttl_seconds: int = 30, **kwargs) -> bool:
        actual_ttl = kwargs.get("ttl", ttl_seconds)
        now = time.time()
        item = self._leases.get(key)
        if item and item[0] == owner_id and now < item[1]:
            self._leases[key] = (owner_id, now + actual_ttl)
            return True
        return False

    async def release_lease(self, key: str, owner_id: str) -> bool:
        item = self._leases.get(key)
        if item and item[0] == owner_id:
            self._leases.pop(key, None)
            return True
        return False

    # RPC
    async def rpc_call(self, queue: str, payload: Dict[str, Any], timeout: float = 3.5) -> Dict[str, Any]:
        handler = self._rpc_handlers.get(queue)
        if not handler:
            return {"ok": False, "error": f"Kein Handler für RPC Queue {queue}"}
        res = handler(payload)
        if asyncio.iscoroutine(res):
            res = await res
        return res or {"ok": True}

    async def rpc_listen(self, queue: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self._rpc_handlers[queue] = handler
