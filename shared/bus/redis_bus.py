import asyncio
import json
import logging
import math
import secrets
import threading
from typing import Any, Callable, Dict, List, Optional

import redis
import redis.asyncio as aioredis

from shared.bus.base import BaseBus

logger = logging.getLogger("toktracker.redis_bus")

LUA_RENEW_LEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
"""

LUA_RELEASE_LEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Atomarer Zähler für Rate-Limits: TTL wird nur beim ersten Treffer gesetzt (fixes Fenster).
def _as_text(value: Any) -> Optional[str]:
    """Normalisiert Redis-Werte (decode_responses=True -> str, Stubs erlauben bytes)."""
    if value is None:
        return None
    return value.decode("utf-8", "replace") if isinstance(value, (bytes, bytearray)) else str(value)


LUA_INCR_KV = """
local current = redis.call("incr", KEYS[1])
if tonumber(ARGV[1]) > 0 and current == 1 then
    redis.call("expire", KEYS[1], tonumber(ARGV[1]))
end
return current
"""


class RedisBus(BaseBus):
    """
    Vollständige Redis-Implementierung für PubSub, Streams, KV, Distributed Leases und RPC.
    Bietet sowohl asynchrone als auch synchrone Methoden.
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._async_client: Optional[aioredis.Redis] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._sync_client: Optional[redis.Redis] = None
        self._sync_lock = threading.Lock()
        self._sub_tasks: List[asyncio.Task] = []
        self._running = False

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        # Ein Redis-Async-Client ist an den Event-Loop gebunden, in dem er erzeugt wurde.
        # Wechselt der Loop (Tests mit mehreren Loops, Reload-Worker), muss der Client
        # neu aufgebaut werden – sonst gibt es "attached to a different loop"-Fehler.
        if self._async_client is not None and self._async_loop is not loop:
            self._async_client = None
            self._async_loop = None

        if self._async_client is None:
            self._async_client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            self._async_loop = loop
            self._running = True

    def _get_sync_client(self) -> redis.Redis:
        if self._sync_client is None:
            with self._sync_lock:
                if self._sync_client is None:
                    self._sync_client = redis.from_url(
                        self.redis_url,
                        decode_responses=True,
                        socket_timeout=5.0,
                        socket_connect_timeout=5.0,
                    )
        return self._sync_client

    async def disconnect(self) -> None:
        self._running = False
        for t in self._sub_tasks:
            t.cancel()
        self._sub_tasks.clear()
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None
        if self._sync_client is not None:
            with self._sync_lock:
                if self._sync_client is not None:
                    try:
                        self._sync_client.close()
                    except Exception:
                        pass
                    self._sync_client = None

    # PubSub
    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        await self.connect()
        assert self._async_client is not None
        payload = json.dumps(message, default=str)
        await self._async_client.publish(channel, payload)

    def publish_sync(self, channel: str, message: Dict[str, Any]) -> None:
        client = self._get_sync_client()
        payload = json.dumps(message, default=str)
        client.publish(channel, payload)

    async def subscribe(self, channel: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        await self.connect()
        assert self._async_client is not None
        pubsub = self._async_client.pubsub()
        await pubsub.subscribe(channel)

        async def _listen_loop():
            try:
                async for msg in pubsub.listen():
                    if not self._running:
                        break
                    if msg.get("type") == "message":
                        try:
                            data = json.loads(msg.get("data", "{}"))
                            res = handler(data)
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception as exc:
                            logger.error("Fehler im PubSub-Handler für %s: %s", channel, exc)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if self._running:
                    logger.error("PubSub Listen-Fehler auf %s: %s", channel, exc)
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    pass

        task = asyncio.create_task(_listen_loop())
        self._sub_tasks.append(task)

    # Streams
    async def add_event(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        await self.connect()
        assert self._async_client is not None
        fields: Dict[Any, Any] = {
            k: json.dumps(v, default=str) if isinstance(v, (dict, list, bool)) else str(v)
            for k, v in data.items()
        }
        await self._async_client.xadd(stream, fields, maxlen=maxlen, approximate=True)

    def add_event_sync(self, stream: str, data: Dict[str, Any], maxlen: int = 5000) -> None:
        client = self._get_sync_client()
        fields: Dict[Any, Any] = {
            k: json.dumps(v, default=str) if isinstance(v, (dict, list, bool)) else str(v)
            for k, v in data.items()
        }
        client.xadd(stream, fields, maxlen=maxlen, approximate=True)

    # Key-Value
    async def set_kv(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        await self.connect()
        assert self._async_client is not None
        if ttl:
            await self._async_client.set(key, value, ex=ttl)
        else:
            await self._async_client.set(key, value)

    def set_kv_sync(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        client = self._get_sync_client()
        if ttl:
            client.set(key, value, ex=ttl)
        else:
            client.set(key, value)

    async def get_kv(self, key: str) -> Optional[str]:
        await self.connect()
        assert self._async_client is not None
        value = await self._async_client.get(key)
        return _as_text(value)

    def get_kv_sync(self, key: str) -> Optional[str]:
        client = self._get_sync_client()
        return _as_text(client.get(key))

    async def delete_kv(self, key: str) -> None:
        await self.connect()
        assert self._async_client is not None
        await self._async_client.delete(key)

    def delete_kv_sync(self, key: str) -> None:
        client = self._get_sync_client()
        client.delete(key)

    async def incr_kv(self, key: str, ttl: Optional[int] = None) -> int:
        await self.connect()
        assert self._async_client is not None
        res = await self._async_client.eval(LUA_INCR_KV, 1, key, str(int(ttl or 0)))
        return int(res)

    def incr_kv_sync(self, key: str, ttl: Optional[int] = None) -> int:
        client = self._get_sync_client()
        res = client.eval(LUA_INCR_KV, 1, key, str(int(ttl or 0)))
        return int(res)

    async def scan_keys(self, pattern: str) -> List[str]:
        await self.connect()
        assert self._async_client is not None
        keys: List[str] = []
        cur = 0
        while True:
            cur, batch = await self._async_client.scan(cursor=cur, match=pattern, count=100)
            keys.extend(_as_text(item) or "" for item in batch)
            if cur == 0:
                break
        return keys

    def scan_keys_sync(self, pattern: str) -> List[str]:
        client = self._get_sync_client()
        keys: List[str] = []
        cur = 0
        while True:
            cur, batch = client.scan(cursor=cur, match=pattern, count=100)
            keys.extend(_as_text(item) or "" for item in batch)
            if cur == 0:
                break
        return keys

    # Leases & Locks
    async def acquire_lease(self, key: str, owner_id: str, ttl_seconds: int = 30, **kwargs) -> bool:
        await self.connect()
        assert self._async_client is not None
        actual_ttl = kwargs.get("ttl", ttl_seconds)
        ok = await self._async_client.set(key, owner_id, nx=True, ex=actual_ttl)
        return bool(ok)

    async def renew_lease(self, key: str, owner_id: str, ttl_seconds: int = 30, **kwargs) -> bool:
        await self.connect()
        assert self._async_client is not None
        actual_ttl = kwargs.get("ttl", ttl_seconds)
        res = await self._async_client.eval(LUA_RENEW_LEASE, 1, key, owner_id, str(actual_ttl))
        return bool(res == 1)

    async def release_lease(self, key: str, owner_id: str) -> bool:
        await self.connect()
        assert self._async_client is not None
        res = await self._async_client.eval(LUA_RELEASE_LEASE, 1, key, owner_id)
        return bool(res == 1)

    # RPC
    async def rpc_call(self, queue: str, payload: Dict[str, Any], timeout: float = 3.5) -> Dict[str, Any]:
        await self.connect()
        assert self._async_client is not None
        req_id = secrets.token_hex(10)
        reply_queue = f"tt:rpc:reply:{req_id}"
        msg = dict(payload)
        msg["_reply_to"] = reply_queue
        msg["_req_id"] = req_id

        await self._async_client.rpush(queue, json.dumps(msg, default=str))

        try:
            wait_timeout = max(1, int(math.ceil(timeout)))
            item = await asyncio.wait_for(
                self._async_client.blpop(reply_queue, timeout=wait_timeout),
                timeout=timeout + 0.5,
            )
            if item and len(item) == 2:
                return json.loads(item[1])
            return {"ok": False, "error": "RPC Timeout (keine Antwort empfangen)"}
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"RPC Timeout nach {timeout}s"}
        except Exception as exc:
            return {"ok": False, "error": f"RPC Fehler: {exc}"}
        finally:
            try:
                await self._async_client.delete(reply_queue)
            except Exception:
                pass

    async def rpc_listen(self, queue: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        await self.connect()
        assert self._async_client is not None
        client = self._async_client

        async def _worker():
            while self._running:
                try:
                    res = await client.blpop(queue, timeout=1)
                    if res and len(res) == 2:
                        raw_data = res[1]
                        req = json.loads(raw_data)
                        reply_to = req.get("_reply_to")
                        reply_payload = handler(req)
                        if asyncio.iscoroutine(reply_payload):
                            reply_payload = await reply_payload

                        if reply_to and reply_payload is not None:
                            await client.rpush(reply_to, json.dumps(reply_payload, default=str))
                            await client.expire(reply_to, 30)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    if self._running:
                        logger.error("Fehler im RPC-Listener auf %s: %s", queue, exc)
                        await asyncio.sleep(0.5)

        task = asyncio.create_task(_worker())
        self._sub_tasks.append(task)
