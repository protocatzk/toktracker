import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx

try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.client.errors import AgeRestrictedError, UserOfflineError
    from TikTokLive.client.web.web_settings import WebDefaults
    from TikTokLive.events import (
        ConnectEvent,
        DisconnectEvent,
        GiftEvent,
        LiveEndEvent,
        RoomUserSeqEvent,
    )
    TIKTOKLIVE_AVAILABLE = True
except ImportError:
    TIKTOKLIVE_AVAILABLE = False
    AgeRestrictedError = Exception  # type: ignore
    UserOfflineError = Exception  # type: ignore
    WebDefaults = None  # type: ignore

from config import config
from database import (
    end_stream_session,
    get_settings,
    record_gift_event,
    start_stream_session,
    update_stream_session_metrics,
    update_streamer_runtime_state,
)

logger = logging.getLogger("tiktok_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Falls ein EulerStream Sign-API-Key in .env / Umgebungsvariablen hinterlegt ist, global setzen
if TIKTOKLIVE_AVAILABLE and WebDefaults is not None and config.has_sign_api_key:
    WebDefaults.tiktok_sign_api_key = config.tiktok_sign_api_key

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

KNOWN_GIFT_DIAMONDS: Dict[str, int] = {
    "rose": 1,
    "tiktok": 1,
    "gg": 1,
    "ice cream cone": 1,
    "finger heart": 5,
    "mic": 5,
    "rosa": 10,
    "perfume": 20,
    "doughnut": 30,
    "cap": 99,
    "little crown": 99,
    "hearts": 199,
    "corgi": 299,
    "boxing gloves": 299,
    "money gun": 500,
    "swan": 699,
    "galaxy": 1000,
    "fireworks": 1088,
    "whale diving": 2150,
    "motorcycle": 2988,
    "sports car": 7000,
    "sunset speedway": 10000,
    "falcon": 10999,
    "planet": 15000,
    "dragon flame": 26999,
    "lion": 29999,
    "tiktok universe": 44999,
}


def fetch_tiktok_user_info(username: str) -> Dict[str, Any]:
    """
    Fragt TikTok-Web-Endpoints (@username) ab, um Anzeigename, Avatar,
    Follower-Anzahl, Room-ID und aktuellen Live-Status zu ermitteln.
    Nutzt automatisch TIKTOK_SESSION_ID falls in .env konfiguriert.
    """
    clean_user = username.strip().lstrip("@").lower()
    result: Dict[str, Any] = {
        "username": clean_user,
        "display_name": clean_user,
        "avatar_url": "",
        "follower_count": 0,
        "room_id": "",
        "is_live": False,
        "title": "",
    }

    cookies = {}
    if config.has_tiktok_session:
        cookies["sessionid"] = config.tiktok_session_id
        cookies["sessionid_ss"] = config.tiktok_session_id
        cookies["sid_tt"] = config.tiktok_session_id
        if config.tiktok_target_idc:
            cookies["tt-target-idc"] = config.tiktok_target_idc

    try:
        url = f"https://www.tiktok.com/@{clean_user}"
        with httpx.Client(
            headers=DEFAULT_HEADERS,
            cookies=cookies,
            proxy=config.tiktok_web_proxy,
            follow_redirects=True,
            timeout=8.0,
        ) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                match = re.search(
                    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                    resp.text,
                    re.DOTALL,
                )
                if match:
                    data = json.loads(match.group(1))
                    user_detail = (
                        data.get("__DEFAULT_SCOPE__", {})
                        .get("webapp.user-detail", {})
                        .get("userInfo", {})
                    )
                    user_obj = user_detail.get("user", {})
                    stats_obj = user_detail.get("stats", {})

                    if user_obj:
                        result["display_name"] = user_obj.get("nickname") or clean_user
                        result["avatar_url"] = (
                            user_obj.get("avatarLarger")
                            or user_obj.get("avatarMedium")
                            or user_obj.get("avatarThumb")
                            or ""
                        )
                        room_id = str(user_obj.get("roomId") or "")
                        result["room_id"] = room_id if room_id and room_id != "0" else ""
                        result["is_live"] = bool(result["room_id"])
                    if stats_obj:
                        result["follower_count"] = int(
                            stats_obj.get("followerCount") or 0
                        )
    except Exception as exc:
        logger.debug("TikTok Profil-Abfrage Fallback für %s: %s", clean_user, exc)

    return result


@dataclass
class PendingStreak:
    """Zwischenspeicher für laufende Combo-/Streak-Geschenke (falls repeat_end wegen Disconnect ausbleibt)."""
    streamer_id: int
    session_id: Optional[int]
    sender_user_id: str
    sender_username: str
    sender_nickname: str
    is_super_fan: bool
    gift_id: int
    gift_name: str
    gift_icon_url: str
    diamond_count: int
    repeat_count: int
    combo_count: int
    group_id: str
    room_fan_tickets: int
    event_uid: str
    updated_at: float = field(default_factory=time.monotonic)


@dataclass
class WorkerDiagnostics:
    """Laufzeit-Telemetrie pro überwachtem Streamer."""
    streamer_id: int
    username: str
    state: str = "stopped"
    auto_reconnect: bool = True
    authenticated_session: bool = False
    room_id: str = ""
    session_id: Optional[int] = None
    connected_since: Optional[str] = None
    last_event_at: Optional[str] = None
    last_message: str = "Bereit"
    last_error: str = ""
    current_viewers: int = 0
    peak_viewers: int = 0
    room_fan_tickets: int = 0
    reconnect_attempts: int = 0
    gifts_received_session: int = 0
    coins_received_session: int = 0


class StreamerWorker:
    STREAK_TIMEOUT_SECONDS = 12.0

    def __init__(
        self,
        streamer_id: int,
        username: str,
        auto_reconnect: bool = True,
    ) -> None:
        self.streamer_id = streamer_id
        self.username = username.strip().lstrip("@").lower()
        self.diag = WorkerDiagnostics(
            streamer_id=streamer_id,
            username=self.username,
            auto_reconnect=auto_reconnect,
            authenticated_session=config.has_tiktok_session,
        )
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[Any] = None
        self._gift_catalog_cache: Dict[int, Tuple[str, int, str]] = {}
        self._pending_streaks: Dict[str, PendingStreak] = {}
        self._recent_logs: Deque[Dict[str, str]] = deque(maxlen=50)

    def _log(self, level: str, message: str) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self.diag.last_message = message
            self._recent_logs.appendleft(
                {"timestamp": ts, "level": level, "message": message}
            )
        if level == "ERROR":
            logger.error("[@%s] %s", self.username, message)
        else:
            logger.info("[@%s] %s", self.username, message)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "streamer_id": self.diag.streamer_id,
                "username": self.diag.username,
                "is_running": self.is_alive(),
                "state": self.diag.state,
                "auto_reconnect": self.diag.auto_reconnect,
                "authenticated_session": self.diag.authenticated_session,
                "room_id": self.diag.room_id,
                "session_id": self.diag.session_id,
                "connected_since": self.diag.connected_since,
                "last_event_at": self.diag.last_event_at,
                "last_message": self.diag.last_message,
                "last_error": self.diag.last_error,
                "current_viewers": self.diag.current_viewers,
                "peak_viewers": self.diag.peak_viewers,
                "room_fan_tickets": self.diag.room_fan_tickets,
                "reconnect_attempts": self.diag.reconnect_attempts,
                "gifts_received_session": self.diag.gifts_received_session,
                "coins_received_session": self.diag.coins_received_session,
                "pending_streaks_count": len(self._pending_streaks),
                "logs": list(self._recent_logs)[:15],
            }

    def start(self, auto_reconnect: Optional[bool] = None) -> None:
        with self._lock:
            if auto_reconnect is not None:
                self.diag.auto_reconnect = auto_reconnect
            if self.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name=f"TikTokWorker-{self.username}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self.diag.state = "stopped"
            client = self._client
            loop = self._loop

        if client is not None and loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
            except Exception as exc:
                logger.debug("Disconnect-Signal Fehler für @%s: %s", self.username, exc)

        self._flush_all_pending_streaks()
        if self.diag.session_id:
            end_stream_session(self.streamer_id, self.diag.session_id)
            self.diag.session_id = None

        update_streamer_runtime_state(
            self.username,
            is_live=False,
            is_tracking=False,
            auto_monitor=False,
            current_viewers=0,
        )
        self._log("INFO", "Worker gestoppt.")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop

        try:
            loop.run_until_complete(self._supervisor_loop())
        except Exception as exc:
            self._log("ERROR", f"Unerwarteter Worker-Abbruch: {exc}")
        finally:
            self._flush_all_pending_streaks()
            if self.diag.session_id:
                end_stream_session(self.streamer_id, self.diag.session_id)
                self.diag.session_id = None
            update_streamer_runtime_state(
                self.username,
                is_live=False,
                is_tracking=False,
                current_viewers=0,
            )
            with self._lock:
                self._client = None
                self._loop = None
                if self.diag.state != "stopped":
                    self.diag.state = "stopped"
            try:
                loop.close()
            except Exception:
                pass

    def _create_configured_client(self) -> Any:
        """
        Erstellt eine TikTokLiveClient-Instanz und injiziert Session-Cookies
        (`sessionid` + `tt-target-idc`) sowie optionale Proxies aus der .env / Umgebung.
        """
        web_proxy = httpx.Proxy(config.tiktok_web_proxy) if config.tiktok_web_proxy else None
        client = TikTokLiveClient(
            unique_id=f"@{self.username}",
            web_proxy=web_proxy,
        )
        if config.has_tiktok_session:
            client.web.set_session(
                session_id=config.tiktok_session_id,
                tt_target_idc=config.tiktok_target_idc or "eu-ttp2",
            )
            with self._lock:
                self.diag.authenticated_session = True
        return client

    async def _start_client_with_age_bypass(self, client: Any) -> Any:
        """
        Startet die TikTokLive-Verbindung.
        - Ohne hinterlegte `TIKTOK_SESSION_ID` wird `fetch_room_info=False` genutzt, da
          TikTokLive v7.0.1 bei altersbeschränkten (18+) Streams sonst einen `AgeRestrictedError`
          wirft, obwohl der WebSocket-Stream über den Sign-Server trotzdem empfangen werden kann!
        - Falls trotz Session ein `AgeRestrictedError` beim Abrufen der Room-Info auftritt,
          fällt der Worker automatisch auf `fetch_room_info=False` zurück.
        """
        use_room_info = bool(config.has_tiktok_session)
        try:
            return await client.start(
                process_connect_events=True,
                compress_ws_events=True,
                fetch_room_info=use_room_info,
                fetch_gift_info=True,
                fetch_live_check=True,
            )
        except AgeRestrictedError:
            self._log(
                "INFO",
                "18+ Stream erkannt (AgeRestrictedError bei Room-Info) -> Verbinde im Bypass-Modus (fetch_room_info=False)...",
            )
            resolved_room_id = getattr(client, "_room_id", None) or None
            return await client.start(
                process_connect_events=True,
                compress_ws_events=True,
                fetch_room_info=False,
                fetch_gift_info=False,
                fetch_live_check=False,
                room_id=int(resolved_room_id) if resolved_room_id else None,
            )

    async def _supervisor_loop(self) -> None:
        backoff = 5.0

        while not self._stop_event.is_set():
            with self._lock:
                self.diag.state = "connecting"

            auth_hint = " (mit Session-Cookie)" if config.has_tiktok_session else " (anonym / 18+ Bypass aktiv)"
            self._log("INFO", f"Prüfe Live-Status & verbinde mit TikTok Webcast{auth_hint}...")

            update_streamer_runtime_state(
                self.username,
                is_tracking=True,
                auto_monitor=self.diag.auto_reconnect,
            )

            client = self._create_configured_client()
            with self._lock:
                self._client = client

            self._register_handlers(client)

            try:
                ws_task = await self._start_client_with_age_bypass(client)
                backoff = 5.0
                self.diag.reconnect_attempts = 0

                streak_watchdog = asyncio.create_task(self._streak_watchdog_loop())
                try:
                    await ws_task
                finally:
                    streak_watchdog.cancel()
                    self._flush_all_pending_streaks()

            except UserOfflineError:
                with self._lock:
                    self.diag.state = "polling_offline"
                    self.diag.current_viewers = 0
                if self.diag.session_id:
                    end_stream_session(self.streamer_id, self.diag.session_id)
                    self.diag.session_id = None

                update_streamer_runtime_state(
                    self.username,
                    is_live=False,
                    is_tracking=self.diag.auto_reconnect,
                    current_viewers=0,
                    last_error="",
                )

                if not self.diag.auto_reconnect or self._stop_event.is_set():
                    self._log("INFO", "Streamer ist offline (Einmal-Check beendet).")
                    break

                poll_sec = max(15, int(get_settings().get("poll_interval_seconds", 45)))
                self._log(
                    "INFO",
                    f"Streamer aktuell offline – nächster Live-Check in {poll_sec}s.",
                )
                await self._interruptible_sleep(float(poll_sec))
                continue

            except Exception as exc:
                err_name = type(exc).__name__
                err_text = f"{err_name}: {exc}"
                with self._lock:
                    self.diag.last_error = err_text
                    self.diag.reconnect_attempts += 1
                    self.diag.state = "backoff" if self.diag.auto_reconnect else "error"

                self._log("ERROR", f"Webcast-Fehler ({err_name}): {exc}")
                update_streamer_runtime_state(
                    self.username,
                    is_live=False,
                    current_viewers=0,
                    last_error=err_text[:240],
                )

                if not self.diag.auto_reconnect or self._stop_event.is_set():
                    break

                wait_s = min(120.0, backoff)
                self._log("INFO", f"Reconnect-Versuch in {int(wait_s)}s...")
                await self._interruptible_sleep(wait_s)
                backoff = min(120.0, backoff * 1.8)
                continue

            finally:
                try:
                    await client.close()
                except Exception:
                    pass
                with self._lock:
                    self._client = None

            if not self.diag.auto_reconnect or self._stop_event.is_set():
                break

            poll_sec = max(15, int(get_settings().get("poll_interval_seconds", 45)))
            await self._interruptible_sleep(float(poll_sec))

    async def _interruptible_sleep(self, seconds: float) -> None:
        end_time = time.monotonic() + seconds
        while not self._stop_event.is_set() and time.monotonic() < end_time:
            await asyncio.sleep(min(0.5, end_time - time.monotonic()))

    async def _streak_watchdog_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(2.0)
            self._flush_expired_streaks()

    def _register_handlers(self, client: Any) -> None:
        @client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent) -> None:
            room_id = str(getattr(client, "room_id", "") or "")
            room_info = getattr(client, "room_info", None) or {}
            gift_info = getattr(client, "gift_info", None)

            self._cache_gift_catalog(gift_info)

            title = ""
            display_name = None
            avatar_url = None
            if isinstance(room_info, dict):
                title = str(room_info.get("title") or "")
                owner = room_info.get("owner") or {}
                if isinstance(owner, dict):
                    display_name = owner.get("nickname")
                    avatar_thumb = owner.get("avatar_thumb") or {}
                    if isinstance(avatar_thumb, dict):
                        urls = avatar_thumb.get("url_list") or []
                        if urls:
                            avatar_url = urls[0]

            session_id = start_stream_session(
                streamer_id=self.streamer_id,
                room_id=room_id,
                title=title,
            )

            now_iso = datetime.now().isoformat(timespec="seconds")
            with self._lock:
                self.diag.state = "connected"
                self.diag.room_id = room_id
                self.diag.session_id = session_id
                self.diag.connected_since = now_iso
                self.diag.last_event_at = now_iso
                self.diag.last_error = ""
                self.diag.gifts_received_session = 0
                self.diag.coins_received_session = 0

            update_streamer_runtime_state(
                self.username,
                is_live=True,
                is_tracking=True,
                room_id=room_id,
                display_name=display_name,
                avatar_url=avatar_url,
                last_error="",
            )
            self._log("INFO", f"Verbunden mit Live-Stream (Room {room_id}, Session #{session_id}).")

        @client.on(RoomUserSeqEvent)
        async def on_room_user_seq(event: RoomUserSeqEvent) -> None:
            viewers = int(getattr(event, "total", 0) or 0)
            now_iso = datetime.now().isoformat(timespec="seconds")
            with self._lock:
                self.diag.current_viewers = viewers
                self.diag.peak_viewers = max(self.diag.peak_viewers, viewers)
                self.diag.last_event_at = now_iso
                sess_id = self.diag.session_id

            update_streamer_runtime_state(self.username, current_viewers=viewers)
            if sess_id:
                update_stream_session_metrics(sess_id, viewer_count=viewers)

        @client.on(LiveEndEvent)
        async def on_live_end(event: LiveEndEvent) -> None:
            self._flush_all_pending_streaks()
            with self._lock:
                sess_id = self.diag.session_id
                self.diag.session_id = None
                self.diag.current_viewers = 0
            if sess_id:
                end_stream_session(self.streamer_id, sess_id)
            update_streamer_runtime_state(
                self.username, is_live=False, current_viewers=0
            )
            self._log("INFO", "Streamer hat den Live-Stream beendet (LiveEndEvent).")

        @client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent) -> None:
            self._flush_all_pending_streaks()
            with self._lock:
                self.diag.current_viewers = 0
            update_streamer_runtime_state(
                self.username, is_live=False, current_viewers=0
            )
            self._log("INFO", "WebSocket-Verbindung getrennt.")

        @client.on(GiftEvent)
        async def on_gift(event: GiftEvent) -> None:
            try:
                self._process_gift_event(event)
            except Exception as exc:
                self._log("ERROR", f"Fehler bei GiftEvent-Verarbeitung: {exc}")

    def _cache_gift_catalog(self, gift_info: Any) -> None:
        if not isinstance(gift_info, dict):
            return
        gifts = gift_info.get("gifts") or gift_info.get("data", {}).get("gifts") or []
        if not isinstance(gifts, list):
            return
        for g in gifts:
            if not isinstance(g, dict):
                continue
            gid = int(g.get("id") or 0)
            if not gid:
                continue
            gname = str(g.get("name") or f"Gift #{gid}")
            diamonds = int(g.get("diamond_count") or 0)
            icon_url = ""
            icon_obj = g.get("icon") or g.get("image") or {}
            if isinstance(icon_obj, dict):
                urls = icon_obj.get("url_list") or []
                if urls:
                    icon_url = str(urls[0])
            self._gift_catalog_cache[gid] = (gname, diamonds, icon_url)

    def _extract_gift_metadata(self, event: Any) -> Dict[str, Any]:
        gift = getattr(event, "gift", None)
        gift_id = int(getattr(event, "gift_id", 0) or getattr(gift, "id", 0) or 0)
        gift_name = str(getattr(gift, "name", "") or "")
        diamond_count = int(getattr(gift, "diamond_count", 0) or 0)
        gift_icon_url = ""

        icon_obj = getattr(gift, "icon", None) or getattr(gift, "image", None)
        if icon_obj is not None:
            url_list = getattr(icon_obj, "url_list", None) or []
            if url_list:
                gift_icon_url = str(url_list[0])

        if gift_id in self._gift_catalog_cache:
            cat_name, cat_diamonds, cat_icon = self._gift_catalog_cache[gift_id]
            if not gift_name:
                gift_name = cat_name
            if diamond_count <= 0:
                diamond_count = cat_diamonds
            if not gift_icon_url:
                gift_icon_url = cat_icon

        if not gift_name:
            gift_name = f"Gift #{gift_id}" if gift_id else "TikTok Gift"

        if diamond_count <= 0:
            diamond_count = KNOWN_GIFT_DIAMONDS.get(gift_name.lower(), 1)

        repeat_count = max(1, int(getattr(event, "repeat_count", 1) or 1))
        combo_count = max(1, int(getattr(event, "combo_count", repeat_count) or repeat_count))
        group_id = str(getattr(event, "group_id", "") or "")
        room_fan_tickets = int(getattr(event, "room_fan_ticket_count", 0) or 0)

        user = getattr(event, "user", None)
        sender_user_id = str(getattr(user, "id", "") or "")
        sender_username = str(
            getattr(user, "unique_id", None)
            or getattr(user, "username", None)
            or sender_user_id
            or "viewer"
        )
        sender_nickname = str(getattr(user, "nickname", None) or sender_username)
        is_super_fan = bool(getattr(event, "user_is_super_fan", False))

        common = getattr(event, "common", None)
        msg_id = str(getattr(common, "msg_id", "") or getattr(event, "log_id", "") or "")

        streaking = bool(getattr(event, "streaking", False))

        streak_key = f"{sender_user_id or sender_username}:{gift_id}:{group_id or 'default'}"

        if group_id and group_id != "0":
            raw_uid = f"tt:{self.streamer_id}:{sender_user_id or sender_username}:{gift_id}:grp:{group_id}"
        elif msg_id:
            raw_uid = f"tt:{self.streamer_id}:msg:{msg_id}"
        else:
            raw_uid = (
                f"tt:{self.streamer_id}:{sender_username}:{gift_id}:"
                f"{repeat_count}:{int(time.time())}"
            )
        event_uid = hashlib.sha1(raw_uid.encode("utf-8")).hexdigest()

        return {
            "gift_id": gift_id,
            "gift_name": gift_name,
            "diamond_count": diamond_count,
            "gift_icon_url": gift_icon_url,
            "repeat_count": repeat_count,
            "combo_count": combo_count,
            "group_id": group_id,
            "room_fan_tickets": room_fan_tickets,
            "sender_user_id": sender_user_id,
            "sender_username": sender_username,
            "sender_nickname": sender_nickname,
            "is_super_fan": is_super_fan,
            "streaking": streaking,
            "streak_key": streak_key,
            "event_uid": event_uid,
        }

    def _process_gift_event(self, event: Any) -> None:
        meta = self._extract_gift_metadata(event)
        now_iso = datetime.now().isoformat(timespec="seconds")

        with self._lock:
            self.diag.last_event_at = now_iso
            if meta["room_fan_tickets"] > 0:
                self.diag.room_fan_tickets = max(
                    self.diag.room_fan_tickets, meta["room_fan_tickets"]
                )
            session_id = self.diag.session_id

        streak_key = meta["streak_key"]

        if meta["streaking"]:
            with self._lock:
                self._pending_streaks[streak_key] = PendingStreak(
                    streamer_id=self.streamer_id,
                    session_id=session_id,
                    sender_user_id=meta["sender_user_id"],
                    sender_username=meta["sender_username"],
                    sender_nickname=meta["sender_nickname"],
                    is_super_fan=meta["is_super_fan"],
                    gift_id=meta["gift_id"],
                    gift_name=meta["gift_name"],
                    gift_icon_url=meta["gift_icon_url"],
                    diamond_count=meta["diamond_count"],
                    repeat_count=meta["repeat_count"],
                    combo_count=meta["combo_count"],
                    group_id=meta["group_id"],
                    room_fan_tickets=meta["room_fan_tickets"],
                    event_uid=meta["event_uid"],
                    updated_at=time.monotonic(),
                )
            return

        with self._lock:
            self._pending_streaks.pop(streak_key, None)

        self._commit_gift(
            session_id=session_id,
            sender_user_id=meta["sender_user_id"],
            sender_username=meta["sender_username"],
            sender_nickname=meta["sender_nickname"],
            is_super_fan=meta["is_super_fan"],
            gift_id=meta["gift_id"],
            gift_name=meta["gift_name"],
            gift_icon_url=meta["gift_icon_url"],
            diamond_count=meta["diamond_count"],
            repeat_count=meta["repeat_count"],
            combo_count=meta["combo_count"],
            group_id=meta["group_id"],
            room_fan_tickets=meta["room_fan_tickets"],
            event_uid=meta["event_uid"],
        )

    def _commit_gift(
        self,
        session_id: Optional[int],
        sender_user_id: str,
        sender_username: str,
        sender_nickname: str,
        is_super_fan: bool,
        gift_id: int,
        gift_name: str,
        gift_icon_url: str,
        diamond_count: int,
        repeat_count: int,
        combo_count: int,
        group_id: str,
        room_fan_tickets: int,
        event_uid: str,
    ) -> None:
        record, created = record_gift_event(
            streamer_id=self.streamer_id,
            session_id=session_id,
            event_uid=event_uid,
            sender_user_id=sender_user_id,
            sender_username=sender_username,
            sender_nickname=sender_nickname,
            is_super_fan=is_super_fan,
            gift_id=gift_id,
            gift_name=gift_name,
            gift_icon_url=gift_icon_url,
            diamond_count=diamond_count,
            repeat_count=repeat_count,
            combo_count=combo_count,
            group_id=group_id,
            room_fan_tickets=room_fan_tickets,
            source="tiktoklive",
        )
        if created and record:
            coins = int(record["total_coins"])
            with self._lock:
                self.diag.gifts_received_session += repeat_count
                self.diag.coins_received_session += coins
            self._log(
                "INFO",
                f"Gift erfasst: {repeat_count}x {gift_name} ({coins} Coins) von @{sender_username}",
            )

    def _flush_expired_streaks(self) -> None:
        now = time.monotonic()
        expired: List[PendingStreak] = []
        with self._lock:
            keys_to_pop = [
                k
                for k, ps in self._pending_streaks.items()
                if (now - ps.updated_at) >= self.STREAK_TIMEOUT_SECONDS
            ]
            for k in keys_to_pop:
                expired.append(self._pending_streaks.pop(k))

        for ps in expired:
            self._commit_gift(
                session_id=ps.session_id,
                sender_user_id=ps.sender_user_id,
                sender_username=ps.sender_username,
                sender_nickname=ps.sender_nickname,
                is_super_fan=ps.is_super_fan,
                gift_id=ps.gift_id,
                gift_name=ps.gift_name,
                gift_icon_url=ps.gift_icon_url,
                diamond_count=ps.diamond_count,
                repeat_count=ps.repeat_count,
                combo_count=ps.combo_count,
                group_id=ps.group_id,
                room_fan_tickets=ps.room_fan_tickets,
                event_uid=ps.event_uid,
            )

    def _flush_all_pending_streaks(self) -> None:
        with self._lock:
            pending = list(self._pending_streaks.values())
            self._pending_streaks.clear()

        for ps in pending:
            self._commit_gift(
                session_id=ps.session_id,
                sender_user_id=ps.sender_user_id,
                sender_username=ps.sender_username,
                sender_nickname=ps.sender_nickname,
                is_super_fan=ps.is_super_fan,
                gift_id=ps.gift_id,
                gift_name=ps.gift_name,
                gift_icon_url=ps.gift_icon_url,
                diamond_count=ps.diamond_count,
                repeat_count=ps.repeat_count,
                combo_count=ps.combo_count,
                group_id=ps.group_id,
                room_fan_tickets=ps.room_fan_tickets,
                event_uid=ps.event_uid,
            )


class StreamerMonitorManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workers: Dict[str, StreamerWorker] = {}

    def is_tracking(self, username: str) -> bool:
        clean = username.strip().lstrip("@").lower()
        with self._lock:
            worker = self._workers.get(clean)
            return bool(worker and worker.is_alive())

    def get_status(self, username: str) -> str:
        clean = username.strip().lstrip("@").lower()
        with self._lock:
            worker = self._workers.get(clean)
            if not worker:
                return "Inaktiv"
            snap = worker.get_snapshot()
            return f"[{snap['state']}] {snap['last_message']}"

    def get_worker_diagnostics(self, username: str) -> Optional[Dict[str, Any]]:
        clean = username.strip().lstrip("@").lower()
        with self._lock:
            worker = self._workers.get(clean)
            return worker.get_snapshot() if worker else None

    def get_all_diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            snapshots = [w.get_snapshot() for w in self._workers.values()]
        active_count = sum(1 for s in snapshots if s["is_running"])
        connected_count = sum(1 for s in snapshots if s["state"] == "connected")
        return {
            "tiktoklive_available": TIKTOKLIVE_AVAILABLE,
            "env_config": config.public_summary(),
            "workers_total": len(snapshots),
            "workers_running": active_count,
            "workers_connected": connected_count,
            "workers": snapshots,
        }

    def start_tracking(
        self, streamer_id: int, username: str, auto_reconnect: bool = True
    ) -> Dict[str, Any]:
        clean = username.strip().lstrip("@").lower()
        if not TIKTOKLIVE_AVAILABLE:
            return {
                "ok": False,
                "message": "TikTokLive-Bibliothek ist nicht installiert.",
            }

        with self._lock:
            worker = self._workers.get(clean)
            if worker and worker.is_alive():
                return {
                    "ok": True,
                    "message": f"Worker für @{clean} läuft bereits.",
                    "diagnostics": worker.get_snapshot(),
                }
            worker = StreamerWorker(
                streamer_id=streamer_id,
                username=clean,
                auto_reconnect=auto_reconnect,
            )
            self._workers[clean] = worker

        worker.start(auto_reconnect=auto_reconnect)
        return {
            "ok": True,
            "message": f"TikTokLive-Worker für @{clean} gestartet (Auto-Monitor={auto_reconnect}).",
            "diagnostics": worker.get_snapshot(),
        }

    def stop_tracking(self, username: str) -> Dict[str, Any]:
        clean = username.strip().lstrip("@").lower()
        with self._lock:
            worker = self._workers.get(clean)

        if worker:
            worker.stop()

        return {
            "ok": True,
            "message": f"Worker für @{clean} gestoppt.",
        }

    def stop_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
        for w in workers:
            w.stop()


monitor_manager = StreamerMonitorManager()
