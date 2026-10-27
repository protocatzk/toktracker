import abc
from typing import Any, Callable, Dict, List, Optional


class BaseBus(abc.ABC):
    """Abstrakte Basisklasse für Message-Bus, Event-Stream, KV-Store und Leases."""

    @abc.abstractmethod
    async def connect(self) -> None:
        pass

    @abc.abstractmethod
    async def disconnect(self) -> None:
        pass

    # PubSub
    @abc.abstractmethod
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        pass

    @abc.abstractmethod
    def publish_sync(self, channel: str, message: Dict[str, Any]) -> None:
        pass

    @abc.abstractmethod
    async def subscribe(self, channel: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        pass

    # Events / Streams
    @abc.abstractmethod
    async def add_event(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        pass

    @abc.abstractmethod
    def add_event_sync(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        pass

    # Key-Value & Caching
    @abc.abstractmethod
    async def set_kv(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        pass

    @abc.abstractmethod
    def set_kv_sync(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        pass

    @abc.abstractmethod
    async def get_kv(self, key: str) -> Optional[str]:
        pass

    @abc.abstractmethod
    def get_kv_sync(self, key: str) -> Optional[str]:
        pass

    @abc.abstractmethod
    async def delete_kv(self, key: str) -> None:
        pass

    @abc.abstractmethod
    def delete_kv_sync(self, key: str) -> None:
        pass

    @abc.abstractmethod
    async def incr_kv(self, key: str, ttl: Optional[int] = None) -> int:
        """Atomarer Zähler (für Rate-Limits). Setzt beim ersten Treffer eine TTL."""
        pass

    @abc.abstractmethod
    def incr_kv_sync(self, key: str, ttl: Optional[int] = None) -> int:
        pass

    @abc.abstractmethod
    async def scan_keys(self, pattern: str) -> List[str]:
        pass

    @abc.abstractmethod
    def scan_keys_sync(self, pattern: str) -> List[str]:
        pass

    # Leases & Distributed Locks
    @abc.abstractmethod
    async def acquire_lease(self, key: str, owner_id: str, ttl_seconds: int = 30) -> bool:
        pass

    @abc.abstractmethod
    async def renew_lease(self, key: str, owner_id: str, ttl_seconds: int = 30) -> bool:
        pass

    @abc.abstractmethod
    async def release_lease(self, key: str, owner_id: str) -> bool:
        pass

    # RPC
    @abc.abstractmethod
    async def rpc_call(self, queue: str, payload: Dict[str, Any], timeout: float = 3.5) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def rpc_listen(self, queue: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        pass
