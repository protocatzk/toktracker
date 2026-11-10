import asyncio
import html
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from telegram.request import HTTPXRequest

try:
    from telegram import (
        BotCommand,
        BotCommandScopeAllGroupChats,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeDefault,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Update,
        WebAppInfo,
    )
    from telegram.constants import ChatType, ParseMode
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    PTB_AVAILABLE = True
except ImportError:
    PTB_AVAILABLE = False
    Update = Any  # type: ignore
    ContextTypes = Any  # type: ignore
    InlineKeyboardButton = Any  # type: ignore
    InlineKeyboardMarkup = Any  # type: ignore
    WebAppInfo = Any  # type: ignore

from config import BASE_DIR, config
from database import (
    add_streamer_alert,
    build_streamer_bot_report,
    check_telegram_user_access,
    get_all_streamers_summary,
    get_dashboard_overview,
    get_db,
    get_donor_details,
    get_donor_radar_data,
    get_network_loyalty_and_overlap,
    get_recent_whale_gifts,
    get_settings,
    get_streamer_by_id_or_username,
    get_telegram_access_mode,
    list_streamer_alert_subscriptions,
    list_telegram_users,
    mark_streamer_alert_notified,
    remove_streamer_alert,
    save_donor_crm,
    set_telegram_access_mode,
    toggle_donor_vip,
    upsert_streamer,
    upsert_telegram_user_permission,
)
from shared import bot_format as bf
from shared.auth_store import AdminAuthManager, admin_auth_manager
from shared.bot_format import BRAND as BOT_BRAND
from shared.bus import get_bus
from shared.contracts import CHANNEL_LIVE_STATUS
from shared.monitor_client import monitor_client as monitor_manager
from shared.permissions import (
    PERM_BOT_ADMIN_LOGIN,
    PERM_BOT_ANALYTICS_VIEW,
    PERM_BOT_CRM_EDIT,
    PERM_BOT_PUBLIC_VIEW,
    PERM_BOT_RADAR_VIEW,
    PERM_BOT_SETTINGS_MANAGE,
    PERM_BOT_STREAMERS_MANAGE,
    PERM_BOT_SYSTEM_VIEW,
    PERM_BOT_USERS_MANAGE,
    ROLE_USER,
    normalize_role,
    permissions_for,
    role_label,
)
from tiktok_service import fetch_tiktok_user_info

PICTURES_DIR = os.path.join(BASE_DIR, "pictures")
WELCOME_BANNER_PATH = os.path.join(PICTURES_DIR, "welcome_banner.jpg")
DAILY_REPORT_BANNER_PATH = os.path.join(PICTURES_DIR, "daily_report_banner.jpg")
BOT_AVATAR_PATH = os.path.join(PICTURES_DIR, "bot_avatar.jpg")

logger = logging.getLogger("telegram_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def generate_full_report_data(hours: int = 24, only_active: bool = False) -> Dict[str, Any]:
    """
    Erzeugt den vollständigen Bericht für alle Streamer (wird sowohl von der FastAPI-Route
    als auch vom Telegram-Bot für den 24h-Job genutzt).
    """
    cfg = get_settings()
    now = datetime.now()
    cutoff = (now - timedelta(hours=hours)).isoformat(timespec="seconds")

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM streamers ORDER BY username ASC").fetchall()

    cards: List[Dict[str, Any]] = []
    for r in rows:
        s_dict = dict(r)
        uname = s_dict["username"]
        is_tracking = monitor_manager.is_tracking(uname)
        diag = monitor_manager.get_worker_diagnostics(uname)
        worker_state = (
            diag["state"]
            if diag
            else ("live" if s_dict.get("is_live") else "stopped")
        )
        card = build_streamer_bot_report(
            streamer_row=s_dict,
            hours=hours,
            is_tracking_active=is_tracking,
            worker_state=worker_state,
        )
        if only_active and card["period_coins"] == 0 and not card["is_live"]:
            continue
        cards.append(card)

    cards.sort(key=lambda c: (c["period_coins"], c["alltime_coins"]), reverse=True)

    total_period_coins = sum(c["period_coins"] for c in cards)
    total_period_usd_net = round(sum(c["period_usd_net"] for c in cards), 2)
    total_period_eur_net = round(sum(c["period_eur_net"] for c in cards), 2)
    total_period_usd_gross = round(sum(c["period_usd_gross"] for c in cards), 2)
    total_period_eur_gross = round(sum(c["period_eur_gross"] for c in cards), 2)
    total_gifts_sent = sum(c["period_gifts_sent"] for c in cards)
    live_now = sum(1 for c in cards if c["is_live"])

    md_lines = [
        f"*{BOT_BRAND} – Streamer Einnahmen-Report ({hours}h)*",
        f"Stand: `{now.strftime('%d.%m.%Y %H:%M')}`",
        f"Gesamt Netto ({hours}h): `{total_period_eur_net:,.2f} €` (`${total_period_usd_net:,.2f}`)",
        f"Gesamt Coins ({hours}h): `{total_period_coins:,}` ({total_gifts_sent:,} Gifts)",
        f"Streamer: {len(cards)} überwacht ({live_now} aktuell LIVE)",
        "────────────────────────",
    ]
    html_lines = [
        bf.eyebrow(f"{bf.BRAND} · REPORT / {hours}H"),
        bf.kv_table(
            [
                ("STAND", now.strftime("%d.%m.%Y %H:%M")),
                ("NETTO", f"€ {total_period_eur_net:,.2f}"),
                ("USD", f"$ {total_period_usd_net:,.2f}"),
                ("COINS", f"{total_period_coins:,}"),
                ("GIFTS", f"{total_gifts_sent:,}"),
                ("STREAMER", f"{len(cards)} · {live_now} LIVE"),
            ]
        ),
        bf.rule(),
    ]

    for idx, c in enumerate(cards, start=1):
        status_dot = "●" if c["is_live"] else "○"
        top_g = (
            f"{c['top_gifts'][0]['gift_name']} ({c['top_gifts'][0]['total_coins']:,})"
            if c["top_gifts"]
            else "-"
        )
        top_u = (
            f"@{c['top_gifters'][0]['sender_username']} ({c['top_gifters'][0]['total_coins']:,})"
            if c["top_gifters"]
            else "-"
        )

        md_lines.append(
            f"*{idx:02d}  {c['display_name']}* (@{c['username']}) {status_dot}\n"
            f"   • {hours}h Netto: *{c['period_eur_net']:,.2f} €* (`${c['period_usd_net']:,.2f}`) | `{c['period_coins']:,}` Coins\n"
            f"   • Top Gift: {top_g} | Top Gifter: {top_u}\n"
            f"   • All-Time: {c['alltime_eur_net']:,.2f} € ({c['alltime_coins']:,} Coins)"
        )
        html_lines.append(
            f"<b>{idx:02d}  {html.escape(str(c['display_name']))}</b> (@{html.escape(str(c['username']))}) {status_dot}\n"
            f"▪ {hours}H: <b>{c['period_eur_net']:,.2f} €</b> (<code>${c['period_usd_net']:,.2f}</code>) · <code>{c['period_coins']:,}</code> Coins\n"
            f"▪ TOP: {html.escape(top_g)} · {html.escape(top_u)}\n"
            f"▪ ALL: {c['alltime_eur_net']:,.2f} € · {c['alltime_coins']:,} Coins"
        )

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "period_hours": hours,
        "cutoff_timestamp": cutoff,
        "currency_primary": cfg["currency_primary"],
        "totals": {
            "streamers_count": len(cards),
            "live_count": live_now,
            "period_coins": total_period_coins,
            "period_gifts_sent": total_gifts_sent,
            "period_usd_net": total_period_usd_net,
            "period_eur_net": total_period_eur_net,
            "period_usd_gross": total_period_usd_gross,
            "period_eur_gross": total_period_eur_gross,
        },
        "streamers": cards,
        "telegram_markdown": "\n\n".join(md_lines),
        "telegram_html": "\n\n".join(html_lines),
    }


class TelegramBotService:
    """
    Vollständig entkoppelter Telegram-Bot-Service auf Basis des offiziellen
    `python-telegram-bot` (v22+) SDKs inkl. `JobQueue` für den automatischen 24h-Bericht,
    Gruppen-Support (`/befehl@BotName` & `@BotName befehl`), mehrstufiger
    Zugriffskontrolle (`whitelist` per `[@]username` oder `id` vs. `public`) sowie
    Telegram-basierter Admin-Panel-Authentifizierung (`/login` & 1-Klick-Freigabe).
    """

    def __init__(self) -> None:
        self._app: Optional[Any] = None
        self._state: str = "disabled"
        self._last_error: str = ""
        self._bot_username: str = ""
        self._bot_username_raw: str = ""
        self._started_at: Optional[str] = None
        self._last_report_sent_at: Optional[str] = None
        self._last_disk_alert_time: float = 0.0
        self._disk_alert_active: bool = False
        self._logs: Deque[Dict[str, str]] = deque(maxlen=40)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._live_alert_subscribed: bool = False

    def _log(self, level: str, msg: str) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        self._logs.appendleft({"timestamp": ts, "level": level, "message": msg})
        if level == "ERROR":
            logger.error("%s", msg)
        else:
            logger.info("%s", msg)

    def get_diagnostics(self) -> Dict[str, Any]:
        try:
            mode = get_telegram_access_mode()
            users = list_telegram_users()
            allowed_count = sum(1 for u in users if int(u.get("is_allowed", 0)) == 1)
            pending_count = sum(1 for u in users if int(u.get("is_allowed", 0)) == 0)
        except Exception:
            mode = config.telegram_access_mode
            allowed_count = 0
            pending_count = 0

        return {
            "sdk_available": PTB_AVAILABLE,
            "state": self._state,
            "bot_username": self._bot_username,
            "has_token": bool(config.telegram_bot_token),
            "default_chat_id": config.telegram_chat_id,
            "access_mode": mode,
            "group_support": True,
            "allowed_users_count": allowed_count,
            "pending_users_count": pending_count,
            "started_at": self._started_at,
            "last_report_sent_at": self._last_report_sent_at,
            "last_error": self._last_error,
            "pictures": {
                "welcome_banner": os.path.exists(WELCOME_BANNER_PATH),
                "daily_report_banner": os.path.exists(DAILY_REPORT_BANNER_PATH),
                "bot_avatar": os.path.exists(BOT_AVATAR_PATH),
            },
            "logs": list(self._logs)[:15],
        }

    async def start(self) -> None:
        if not PTB_AVAILABLE:
            self._state = "disabled"
            self._log("INFO", "python-telegram-bot SDK nicht installiert – Bot deaktiviert.")
            return

        token = (config.telegram_bot_token or "").strip()
        if not token or token.startswith("123456789:"):
            self._state = "disabled"
            self._log(
                "INFO",
                "Kein TELEGRAM_BOT_TOKEN in .env hinterlegt – Bot im Standby (API & Web laufen normal).",
            )
            return

        self._state = "starting"
        self._last_error = ""
        try:
            request = HTTPXRequest(
                connection_pool_size=16,
                read_timeout=20.0,
                write_timeout=20.0,
                connect_timeout=10.0,
                pool_timeout=10.0,
                )
            builder = Application.builder().token(token).request(request)
            self._app = builder.build()

            # Lese- & Analyse-Befehle
            self._app.add_handler(CommandHandler(["start", "help"], self._cmd_help))
            self._app.add_handler(CommandHandler(["app", "miniapp"], self._cmd_miniapp))
            self._app.add_handler(CommandHandler(["id", "whoami"], self._cmd_whoami))
            self._app.add_handler(CommandHandler(["overview", "dashboard", "finanzen"], self._cmd_overview))
            self._app.add_handler(CommandHandler(["radar", "whales_radar"], self._cmd_radar))
            self._app.add_handler(CommandHandler(["whales", "whale_alerts", "alerts"], self._cmd_whales))
            self._app.add_handler(CommandHandler(["donor", "dossier", "spender"], self._cmd_donor))
            self._app.add_handler(CommandHandler(["vip", "vips"], self._cmd_vip))
            self._app.add_handler(CommandHandler(["loyalty", "switchers", "frontenwechsler"], self._cmd_loyalty))
            self._app.add_handler(CommandHandler(["streamers", "channels", "liste"], self._cmd_streamers))
            self._app.add_handler(CommandHandler(["gifts", "geschenke", "ticker"], self._cmd_gifts))
            self._app.add_handler(CommandHandler("report", self._cmd_report))
            self._app.add_handler(CommandHandler(["streamer", "stats"], self._cmd_streamer))
            self._app.add_handler(CommandHandler("status", self._cmd_status))

            # Schreib- & Verwaltungs-Befehle (immer nur für Admins)
            self._app.add_handler(CommandHandler("login", self._cmd_admin_login))
            self._app.add_handler(CommandHandler("add", self._cmd_add_streamer))
            self._app.add_handler(CommandHandler("track", self._cmd_track_streamer))
            self._app.add_handler(CommandHandler("stop", self._cmd_stop_streamer))
            self._app.add_handler(CommandHandler("allow", self._cmd_allow_user))
            self._app.add_handler(CommandHandler("revoke", self._cmd_revoke_user))
            self._app.add_handler(CommandHandler("users", self._cmd_list_users))
            self._app.add_handler(CommandHandler("mode", self._cmd_access_mode))
            self._app.add_handler(CommandHandler(["alert", "livealert", "livealerts"], self._cmd_alert))

            # Callback-Handler für 1-Klick Admin-Login-Freigabe
            self._app.add_handler(
                CallbackQueryHandler(self._on_login_callback, pattern=r"^admin_login_(approve|reject):")
            )
            # Callback-Handler für interaktive Buttons (Overview, Radar, Whales, Donor VIP, Loyalty etc.)
            self._app.add_handler(
                CallbackQueryHandler(
                    self._on_interactive_callback,
                    pattern=r"^(overview_period|radar_tier|whales_min|donor_vip_toggle|donor_refresh|loyalty_days|streamers_list|gifts_refresh|overview_streamer):"
                )
            )

            # Gruppen-Mention-Handler
            self._app.add_handler(
                MessageHandler(
                    filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
                    self._on_group_mention,
                )
            )

            await self._app.initialize()
            bot_me = await self._app.bot.get_me()
            self._bot_username_raw = (bot_me.username or "").lower()
            self._bot_username = f"@{bot_me.username}" if bot_me.username else str(bot_me.id)

            await self._register_bot_commands()

            await self._app.start()
            self._loop = asyncio.get_running_loop()
            await self._ensure_live_alert_subscription()
            if self._app.updater:
                await self._app.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES,
                )

            if self._app.job_queue and config.telegram_chat_id:
                self._app.job_queue.run_repeating(
                    self._scheduled_24h_report_job,
                    interval=timedelta(hours=24),
                    first=timedelta(hours=24),
                    name="daily_24h_tiktok_report",
                )
                self._log(
                    "INFO",
                    f"24h-Automatik-Bericht für Chat-ID {config.telegram_chat_id} geplant.",
                )

            if self._app.job_queue:
                self._app.job_queue.run_repeating(
                    self._scheduled_disk_health_monitor_job,
                    interval=timedelta(minutes=15),
                    first=timedelta(seconds=45),
                    name="disk_health_monitor",
                )
                self._log(
                    "INFO",
                    "Speicherplatz-Überwachung aktiv (Intervall: alle 15 Min, Alarm bei >=85%).",
                )

            self._state = "running"
            self._started_at = datetime.now().isoformat(timespec="seconds")
            self._log(
                "INFO",
                f"toktracker Telegram-Bot ({self._bot_username}) gestartet [Modus: {get_telegram_access_mode().upper()}, Admin-Auth: AKTIV].",
            )

        except Exception as exc:
            self._state = "error"
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._log(
                "ERROR",
                f"Telegram-Bot konnte nicht gestartet werden ({self._last_error}). FastAPI & Web laufen weiter.",
            )
            await self._safe_cleanup()

    async def _register_bot_commands(self) -> None:
        if not self._app:
            return
        commands = [
            BotCommand("start", "Hauptmenü & Befehlsübersicht öffnen"),
            BotCommand("overview", "Finanz- & Performance-Dashboard (Heute, 24h, 7d)"),
            BotCommand("radar", "Spender-Radar & Rangliste nach Tiers (Whales, Sharks)"),
            BotCommand("whales", "Live-Stream der neuesten Großspenden"),
            BotCommand("donor", "Spender-Dossier, Stammkanal & VIP (<username>)"),
            BotCommand("vip", "VIP-Watchlist anzeigen oder Spender markieren"),
            BotCommand("loyalty", "Frontenwechsler & Streamer-Überschneidungen"),
            BotCommand("streamers", "Alle Kanäle mit Live-Status & Zuschauern"),
            BotCommand("gifts", "Live Gift-Ticker der letzten Geschenke"),
            BotCommand("streamer", "Einzelabfrage für einen Streamer (<username>)"),
            BotCommand("report", "24h-Gesamtbericht aller überwachten Streamer"),
            BotCommand("status", "Laufzeit-Status aller aktiven TikTokLive-Worker"),
            BotCommand("app", "Mini-App: Live-Matches & Einnahmen"),
            BotCommand("id", "Eigene Telegram-ID, Gruppen-ID & Berechtigung"),
            BotCommand("login", "[Admin] Einmal-Code für das Web-Admin-Panel erzeugen"),
            BotCommand("add", "[Admin] Streamer hinzufügen & Live-Worker starten"),
            BotCommand("track", "[Admin] Live-Überwachung für einen Streamer starten"),
            BotCommand("stop", "[Admin] Live-Überwachung für einen Streamer stoppen"),
            BotCommand("allow", "[Admin] Nutzer freischalten (viewer|user|moderator|admin)"),
            BotCommand("revoke", "[Admin] Nutzer-Berechtigung entziehen / sperren"),
            BotCommand("users", "[Admin] Freigeschaltete Nutzer & offene Anfragen auflisten"),
            BotCommand("mode", "[Admin] Zugriffsmodus wechseln (whitelist oder public)"),
            BotCommand("alert", "[Admin] Live-Alert für Streamer in diesem Chat verwalten"),
        ]
        try:
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        except Exception as exc:
            self._log("INFO", f"Hinweis bei set_my_commands: {exc}")

    async def _ensure_live_alert_subscription(self) -> None:
        """Abonniert Live-Status-Events des Ingest-Workers (einmal pro Prozess)."""
        if self._live_alert_subscribed:
            return
        try:
            await get_bus().subscribe(CHANNEL_LIVE_STATUS, self._on_live_status_event)
            self._live_alert_subscribed = True
            self._log("INFO", "Live-Status-Alerts abonniert.")
        except Exception as exc:
            self._log("ERROR", f"Live-Status-Alerts konnten nicht abonniert werden: {exc}")

    def _on_live_status_event(self, payload: Dict[str, Any]) -> None:
        """Sync-Handler: leitet das Event thread-sicher in den Bot-Event-Loop."""
        if self._state != "running" or not self._loop or self._loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._send_live_status_alert(payload),
                self._loop,
            )
        except Exception as exc:
            self._log("ERROR", f"Live-Status-Event konnte nicht eingeplant werden: {exc}")

    async def _send_live_status_alert(self, payload: Dict[str, Any]) -> None:
        """Verschickt einen Live-Alert an alle abonnierten Chats eines Streamers."""
        if not self._app or self._state != "running":
            return
        try:
            streamer_id = int(payload.get("streamer_id") or 0)
            session_id = int(payload.get("session_id") or 0)
        except (TypeError, ValueError):
            return
        if not streamer_id or not session_id:
            return

        username = str(payload.get("username") or "").strip().lstrip("@")
        if not username:
            return
        display_name = str(payload.get("display_name") or username)
        title = str(payload.get("title") or "").strip()
        avatar_url = str(payload.get("avatar_url") or "").strip()

        alerts = await asyncio.to_thread(
            list_streamer_alert_subscriptions,
            streamer_id=streamer_id,
        )
        if not alerts:
            return

        stream_url = f"https://www.tiktok.com/@{username}/live"
        text_lines = [
            bf.eyebrow("LIVE-ALERT"),
            f"{bf.LIVE} · <b>@{html.escape(username)}</b>",
            f"<b>{html.escape(display_name)}</b>",
        ]
        if title:
            text_lines.append(f"▪ {html.escape(title)}")
        text_lines.append(f'<a href="{stream_url}">Stream öffnen →</a>')
        text = "\n".join(text_lines)
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("▸ STREAM ÖFFNEN", url=stream_url)]]
        )

        for alert in alerts:
            try:
                last_session = alert.get("last_notified_session_id")
                if last_session is not None and int(last_session) == session_id:
                    continue
                chat_id = int(alert.get("chat_id"))
                sent = False
                if avatar_url.startswith(("http://", "https://")):
                    try:
                        await self._app.bot.send_photo(
                            chat_id=chat_id,
                            photo=avatar_url,
                            caption=text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup,
                        )
                        sent = True
                    except Exception:
                        sent = False
                if not sent:
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=markup,
                        disable_web_page_preview=False,
                    )
                await asyncio.to_thread(
                    mark_streamer_alert_notified,
                    int(alert["id"]),
                    session_id,
                )
                self._log(
                    "INFO",
                    f"Live-Alert für @{username} an Chat {chat_id} gesendet.",
                )
            except Exception as exc:
                self._log(
                    "ERROR",
                    f"Live-Alert für @{username} an Chat {alert.get('chat_id')} fehlgeschlagen: {exc}",
                )

    async def stop(self) -> None:
        if not self._app:
            return
        self._log("INFO", "Stoppe Telegram-Bot...")
        await self._safe_cleanup()
        self._state = "stopped"

    async def _safe_cleanup(self) -> None:
        if not self._app:
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
        except Exception:
            pass
        try:
            if self._app.running:
                await self._app.stop()
        except Exception:
            pass
        try:
            await self._app.shutdown()
        except Exception:
            pass
        self._app = None

    # =================================================================
    # TELEGRAM ADMIN-PANEL AUTHENTIFIZIERUNG (OTP + 1-KLICK FREIGABE)
    # =================================================================

    def _resolve_admin_chat_ids(self, identifier_hint: Optional[str] = None) -> List[int]:
        """
        Ermittelt alle bekannten privaten Telegram-Chat-IDs von berechtigten Administratoren.
        """
        users = list_telegram_users()
        hint = (identifier_hint or "").strip().lstrip("@").lower()
        matched_ids: Set[int] = set()
        all_admin_ids: Set[int] = set()

        for cid in config.env_allowed_telegram_ids:
            if cid > 0:
                all_admin_ids.add(int(cid))
                if hint and str(cid) == hint:
                    matched_ids.add(int(cid))

        for u in users:
            if int(u.get("is_allowed", 0)) == 1 and u.get("role") == "admin":
                tg_id = u.get("telegram_id")
                uname = str(u.get("username") or "").strip().lstrip("@").lower()
                if tg_id and int(tg_id) > 0:
                    all_admin_ids.add(int(tg_id))
                    if hint and (hint == uname or hint == str(tg_id)):
                        matched_ids.add(int(tg_id))

        if hint and matched_ids:
            return sorted(matched_ids)
        return sorted(all_admin_ids)

    async def send_admin_login_challenge(
        self,
        identifier_hint: Optional[str] = None,
        client_info: str = "Web-Browser",
    ) -> Dict[str, Any]:
        """
        Erzeugt eine Login-Challenge und sendet den 6-stelligen Einmal-Code sowie
        einen Inline-Freigabe-Button an die hinterlegten Admin-Telegram-Chats.
        """
        challenge = admin_auth_manager.create_challenge(client_info=client_info)
        cid = challenge["challenge_id"]
        code = challenge["code"]

        if self._state != "running" or not self._app:
            self._log(
                "INFO",
                f"[Admin-Login] Lokaler Einmal-Code erzeugt: {code} (Telegram-Bot Status: {self._state})",
            )
            return {
                "ok": True,
                "challenge_id": cid,
                "delivered_count": 0,
                "bot_running": False,
                "bot_username": self._bot_username,
                "expires_in": AdminAuthManager.CHALLENGE_TTL_SECONDS,
                "message": (
                    "Telegram-Bot ist aktuell nicht verbunden. "
                    "Der Einmal-Code wurde im Server-Log ausgegeben (oder nutze das Admin-Passwort aus der .env)."
                ),
            }

        target_ids = await asyncio.to_thread(self._resolve_admin_chat_ids, identifier_hint)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✓ LOGIN FREIGEBEN",
                        callback_data=f"admin_login_approve:{cid}",
                    ),
                    InlineKeyboardButton(
                        "× ABLEHNEN",
                        callback_data=f"admin_login_reject:{cid}",
                    ),
                ]
            ]
        )

        msg_html = (
            bf.eyebrow("ADMIN-LOGIN")
            + "\n<b>LOGIN-ANFRAGE</b>\n"
            + bf.kv_table(
                [
                    ("CODE", code),
                    ("ANFRAGE", client_info),
                    ("GÜLTIG", "10 MINUTEN"),
                ]
            )
            + "\n<i>Code im Browser eingeben oder Login direkt bestätigen.</i>"
        )

        delivered = 0
        for chat_id in target_ids:
            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=msg_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                delivered += 1
            except Exception as exc:
                self._log("INFO", f"Login-Code konnte nicht an Admin-Chat {chat_id} gesendet werden: {exc}")

        if delivered > 0:
            self._log("INFO", f"Admin-Login-Code an {delivered} Admin-Chat(s) gesendet.")
            return {
                "ok": True,
                "challenge_id": cid,
                "delivered_count": delivered,
                "bot_running": True,
                "bot_username": self._bot_username,
                "expires_in": AdminAuthManager.CHALLENGE_TTL_SECONDS,
                "message": f"Einmal-Code & Freigabe-Anfrage an {delivered} Admin-Chat(s) gesendet.",
            }

        return {
            "ok": True,
            "challenge_id": cid,
            "delivered_count": 0,
            "bot_running": True,
            "bot_username": self._bot_username,
            "expires_in": AdminAuthManager.CHALLENGE_TTL_SECONDS,
            "message": (
                f"Öffne den Telegram-Bot {self._bot_username or ''} und sende den Befehl /login, "
                "um deinen 6-stelligen Einmal-Code direkt im Chat zu erhalten."
            ),
        }

    async def _cmd_admin_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Erlaubt einem Admin, direkt im Telegram-Chat mit `/login` einen frischen
        6-stelligen Einmal-Code abzurufen oder eine offene Browser-Anfrage freizugeben.
        """
        if not update.effective_message or not update.effective_user:
            return
        access = await self._authorize(update, require_permission=PERM_BOT_ADMIN_LOGIN)
        if not access:
            return

        tg_user = update.effective_user
        admin_label = f"@{tg_user.username}" if tg_user.username else str(tg_user.id)

        pending = admin_auth_manager.get_latest_pending_challenge()
        if pending:
            pending["admin_label"] = admin_label
            challenge = pending
        else:
            challenge = admin_auth_manager.create_challenge(
                client_info=f"Telegram /login ({admin_label})",
                admin_label=admin_label,
            )

        cid = challenge["challenge_id"]
        code = challenge["code"]
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✓ BROWSER-SITZUNG FREIGEBEN",
                        callback_data=f"admin_login_approve:{cid}",
                    )
                ]
            ]
        )

        await update.effective_message.reply_text(
            bf.eyebrow("ADMIN-LOGIN")
            + "\n<b>EINMAL-CODE</b>\n\n"
            f"<code>{code}</code>\n\n"
            "<i>Unter <code>/login</code> im Browser eingeben (10 Minuten gültig) "
            "oder die geöffnete Sitzung unten freigeben.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    async def _on_login_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        tg_user = update.effective_user
        access = await asyncio.to_thread(
            check_telegram_user_access,
            int(tg_user.id),
            tg_user.username or "",
            tg_user.first_name or "",
            int(update.effective_chat.id) if update.effective_chat else int(tg_user.id),
            "",
        )

        access_perms = permissions_for(
            normalize_role(access.get("role")),
            1 if access.get("allowed") else 0,
        )
        if not access.get("allowed") or PERM_BOT_ADMIN_LOGIN not in access_perms:
            await query.answer("× Nur Administratoren dürfen Logins freigeben.", show_alert=True)
            return

        action_part, cid = query.data.split(":", 1)
        admin_label = f"@{tg_user.username}" if tg_user.username else (tg_user.first_name or str(tg_user.id))

        if action_part == "admin_login_approve":
            ch = admin_auth_manager.approve_challenge(cid, admin_label=admin_label)
            if not ch:
                await query.answer("Diese Login-Anfrage ist bereits abgelaufen oder wurde verwendet.", show_alert=True)
                return
            await query.answer("Admin-Login freigegeben!")
            self._log("INFO", f"Admin-Panel Login per 1-Klick freigegeben von {admin_label}.")
            try:
                await query.edit_message_text(
                    f"<b>LOGIN FREIGEGEBEN</b>\n\n"
                    f"▪ Bestätigt durch: <code>{html.escape(admin_label)}</code>\n"
                    f"▪ Zeitpunkt: <code>{datetime.now().strftime('%H:%M:%S')}</code>\n\n"
                    "<i>Der Browser wird automatisch weitergeleitet.</i>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        else:
            admin_auth_manager.reject_challenge(cid, admin_label=admin_label)
            await query.answer("Login-Anfrage abgelehnt.")
            self._log("INFO", f"Admin-Panel Login abgelehnt von {admin_label}.")
            try:
                await query.edit_message_text(
                    f"<b>LOGIN-ANFRAGE ABGELEHNT</b> · <code>{html.escape(admin_label)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    # =================================================================
    # ZUGRIFFSKONTROLLE & AUTORISIERUNG (PRIVATCHAT & GRUPPEN)
    # =================================================================

    @staticmethod
    def _is_group_chat(update: Update) -> bool:
        if not update.effective_chat:
            return False
        return update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

    async def _authorize(
        self,
        update: Update,
        require_admin: bool = False,
        require_permission: Optional[str] = None,
        require_any_permission: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not update.effective_user or not update.effective_message or not update.effective_chat:
            return None

        tg_user = update.effective_user
        tg_chat = update.effective_chat
        access = await asyncio.to_thread(
            check_telegram_user_access,
            int(tg_user.id),
            tg_user.username or "",
            tg_user.first_name or "",
            int(tg_chat.id),
            tg_chat.title or "",
        )

        uname_display = (
            f"@{tg_user.username}"
            if tg_user.username
            else (tg_user.first_name or str(tg_user.id))
        )
        chat_context = (
            f" in Gruppe '{tg_chat.title}' ({tg_chat.id})"
            if self._is_group_chat(update)
            else ""
        )

        if not access["allowed"]:
            self._log(
                "INFO",
                f"Zugriff verweigert für {uname_display} (ID: {tg_user.id}){chat_context} [Modus: {access['mode']}].",
            )
            allow_hint = (
                f"<code>/allow @{html.escape(tg_user.username)}</code> oder <code>/allow {tg_user.id}</code>"
                if tg_user.username
                else f"<code>/allow {tg_user.id}</code>"
            )
            await update.effective_message.reply_text(
                bf.eyebrow("ZUGRIFF BESCHRÄNKT")
                + "\n<b>WHITELIST AKTIV</b>\n\n"
                "Du bist noch nicht für diesen Bot freigeschaltet.\n\n"
                + bf.kv_table(
                    [
                        ("USER-ID", str(tg_user.id)),
                        ("USERNAME", uname_display),
                    ]
                )
                + f"\n<i>Freischaltung über das Web-Interface, per Reply mit <code>/allow</code> oder {allow_hint}.</i>\n"
                + bf.footer(),
                parse_mode=ParseMode.HTML,
            )
            return None

        access["role"] = normalize_role(access.get("role"))
        access["permissions"] = set(permissions_for(access["role"], 1 if access["allowed"] else 0))

        if require_admin and not access["is_admin"]:
            self._log(
                "INFO",
                f"Admin-Befehl verweigert für {uname_display} (ID: {tg_user.id}){chat_context}.",
            )
            await update.effective_message.reply_text(
                "<b>KEINE BERECHTIGUNG</b>\nDieser Verwaltungsbefehl ist Administratoren vorbehalten.",
                parse_mode=ParseMode.HTML,
            )
            return None

        missing_permission = None
        if require_permission and require_permission not in access["permissions"]:
            missing_permission = require_permission
        elif require_any_permission and not (access["permissions"] & set(require_any_permission)):
            missing_permission = ", ".join(sorted(require_any_permission))

        if missing_permission:
            self._log(
                "INFO",
                f"Befehl verweigert für {uname_display} (ID: {tg_user.id}){chat_context} "
                f"[Rolle: {access['role']}, fehlt: {missing_permission}].",
            )
            await update.effective_message.reply_text(
                "<b>KEINE BERECHTIGUNG</b>\nDeine Rolle "
                f"<code>{html.escape(role_label(access['role']))}</code> darf diesen Befehl nicht ausführen.",
                parse_mode=ParseMode.HTML,
            )
            return None

        return access

    async def _send_with_optional_banner(
        self,
        bot: Any,
        chat_id: str | int,
        html_text: str,
        banner_path: str,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        chunks = list(bf.chunk_message(html_text))
        single = len(chunks) == 1

        if os.path.exists(banner_path):
            with open(banner_path, "rb") as photo_file:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    caption=chunks[0] if single and len(chunks[0]) <= 1000 else None,
                    parse_mode=ParseMode.HTML if single and len(chunks[0]) <= 1000 else None,
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=reply_markup if single and len(chunks[0]) <= 1000 else None,
                )
            if single and len(chunks[0]) <= 1000:
                return

        for index, chunk in enumerate(chunks):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=reply_to_message_id if index == 0 else None,
                reply_markup=reply_markup if index == len(chunks) - 1 else None,
                disable_web_page_preview=True,
            )

    async def send_report_now(
        self, chat_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        target_chat = (chat_id or config.telegram_chat_id or "").strip()
        if self._state != "running" or not self._app:
            return {
                "ok": False,
                "error": f"Telegram-Bot läuft aktuell nicht (Status: {self._state}). Bitte TELEGRAM_BOT_TOKEN in .env prüfen.",
            }
        if not target_chat:
            return {
                "ok": False,
                "error": "Keine TELEGRAM_CHAT_ID in .env angegeben.",
            }

        try:
            report = await asyncio.to_thread(generate_full_report_data, hours, False)
            await self._send_with_optional_banner(
                bot=self._app.bot,
                chat_id=target_chat,
                html_text=report["telegram_html"],
                banner_path=DAILY_REPORT_BANNER_PATH,
            )
            self._last_report_sent_at = datetime.now().isoformat(timespec="seconds")
            self._log("INFO", f"{hours}h-Report manuell an Chat {target_chat} gesendet.")
            return {"ok": True, "chat_id": target_chat, "hours": hours}
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            self._log("ERROR", f"Fehler beim Senden des Reports: {err}")
            return {"ok": False, "error": err}

    async def _scheduled_24h_report_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        target_chat = (config.telegram_chat_id or "").strip()
        if not target_chat:
            return
        try:
            report = await asyncio.to_thread(generate_full_report_data, 24, False)
            await self._send_with_optional_banner(
                bot=context.bot,
                chat_id=target_chat,
                html_text=report["telegram_html"],
                banner_path=DAILY_REPORT_BANNER_PATH,
            )
            self._last_report_sent_at = datetime.now().isoformat(timespec="seconds")
            self._log("INFO", f"Automatischer 24h-Bericht an Chat {target_chat} gesendet.")
        except Exception as exc:
            self._log("ERROR", f"Fehler im 24h-Report-Job: {exc}")

    async def _scheduled_disk_health_monitor_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            from system_service import get_system_health

            health = await asyncio.to_thread(get_system_health, True)
            disk = health.get("host", {}).get("disk", {})
            pct = float(disk.get("percent", 0.0))
            free_gb = float(disk.get("free_gb", 0.0))
            total_gb = float(disk.get("total_gb", 0.0))
            used_gb = float(disk.get("used_gb", 0.0))

            now = time.time()
            if pct >= 85.0:
                if not self._disk_alert_active or (now - self._last_disk_alert_time) > 14400:
                    self._disk_alert_active = True
                    self._last_disk_alert_time = now

                    docker_info = health.get("docker", {})
                    containers = docker_info.get("containers", [])
                    volumes = docker_info.get("volumes", [])

                    cont_lines = []
                    for c in containers:
                        cont_lines.append(
                            f"▪ <b>{html.escape(c.get('name', ''))}</b> · "
                            f"<code>{c.get('memory_used_mb', 0)} MB</code> RAM "
                            f"({c.get('memory_percent', 0)}%) · "
                            f"<code>{c.get('cpu_percent', 0)}%</code> CPU"
                        )

                    vol_lines = []
                    for v in volumes[:4]:
                        vol_lines.append(
                            f"▪ <code>{html.escape(v.get('name', ''))}</code> · <b>{v.get('size_mb', 0):.1f} MB</b>"
                        )

                    msg = (
                        bf.eyebrow("WARNUNG · SPEICHERPLATZ")
                        + "\n<b>KRITISCHER SPEICHERPLATZ</b>\n"
                        + bf.kv_table(
                            [
                                ("DISK", f"{pct:.1f}% · {used_gb:.1f}/{total_gb:.1f} GB"),
                                ("FREI", f"{free_gb:.1f} GB"),
                            ]
                        )
                        + "\n"
                        + bf.eyebrow("DOCKER CONTAINER")
                        + "\n"
                        + ("\n".join(cont_lines) if cont_lines else "<i>Keine Container erfasst</i>")
                        + "\n\n"
                        + bf.eyebrow("VOLUMES")
                        + "\n"
                        + ("\n".join(vol_lines) if vol_lines else "<i>Keine Volumes</i>")
                        + "\n\n"
                        + "<i>Tipp: Ungenutzte Images/Build-Caches mit <code>docker system prune -a</code> bereinigen.</i>"
                    )

                    admin_ids = self._resolve_admin_chat_ids()
                    if config.telegram_chat_id:
                        try:
                            admin_ids.append(int(config.telegram_chat_id))
                        except Exception:
                            pass
                    for target_id in set(admin_ids):
                        try:
                            await context.bot.send_message(
                                chat_id=target_id,
                                text=msg,
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception as send_err:
                            self._log("DEBUG", f"Konnte Speicher-Warnung nicht an {target_id} senden: {send_err}")

            elif pct < 78.0 and self._disk_alert_active:
                self._disk_alert_active = False
                recovery_msg = (
                    bf.eyebrow("ENTWARNUNG · SPEICHERPLATZ")
                    + "\n\nSpeicherplatz wieder normalisiert.\n\n"
                    + bf.kv_table(
                        [
                            ("DISK", f"{pct:.1f}% BELEGT"),
                            ("FREI", f"{free_gb:.1f} GB / {total_gb:.1f} GB"),
                        ]
                    )
                )
                admin_ids = self._resolve_admin_chat_ids()
                if config.telegram_chat_id:
                    try:
                        admin_ids.append(int(config.telegram_chat_id))
                    except Exception:
                        pass
                for target_id in set(admin_ids):
                    try:
                        await context.bot.send_message(
                            chat_id=target_id,
                            text=recovery_msg,
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

        except Exception as exc:
            self._log("DEBUG", f"Fehler im Disk-Health-Job: {exc}")

    # =================================================================
    # GRUPPEN-MENTION HANDLER
    # =================================================================

    async def _on_group_mention(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_message.text:
            return

        text = update.effective_message.text.strip()
        bot_tag = f"@{self._bot_username_raw}" if self._bot_username_raw else ""

        is_mentioned = bool(bot_tag and bot_tag in text.lower())
        is_reply_to_bot = bool(
            update.effective_message.reply_to_message
            and update.effective_message.reply_to_message.from_user
            and self._bot_username_raw
            and (update.effective_message.reply_to_message.from_user.username or "").lower()
            == self._bot_username_raw
        )

        if not is_mentioned and not is_reply_to_bot:
            return

        cleaned = text
        if bot_tag:
            for token in text.split():
                if token.lower().lstrip("/") == bot_tag:
                    cleaned = cleaned.replace(token, "", 1).strip()

        parts = cleaned.split()
        cmd = parts[0].lower().lstrip("/") if parts else "help"
        context.args = parts[1:] if len(parts) > 1 else []

        if cmd in ("report", "bericht"):
            await self._cmd_report(update, context)
        elif cmd in ("overview", "dashboard", "finanzen"):
            await self._cmd_overview(update, context)
        elif cmd in ("radar", "whales_radar"):
            await self._cmd_radar(update, context)
        elif cmd in ("whales", "whale_alerts", "alerts"):
            await self._cmd_whales(update, context)
        elif cmd in ("donor", "dossier", "spender"):
            await self._cmd_donor(update, context)
        elif cmd in ("vip", "vips"):
            await self._cmd_vip(update, context)
        elif cmd in ("loyalty", "switchers", "frontenwechsler"):
            await self._cmd_loyalty(update, context)
        elif cmd in ("streamers", "channels", "liste"):
            await self._cmd_streamers(update, context)
        elif cmd in ("gifts", "geschenke", "ticker"):
            await self._cmd_gifts(update, context)
        elif cmd in ("streamer", "stats", "info"):
            await self._cmd_streamer(update, context)
        elif cmd in ("status", "worker", "workers"):
            await self._cmd_status(update, context)
        elif cmd in ("id", "whoami"):
            await self._cmd_whoami(update, context)
        elif cmd == "login":
            await self._cmd_admin_login(update, context)
        elif cmd == "allow":
            await self._cmd_allow_user(update, context)
        elif cmd == "revoke":
            await self._cmd_revoke_user(update, context)
        elif cmd == "users":
            await self._cmd_list_users(update, context)
        elif cmd == "mode":
            await self._cmd_access_mode(update, context)
        else:
            await self._cmd_help(update, context)

    # =================================================================
    # TELEGRAM BOT COMMAND HANDLERS
    # =================================================================

    async def _cmd_whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.effective_message or not update.effective_chat:
            return
        tg_user = update.effective_user
        tg_chat = update.effective_chat
        access = await asyncio.to_thread(
            check_telegram_user_access,
            int(tg_user.id),
            tg_user.username or "",
            tg_user.first_name or "",
            int(tg_chat.id),
            tg_chat.title or "",
        )
        role_display = (
            role_label(access.get("role"))
            if access["allowed"]
            else "Gesperrt / Wartend"
        )
        profile_rows = [
            ("USER-ID", str(tg_user.id)),
            ("USERNAME", f"@{tg_user.username or '-'}"),
        ]
        if self._is_group_chat(update):
            profile_rows.extend(
                [
                    ("GRUPPE", tg_chat.title or "-"),
                    ("CHAT-ID", str(tg_chat.id)),
                ]
            )
        profile_rows.append(("STATUS", role_display.upper()))
        profile_rows.append(("MODUS", str(access["mode"]).upper()))
        await update.effective_message.reply_text(
            bf.eyebrow("PROFIL")
            + "\n"
            + bf.kv_table(profile_rows)
            + "\n"
            + bf.footer(),
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat or not update.effective_user:
            return
        access = await self._authorize(update, require_permission=PERM_BOT_PUBLIC_VIEW)
        if not access:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        is_grp = self._is_group_chat(update)

        perms = access.get("permissions", set())
        sections: List[str] = []

        identity_rows = [("USER-ID", str(user_id))]
        if is_grp:
            identity_rows.insert(0, ("CHAT-ID", str(chat_id)))
        identity_rows.append(("ROLLE", role_label(access.get("role")).upper()))
        identity_rows.append(("MODUS", str(access["mode"]).upper()))

        public_lines = [
            "▪ <code>/streamers</code> — Kanäle mit Live-Status &amp; Zuschauern",
            "▪ <code>/gifts [streamer]</code> — Gift-Ticker der letzten Geschenke",
            "▪ <code>/app</code> — Mini-App öffnen",
            "▪ <code>/id</code> — eigene User- und Gruppen-ID prüfen",
        ]
        sections.append(bf.eyebrow("01 / ÖFFENTLICH") + "\n" + "\n".join(public_lines))

        if PERM_BOT_ANALYTICS_VIEW in perms:
            sections.append(
                bf.eyebrow("02 / STATISTIK") + "\n"
                "▪ <code>/overview [heute|24h|7d|30d|all]</code> — Finanz-Dashboard\n"
                "▪ <code>/report [stunden]</code> — Gesamtbericht aller Streamer\n"
                "▪ <code>/streamer &lt;username&gt; [stunden]</code> — Detailbericht\n"
                "▪ <code>/status</code> — Laufzeit-Status der TikTokLive-Worker"
            )

        if PERM_BOT_RADAR_VIEW in perms:
            sections.append(
                bf.eyebrow("03 / RADAR") + "\n"
                "▪ <code>/radar [all|whale|shark|dolphin|vip]</code> — Spender-Radar\n"
                "▪ <code>/whales [min_coins]</code> — Feed der Großspenden\n"
                "▪ <code>/donor &lt;username&gt;</code> — Spender-Dossier\n"
                "▪ <code>/vip [add|remove &lt;user&gt;]</code> — VIP-Watchlist\n"
                "▪ <code>/loyalty [tage]</code> — Frontenwechsler &amp; Überschneidungen"
            )

        admin_lines: List[str] = []
        if PERM_BOT_ADMIN_LOGIN in perms:
            admin_lines.append("▪ <code>/login</code> — Einmal-Code für das Web-Panel")
        if PERM_BOT_STREAMERS_MANAGE in perms:
            admin_lines.append("▪ <code>/add &lt;username&gt;</code> — Streamer anlegen")
            admin_lines.append("▪ <code>/track</code> | <code>/stop &lt;username&gt;</code> — Worker steuern")
            admin_lines.append("▪ <code>/alert &lt;@username&gt;</code> — Live-Alert in diesem Chat")
        if PERM_BOT_USERS_MANAGE in perms:
            admin_lines.append("▪ <code>/allow &lt;id|@user&gt; [rolle]</code> — Nutzer freischalten")
            admin_lines.append("▪ <code>/revoke &lt;id|@user&gt;</code> — Zugriff entziehen")
            admin_lines.append("▪ <code>/users</code> — Nutzerliste &amp; Anfragen")
        if PERM_BOT_SETTINGS_MANAGE in perms:
            admin_lines.append("▪ <code>/mode &lt;whitelist|public&gt;</code> — Zugriffsmodus")
        if admin_lines:
            sections.append(bf.eyebrow("04 / VERWALTUNG") + "\n" + "\n".join(admin_lines))

        text = (
            bf.eyebrow("LIVE EARNINGS INTELLIGENCE")
            + "\n<b>WILLKOMMEN BEI TT-INTELLIGENCE</b>\n\n"
            "Echtzeit-Tracking von TikTok-Livestreams: Geschenke, Coins und "
            "Netto-Auszahlungen in <b>EUR (€)</b> und <b>USD ($)</b>.\n\n"
            + bf.kv_table(identity_rows)
            + "\n"
            + bf.rule()
            + "\n"
            + "\n\n".join(sections)
            + "\n\n"
            + bf.rule()
            + "\n"
            + bf.footer()
        )

        buttons = []
        webapp_url = (config.telegram_webapp_url or "").strip()
        if webapp_url:
            if webapp_url.lower().startswith("https://"):
                buttons.append([
                    InlineKeyboardButton(
                        text="▸ MINI-APP ÖFFNEN",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text="▸ WEB-APP ÖFFNEN",
                        url=webapp_url,
                    )
                ])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        await self._send_with_optional_banner(
            bot=context.bot,
            chat_id=chat_id,
            html_text=text,
            banner_path=WELCOME_BANNER_PATH,
            reply_to_message_id=update.effective_message.message_id if is_grp else None,
            reply_markup=reply_markup,
        )

    async def _cmd_miniapp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat:
            return
        access = await self._authorize(update, require_permission=PERM_BOT_PUBLIC_VIEW)
        if not access:
            return

        is_grp = self._is_group_chat(update)
        webapp_url = (config.telegram_webapp_url or "").strip()

        buttons = []
        if webapp_url:
            if webapp_url.lower().startswith("https://"):
                buttons.append([
                    InlineKeyboardButton(
                        text="▸ MINI-APP ÖFFNEN",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text="▸ WEB-APP ÖFFNEN",
                        url=webapp_url,
                    )
                ])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        text = (
            bf.eyebrow("MINI-APP")
            + "\n<b>TT-INTELLIGENCE MOBILE</b>\n\n"
            "Live-Battles, Punktestände und Einnahmen direkt in Telegram.\n\n"
            + bf.kv_table(
                [
                    ("LIVE-MATCHES", "PUNKTE · MVPS"),
                    ("EINNAHMEN", "NETTO € / $"),
                    ("MONITOR", "ZUSCHAUER · STATUS"),
                    ("RADAR", "WHALES · ALERTS"),
                ]
            )
            + "\n"
            + bf.rule()
        )
        if webapp_url:
            text += f"\n<code>{html.escape(webapp_url)}</code>\n\nTippe auf den Button, um die Mini-App zu starten."
        else:
            text += (
                "\n<i>Hinweis:</i> Es ist noch keine <code>TELEGRAM_WEBAPP_URL</code> hinterlegt.\n"
                f"Browser-Aufruf: <code>http://localhost:{config.app_port}/miniapp</code>\n\n"
                "Für die native Telegram-WebApp in der <code>.env</code> setzen:\n"
                "<code>TELEGRAM_WEBAPP_URL=https://deine-domain.de/miniapp</code>"
            )
        text += "\n" + bf.footer()

        await self._send_with_optional_banner(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            html_text=text,
            banner_path=WELCOME_BANNER_PATH,
            reply_to_message_id=update.effective_message.message_id if is_grp else None,
            reply_markup=reply_markup,
        )

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_ANALYTICS_VIEW):
            return

        hours = 24
        if context.args and context.args[0].isdigit():
            hours = max(1, min(720, int(context.args[0])))

        is_grp = self._is_group_chat(update)
        report = await asyncio.to_thread(generate_full_report_data, hours, False)
        await self._send_with_optional_banner(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            html_text=report["telegram_html"],
            banner_path=DAILY_REPORT_BANNER_PATH,
            reply_to_message_id=update.effective_message.message_id if is_grp else None,
        )

    async def _cmd_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_ANALYTICS_VIEW):
            return

        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/streamer &lt;username&gt; [stunden]</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        identifier = context.args[0].strip().lstrip("@")
        hours = 24
        if len(context.args) > 1 and context.args[1].isdigit():
            hours = max(1, min(8760, int(context.args[1])))

        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, identifier)
        if not s_row:
            await update.effective_message.reply_text(
                f"Streamer <code>@{html.escape(identifier)}</code> nicht in der Datenbank gefunden.",
                parse_mode=ParseMode.HTML,
            )
            return

        uname = s_row["username"]
        is_tracking = monitor_manager.is_tracking(uname)
        diag = monitor_manager.get_worker_diagnostics(uname)
        worker_state = diag["state"] if diag else ("live" if s_row.get("is_live") else "stopped")

        card = await asyncio.to_thread(
            build_streamer_bot_report,
            s_row,
            hours,
            is_tracking,
            worker_state,
        )

        live_str = bf.status(bool(card["is_live"])) if card["is_live"] else f"○ {card['worker_state'].upper()}"
        top_g = (
            " · ".join(
                f"{g['gift_name']} ({g['total_coins']:,})" for g in card["top_gifts"][:3]
            )
            or "Keine"
        )
        top_u = (
            " · ".join(
                f"@{u['sender_username']} ({u['total_coins']:,})"
                for u in card["top_gifters"][:3]
            )
            or "Keine"
        )

        msg = (
            bf.header(8, f"STREAMER · {card['display_name']}")
            + f"\n<b>@{html.escape(uname)}</b> · {live_str} · {card['current_viewers']:,} Viewer\n"
            + bf.kv_table(
                [
                    ("NETTO", f"€ {card['period_eur_net']:,.2f}"),
                    ("USD", f"$ {card['period_usd_net']:,.2f}"),
                    ("BRUTTO", f"€ {card['period_eur_gross']:,.2f}"),
                    ("COINS", f"{card['period_coins']:,}"),
                    ("GIFTS", f"{card['period_gifts_sent']:,} / {card['period_unique_gifters']} GIFTER"),
                    ("PEAK", f"{card['period_peak_viewers']:,}"),
                    ("ZEITRAUM", f"{hours}H"),
                ]
            )
            + f"\n<b>TOP GIFTS</b>\n{html.escape(top_g)}\n"
            + f"<b>TOP SPENDER</b>\n{html.escape(top_u)}\n"
            + bf.rule()
            + f"\nALL-TIME: <code>{card['alltime_eur_net']:,.2f} €</code> · <code>{card['alltime_coins']:,}</code> Coins\n"
            + bf.footer()
        )
        await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    @staticmethod
    def _format_relative_time(dt_val: Any) -> str:
        if not dt_val:
            return "nie"
        try:
            now = datetime.utcnow()
            if isinstance(dt_val, (int, float)):
                dt = datetime.utcfromtimestamp(dt_val)
            elif isinstance(dt_val, datetime):
                dt = dt_val.replace(tzinfo=None) if dt_val.tzinfo else dt_val
            elif isinstance(dt_val, str):
                clean = dt_val.replace("T", " ").replace("Z", "").split("+")[0].split(".")[0]
                dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
            else:
                return str(dt_val)

            diff = now - dt
            secs = max(0, int(diff.total_seconds()))
            if secs < 60:
                return f"vor {secs}s"
            mins = secs // 60
            if mins < 60:
                return f"vor {mins}m"
            hours = mins // 60
            if hours < 24:
                return f"vor {hours}h"
            days = hours // 24
            return f"vor {days}d"
        except Exception:
            return str(dt_val)

    # -----------------------------------------------------------------
    # INTERAKTIVE DASHBOARD & FINANZ-ÜBERSICHT (/overview)
    # -----------------------------------------------------------------
    def _format_overview_view(self, period: str = "today") -> Tuple[str, InlineKeyboardMarkup]:
        norm_period = period if period in ("today", "24h", "7d", "30d", "all") else "today"
        data = get_dashboard_overview(period=norm_period, force_refresh=True)
        totals = data.get("totals", {})
        streamers = data.get("streamers", [])

        period_labels = {
            "today": "Heute (seit 00:00 Uhr)",
            "24h": "Letzte 24 Stunden",
            "7d": "Letzte 7 Tage",
            "30d": "Letzte 30 Tage",
            "all": "Gesamt (All-Time)",
        }
        p_label = period_labels.get(norm_period, norm_period)

        eur_net = totals.get("eur_net", 0.0)
        usd_net = totals.get("usd_net", 0.0)
        eur_gross = totals.get("eur_gross", 0.0)
        usd_gross = totals.get("usd_gross", 0.0)
        total_coins = totals.get("total_coins", 0)
        live_count = totals.get("live_count", 0)
        streamer_count = totals.get("streamer_count", 0)
        total_gifts = totals.get("total_gifts_sent", 0)

        lines = [
            bf.header(1, "FINANZEN"),
            bf.kv_table(
                [
                    ("ZEITRAUM", p_label.upper()),
                    ("NETTO", f"€ {eur_net:,.2f}"),
                    ("USD", f"$ {usd_net:,.2f}"),
                    ("BRUTTO", f"€ {eur_gross:,.2f}"),
                    ("BRUTTO USD", f"$ {usd_gross:,.2f}"),
                    ("COINS", f"{total_coins:,}"),
                    ("GIFTS", f"{total_gifts:,}"),
                    ("STREAMER", f"{live_count} LIVE / {streamer_count}"),
                ]
            ),
            bf.rule(),
            bf.eyebrow(f"TOP STREAMER · {p_label}"),
        ]

        sorted_streamers = sorted(streamers, key=lambda s: int(s.get("total_coins") or 0), reverse=True)
        active_sorted = [s for s in sorted_streamers if int(s.get("total_coins") or 0) > 0]
        if not active_sorted:
            lines.append("<i>Keine Einnahmen in diesem Zeitraum verzeichnet.</i>")
        else:
            for idx, s in enumerate(active_sorted[:5], start=1):
                live_badge = " ●" if s.get("is_live") else ""
                s_coins = int(s.get("total_coins") or 0)
                s_eur = float(s.get("eur_net") or 0.0)
                lines.append(
                    f"<b>{bf.rank(idx)}</b>  {html.escape(s.get('display_name') or s['username'])}{live_badge}  "
                    f"<code>{s_eur:,.2f} €</code> · <code>{s_coins:,}</code>"
                )

        lines.append("\n" + bf.footer())
        text = "\n".join(lines)

        buttons = [
            [
                InlineKeyboardButton(f"{'✓ ' if norm_period == 'today' else ''}HEUTE", callback_data="overview_period:today"),
                InlineKeyboardButton(f"{'✓ ' if norm_period == '24h' else ''}24H", callback_data="overview_period:24h"),
                InlineKeyboardButton(f"{'✓ ' if norm_period == '7d' else ''}7 TAGE", callback_data="overview_period:7d"),
            ],
            [
                InlineKeyboardButton(f"{'✓ ' if norm_period == '30d' else ''}30 TAGE", callback_data="overview_period:30d"),
                InlineKeyboardButton(f"{'✓ ' if norm_period == 'all' else ''}GESAMT", callback_data="overview_period:all"),
                InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"overview_period:{norm_period}"),
            ],
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_overview(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_ANALYTICS_VIEW):
            return

        period = "today"
        if context.args:
            arg = context.args[0].lower().strip()
            if arg in ("today", "24h", "7d", "30d", "all"):
                period = arg
            elif arg in ("heute", "day"):
                period = "today"
            elif arg in ("woche", "week"):
                period = "7d"
            elif arg in ("monat", "month"):
                period = "30d"
            elif arg in ("gesamt", "total"):
                period = "all"

        text, markup = await asyncio.to_thread(self._format_overview_view, period)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # SPENDER-RADAR & CRM (/radar)
    # -----------------------------------------------------------------
    def _format_radar_view(self, tier: str = "all", period: str = "all") -> Tuple[str, InlineKeyboardMarkup]:
        norm_tier = tier if tier in ("all", "whale", "shark", "dolphin") else "all"
        min_tier_param = None if norm_tier == "all" else norm_tier
        data = get_donor_radar_data(period=period, min_tier=min_tier_param, limit=10, offset=0)
        kpis = data.get("kpis", {})
        donors = data.get("donors", [])

        tier_labels = {
            "all": "ALLE SPENDER",
            "whale": "WHALE ≥ 10K",
            "shark": "SHARK ≥ 2.5K",
            "dolphin": "DOLPHIN ≥ 500",
        }
        tier_title = tier_labels.get(norm_tier, "ALLE SPENDER")

        lines = [
            bf.header(2, "SPENDER-RADAR"),
            bf.kv_table(
                [
                    ("FILTER", tier_title),
                    ("WHALES", str(kpis.get("whales", 0))),
                    ("SHARKS", str(kpis.get("sharks", 0))),
                    ("DOLPHINS", str(kpis.get("dolphins", 0))),
                    ("CROSS", str(kpis.get("cross_streamer_whales", 0))),
                    ("VIP", str(kpis.get("vip_donors", 0))),
                    ("WAL-VOLUMEN", f"€ {kpis.get('whale_eur_net', 0.0):,.2f}"),
                ]
            ),
            bf.rule(),
            bf.eyebrow("TOP SPENDER"),
        ]

        if not donors:
            lines.append("<i>Keine Spender in dieser Kategorie erfasst.</i>")
        else:
            for idx, d in enumerate(donors[:8], 1):
                vip_star = " · VIP" if d.get("is_vip") else ""
                d_coins = int(d.get("total_coins") or 0)
                d_eur = float(d.get("total_net_eur") or 0.0)
                s_count = int(d.get("streamer_count") or 1)
                lines.append(
                    f"<b>{bf.rank(idx)}</b>  @{html.escape(d['username'])}{vip_star}\n"
                    f"    <code>{d_coins:,}</code> Coins · <code>{d_eur:,.2f} €</code> · {s_count} Streamer"
                )

        lines.append("\nDossier: <code>/donor &lt;username&gt;</code>")
        lines.append(bf.footer())
        text = "\n".join(lines)

        buttons = [
            [
                InlineKeyboardButton(f"{'✓ ' if norm_tier == 'all' else ''}ALLE", callback_data="radar_tier:all"),
                InlineKeyboardButton(f"{'✓ ' if norm_tier == 'whale' else ''}WHALE", callback_data="radar_tier:whale"),
                InlineKeyboardButton(f"{'✓ ' if norm_tier == 'shark' else ''}SHARK", callback_data="radar_tier:shark"),
            ],
            [
                InlineKeyboardButton(f"{'✓ ' if norm_tier == 'dolphin' else ''}DOLPHIN", callback_data="radar_tier:dolphin"),
                InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"radar_tier:{norm_tier}"),
            ],
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_radar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_RADAR_VIEW):
            return

        tier = "all"
        if context.args:
            arg = context.args[0].lower().strip()
            if arg in ("whale", "whales", "wal", "wale"):
                tier = "whale"
            elif arg in ("shark", "sharks", "hai", "haie"):
                tier = "shark"
            elif arg in ("dolphin", "dolphins", "delfin", "delfine"):
                tier = "dolphin"

        text, markup = await asyncio.to_thread(self._format_radar_view, tier)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # WHALE GIFT TICKER (/whales)
    # -----------------------------------------------------------------
    def _format_whales_view(self, min_coins: int = 1000) -> Tuple[str, InlineKeyboardMarkup]:
        val_min = min_coins if min_coins in (1000, 5000, 10000, 30000) else min_coins
        alerts = get_recent_whale_gifts(min_coins=val_min, limit=10)
        lines = [
            bf.header(3, "WHALE-TICKER"),
            bf.kv_table([("SCHWELLE", f"≥ {val_min:,} Coins"), ("EINTRÄGE", str(len(alerts)))]),
            bf.rule(),
        ]

        if not alerts:
            lines.append(f"<i>Keine Geschenke ab {val_min:,} Coins in der Historie verzeichnet.</i>")
        else:
            for a in alerts[:8]:
                rel = self._format_relative_time(a.get("created_at"))
                vip_star = " · VIP" if a.get("is_vip") else ""
                a_coins = int(a.get("total_coins") or 0)
                a_eur = float(a.get("eur_net") or 0.0)
                repeat = f" ×{a['repeat_count']}" if int(a.get("repeat_count") or 1) > 1 else ""
                lines.append(
                    f"<b>@{html.escape(a['sender_username'])}</b>{vip_star} → <b>@{html.escape(a['streamer_username'])}</b>\n"
                    f"    {html.escape(a['gift_name'])}{repeat} · <code>{a_coins:,}</code> Coins · <code>{a_eur:,.2f} €</code> · {rel}"
                )

        lines.append("\nAnalyse: <code>/donor &lt;username&gt;</code>")
        lines.append(bf.footer())
        text = "\n".join(lines)

        buttons = [
            [
                InlineKeyboardButton(f"{'✓ ' if val_min == 1000 else ''}≥ 1K", callback_data="whales_min:1000"),
                InlineKeyboardButton(f"{'✓ ' if val_min == 5000 else ''}≥ 5K", callback_data="whales_min:5000"),
                InlineKeyboardButton(f"{'✓ ' if val_min == 10000 else ''}≥ 10K", callback_data="whales_min:10000"),
                InlineKeyboardButton(f"{'✓ ' if val_min == 30000 else ''}≥ 30K", callback_data="whales_min:30000"),
            ],
            [
                InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"whales_min:{val_min}"),
            ],
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_RADAR_VIEW):
            return

        min_coins = 1000
        if context.args:
            try:
                val = int(context.args[0].strip().replace(".", "").replace(",", ""))
                if val > 0:
                    min_coins = val
            except Exception:
                pass

        text, markup = await asyncio.to_thread(self._format_whales_view, min_coins)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # SPENDER-DOSSIER & CRM (/donor)
    # -----------------------------------------------------------------
    def _format_donor_view(
        self, username: str, can_edit_crm: bool = True
    ) -> Tuple[str, InlineKeyboardMarkup]:
        clean_uname = username.strip().lstrip("@").lower()
        data = get_donor_details(clean_uname)
        if not data or not data.get("profile"):
            text = (
                "<b>SPENDER NICHT GEFUNDEN</b>\n\n"
                f"Für <code>@{html.escape(clean_uname)}</code> liegen noch keine Geschenke-Daten vor.\n"
                "Sobald dieser Nutzer in einem überwachten Livestream schenkt, wird sein Dossier automatisch angelegt.\n\n"
                + bf.footer()
            )
            buttons = [
                [InlineKeyboardButton("▸ ZUM SPENDER-RADAR", callback_data="radar_tier:all")]
            ]
            return text, InlineKeyboardMarkup(buttons)

        p = data["profile"]
        tier = p.get("tier", "fish")
        is_vip = bool(p.get("is_vip"))
        vip_str = "VIP" if is_vip else "STANDARD"

        rel_first = self._format_relative_time(p.get("first_seen"))
        rel_last = self._format_relative_time(p.get("last_seen"))

        loyalty = data.get("loyalty") or {}
        loyalty_badge = loyalty.get("badge", "Keine Einstufung")
        loyalty_label = loyalty.get("label", "")

        lines = [
            bf.header(4, "SPENDER-DOSSIER"),
            f"<b>@{html.escape(p['username'])}</b> · {html.escape(p.get('display_name') or p['username'])}\n"
            f"<code>{str(tier).upper()}</code> · <code>{vip_str}</code>",
            bf.rule(),
            bf.kv_table(
                [
                    ("COINS", f"{int(p.get('total_coins') or 0):,}"),
                    ("NETTO", f"€ {float(p.get('total_eur_net') or 0.0):,.2f}"),
                    ("USD", f"$ {float(p.get('total_usd_net') or 0.0):,.2f}"),
                    ("GIFTS", f"{int(p.get('total_gifts') or 0):,}"),
                    ("ZUERST", rel_first.upper()),
                    ("ZULETZT", rel_last.upper()),
                ]
            ),
            bf.rule(),
            f"LOYALITÄT: <b>{html.escape(str(loyalty_badge)).upper()}</b>",
        ]
        if loyalty_label:
            lines.append(f"<i>{html.escape(loyalty_label)}</i>")

        streamers = data.get("streamers", [])
        if streamers:
            lines.append("\n" + bf.eyebrow(f"KANÄLE · {len(streamers)}"))
            total_coins = max(1, int(p.get("total_coins") or 0))
            for s in streamers[:4]:
                c_given = int(s.get("coins_given") or 0)
                pct = round((c_given / total_coins) * 100, 1)
                lines.append(
                    f"▪ @{html.escape(s['streamer_username'])} · <code>{c_given:,}</code> Coins ({pct}%) · "
                    f"<code>{float(s.get('eur_net') or 0.0):,.2f} €</code>"
                )

        top_gifts = data.get("top_gifts", [])
        if top_gifts:
            lines.append("\n" + bf.eyebrow("TOP GESCHENKE"))
            g_strs = [
                f"{html.escape(g['gift_name'])} ({int(g.get('total_coins') or 0):,})"
                for g in top_gifts[:3]
            ]
            lines.append("▪ " + " · ".join(g_strs))

        if p.get("notes"):
            lines.append(f"\n<b>CRM-NOTIZ</b>\n<i>{html.escape(p['notes'])}</i>")

        lines.append("\n" + bf.footer())
        text = "\n".join(lines)

        first_row = [
            InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"donor_refresh:{p['username']}"),
        ]
        if can_edit_crm:
            vip_btn_label = "VIP ENTFERNEN" if is_vip else "ALS VIP MARKIEREN"
            first_row.insert(
                0,
                InlineKeyboardButton(vip_btn_label, callback_data=f"donor_vip_toggle:{p['username']}"),
            )
        buttons = [
            first_row,
            [
                InlineKeyboardButton("▸ ZUM SPENDER-RADAR", callback_data="radar_tier:all"),
            ],
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_donor(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        access = await self._authorize(update, require_permission=PERM_BOT_RADAR_VIEW)
        if not access:
            return

        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/donor &lt;username&gt;</code>\n"
                "Beispiel: <code>/donor montanablack</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        uname = context.args[0].strip().lstrip("@").lower()
        text, markup = await asyncio.to_thread(
            self._format_donor_view,
            uname,
            PERM_BOT_CRM_EDIT in access["permissions"],
        )
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # VIP MANAGEMENT (/vip)
    # -----------------------------------------------------------------
    async def _cmd_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_RADAR_VIEW):
            return

        args = context.args or []
        if not args:
            radar_data = await asyncio.to_thread(
                get_donor_radar_data,
                vip_only=True,
                limit=25,
            )
            vips = radar_data.get("donors", [])
            if not vips:
                msg = (
                    bf.eyebrow("VIP-WATCHLIST")
                    + "\n\nEs sind aktuell keine Spender als VIP markiert.\n\n"
                    "<i>Hinzufügen:</i> <code>/vip add &lt;username&gt;</code>\n"
                    + bf.footer()
                )
            else:
                lines = [
                    bf.header(5, "VIP-WATCHLIST"),
                    bf.kv_table([("EINTRÄGE", str(len(vips)))]),
                    bf.rule(),
                ]
                for idx, v in enumerate(vips, 1):
                    lines.append(
                        f"<b>{bf.rank(idx)}</b>  @{html.escape(v['username'])} · <code>{v['total_coins']:,}</code> Coins · "
                        f"<code>{v['total_net_eur']:,.2f} €</code> · {v['streamer_count']} Streamer"
                    )
                lines.append("\nDossier: <code>/donor &lt;username&gt;</code>")
                lines.append(bf.footer())
                msg = "\n".join(lines)
            await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        if not await self._authorize(update, require_permission=PERM_BOT_CRM_EDIT):
            return

        first = args[0].lower().strip()
        if first in ("add", "set") and len(args) > 1:
            target_uname = args[1].strip().lstrip("@").lower()
            await asyncio.to_thread(save_donor_crm, target_uname, is_vip=True)
            await update.effective_message.reply_text(
                f"<b>@{html.escape(target_uname)}</b> als <b>VIP</b> markiert.",
                parse_mode=ParseMode.HTML,
            )
        elif first in ("remove", "delete", "del") and len(args) > 1:
            target_uname = args[1].strip().lstrip("@").lower()
            await asyncio.to_thread(save_donor_crm, target_uname, is_vip=False)
            await update.effective_message.reply_text(
                f"VIP-Status für <b>@{html.escape(target_uname)}</b> entfernt.",
                parse_mode=ParseMode.HTML,
            )
        else:
            target_uname = first.lstrip("@").lower()
            new_status = await asyncio.to_thread(toggle_donor_vip, target_uname)
            st_str = "VIP" if new_status else "STANDARD"
            await update.effective_message.reply_text(
                f"Status für <b>@{html.escape(target_uname)}</b>: <b>{st_str}</b>.",
                parse_mode=ParseMode.HTML,
            )

    # -----------------------------------------------------------------
    # LOYALITÄT & FRONTENWECHSLER (/loyalty)
    # -----------------------------------------------------------------
    def _format_loyalty_view(self, days: int = 14) -> Tuple[str, InlineKeyboardMarkup]:
        norm_days = days if days in (7, 14, 30) else 14
        data = get_network_loyalty_and_overlap(days_recent=norm_days)
        shifters = data.get("frontenwechsler", [])
        overlaps = data.get("overlap_matrix", [])

        lines = [
            bf.header(6, "LOYALITÄT"),
            bf.kv_table(
                [
                    ("ZEITRAUM", f"{norm_days} TAGE"),
                    ("WECHSEL", str(len(shifters))),
                    ("OVERLAPS", str(len(overlaps))),
                ]
            ),
            bf.rule(),
            bf.eyebrow("FRONTENWECHSLER"),
        ]

        if not shifters:
            lines.append("<i>Keine markanten Wechsel im gewählten Zeitraum festgestellt.</i>")
        else:
            for s in shifters[:5]:
                fw = s.get("frontenwechsel", {})
                old_s = fw.get("old_streamer", "?")
                new_s = fw.get("new_streamer", "?")
                vol_coins = int(s.get("shift_volume_coins") or 0)
                vol_eur = float(s.get("shift_volume_eur") or 0.0)
                vip = " · VIP" if s.get("is_vip") else ""
                lines.append(
                    f"▪ <b>@{html.escape(s['username'])}</b>{vip} · <code>{html.escape(str(s.get('migration_type', 'Wechsel')))}</code>\n"
                    f"    @{html.escape(old_s)} → <b>@{html.escape(new_s)}</b> · <code>{vol_coins:,}</code> Coins · <code>{vol_eur:,.2f} €</code>"
                )

        lines.append("\n" + bf.eyebrow("STREAMER-OVERLAPS"))
        if not overlaps:
            lines.append("<i>Keine geteilten Spender verzeichnet.</i>")
        else:
            for o in overlaps[:4]:
                s1 = o.get("s1_username", "?")
                s2 = o.get("s2_username", "?")
                count = int(o.get("shared_donors_count") or 0)
                vol = float(o.get("shared_volume_eur") or 0.0)
                lines.append(
                    f"▪ @{html.escape(s1)} &amp; @{html.escape(s2)} · <b>{count}</b> geteilte Spender · <code>{vol:,.2f} €</code>"
                )

        lines.append("\n" + bf.footer())
        text = "\n".join(lines)

        buttons = [
            [
                InlineKeyboardButton(f"{'✓ ' if norm_days == 7 else ''}7 TAGE", callback_data="loyalty_days:7"),
                InlineKeyboardButton(f"{'✓ ' if norm_days == 14 else ''}14 TAGE", callback_data="loyalty_days:14"),
                InlineKeyboardButton(f"{'✓ ' if norm_days == 30 else ''}30 TAGE", callback_data="loyalty_days:30"),
            ],
            [
                InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"loyalty_days:{norm_days}"),
            ],
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_loyalty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_RADAR_VIEW):
            return

        days = 14
        if context.args:
            try:
                val = int(context.args[0].strip())
                if val in (7, 14, 30, 60, 90):
                    days = val
            except Exception:
                pass

        text, markup = await asyncio.to_thread(self._format_loyalty_view, days)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # STREAMER-MONITOR & LISTE (/streamers)
    # -----------------------------------------------------------------
    def _format_streamers_view(self) -> Tuple[str, InlineKeyboardMarkup]:
        streamers = get_all_streamers_summary()
        lines = [
            bf.header(7, "STREAMER-MONITOR"),
            bf.kv_table([("KANÄLE", str(len(streamers)))]),
            bf.rule(),
        ]

        if not streamers:
            lines.append("<i>Keine Streamer hinterlegt. Anlegen mit <code>/add &lt;username&gt;</code>.</i>")
        else:
            for s in streamers[:12]:
                is_live = bool(s.get("is_live"))
                status_icon = bf.status(is_live)
                viewers = f" · {int(s.get('current_viewers') or 0):,} Viewer" if is_live else ""
                coins = int(s.get("today_coins") or 0)
                eur = float(s.get("today_eur_net") or 0.0)
                lines.append(
                    f"{status_icon}{viewers} · <b>{html.escape(s.get('display_name') or s['username'])}</b> (@{html.escape(s['username'])})\n"
                    f"    Heute: <code>{coins:,}</code> Coins · <code>{eur:,.2f} €</code>"
                )

        lines.append("\nEinzelabfrage: <code>/streamer &lt;username&gt;</code>")
        lines.append(bf.footer())
        text = "\n".join(lines)

        buttons = [
            [InlineKeyboardButton("▸ AKTUALISIEREN", callback_data="streamers_list:all")]
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_streamers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_PUBLIC_VIEW):
            return

        text, markup = await asyncio.to_thread(self._format_streamers_view)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # GESCHENKE-FEED (/gifts)
    # -----------------------------------------------------------------
    def _format_gifts_view(self, streamer_ident: Optional[str] = None) -> Tuple[str, InlineKeyboardMarkup]:
        streamer_row = None
        if streamer_ident:
            streamer_row = get_streamer_by_id_or_username(streamer_ident)

        if streamer_row:
            s_id = streamer_row["id"]
            gifts = get_recent_whale_gifts(min_coins=1, streamer_id=s_id, limit=10)
            header = (
                bf.eyebrow("GIFT-TICKER")
                + f"\n<b>@{html.escape(streamer_row['username'])}</b> · {html.escape(streamer_row.get('display_name') or streamer_row['username'])}"
            )
        else:
            gifts = get_recent_whale_gifts(min_coins=100, limit=10)
            header = bf.eyebrow("GIFT-TICKER") + "\n<b>NETZWERKWEIT · ≥ 100 COINS</b>"

        lines = [
            header,
            bf.rule(),
        ]

        if not gifts:
            lines.append("<i>Noch keine Geschenke im Erfassungszeitraum eingetroffen.</i>")
        else:
            for g in gifts[:8]:
                rel = self._format_relative_time(g.get("created_at"))
                vip = " · VIP" if g.get("is_vip") else ""
                coins = int(g.get("total_coins") or 0)
                eur = float(g.get("eur_net") or 0.0)
                repeat = f" ×{g['repeat_count']}" if int(g.get("repeat_count") or 1) > 1 else ""
                lines.append(
                    f"<b>@{html.escape(g['sender_username'])}</b>{vip} → <b>@{html.escape(g['streamer_username'])}</b>\n"
                    f"    {html.escape(g['gift_name'])}{repeat} · <code>{coins:,}</code> Coins · <code>{eur:,.2f} €</code> · {rel}"
                )

        lines.append("\nAnalyse: <code>/donor &lt;username&gt;</code>")
        lines.append(bf.footer())
        text = "\n".join(lines)

        val = streamer_row["username"] if streamer_row else "all"
        buttons = [
            [InlineKeyboardButton("▸ AKTUALISIEREN", callback_data=f"gifts_refresh:{val}")]
        ]
        return text, InlineKeyboardMarkup(buttons)

    async def _cmd_gifts(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_PUBLIC_VIEW):
            return

        streamer_ident = context.args[0].strip().lstrip("@") if context.args else None
        text, markup = await asyncio.to_thread(self._format_gifts_view, streamer_ident)
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    # -----------------------------------------------------------------
    # INTERAKTIVE CALLBACK DISPATCHER
    # -----------------------------------------------------------------
    async def _on_interactive_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        tg_user = update.effective_user
        access = await asyncio.to_thread(
            check_telegram_user_access,
            int(tg_user.id),
            tg_user.username or "",
            tg_user.first_name or "",
            int(update.effective_chat.id) if update.effective_chat else int(tg_user.id),
            update.effective_chat.title if update.effective_chat else "",
        )
        if not access.get("allowed"):
            await query.answer("× Kein Zugriff (Whitelist aktiv).", show_alert=True)
            return

        data = query.data
        parts = data.split(":", 1)
        action = parts[0]
        val = parts[1] if len(parts) > 1 else ""

        access_role = normalize_role(access.get("role"))
        access_perms = set(permissions_for(access_role, 1))

        async def _deny_permission(permission: str) -> None:
            await query.answer(
                f"× Deine Rolle ({role_label(access_role)}) darf diese Aktion nicht ausführen.",
                show_alert=True,
            )

        text = None
        markup = None

        if action in ("overview_period", "overview_streamer") and PERM_BOT_ANALYTICS_VIEW not in access_perms:
            await _deny_permission(PERM_BOT_ANALYTICS_VIEW)
            return
        if action in ("radar_tier", "whales_min", "donor_refresh", "loyalty_days") and PERM_BOT_RADAR_VIEW not in access_perms:
            await _deny_permission(PERM_BOT_RADAR_VIEW)
            return
        if action == "donor_vip_toggle" and PERM_BOT_CRM_EDIT not in access_perms:
            await _deny_permission(PERM_BOT_CRM_EDIT)
            return

        if action == "overview_period":
            await query.answer()
            period = val or "today"
            text, markup = await asyncio.to_thread(self._format_overview_view, period)
        elif action == "radar_tier":
            await query.answer()
            tier = val or "all"
            text, markup = await asyncio.to_thread(self._format_radar_view, tier)
        elif action == "whales_min":
            await query.answer()
            try:
                min_coins = int(val)
            except Exception:
                min_coins = 1000
            text, markup = await asyncio.to_thread(self._format_whales_view, min_coins)
        elif action == "donor_vip_toggle":
            uname = val.strip().lower()
            new_vip = await asyncio.to_thread(toggle_donor_vip, uname)
            alert_msg = f"@{uname} ist jetzt VIP." if new_vip else f"VIP-Status für @{uname} entfernt."
            await query.answer(alert_msg)
            text, markup = await asyncio.to_thread(self._format_donor_view, uname, True)
        elif action == "donor_refresh":
            await query.answer("Aktualisiert")
            uname = val.strip().lower()
            text, markup = await asyncio.to_thread(
                self._format_donor_view,
                uname,
                PERM_BOT_CRM_EDIT in access_perms,
            )
        elif action == "loyalty_days":
            await query.answer()
            try:
                days = int(val)
            except Exception:
                days = 14
            text, markup = await asyncio.to_thread(self._format_loyalty_view, days)
        elif action == "streamers_list":
            await query.answer("Aktualisiert")
            text, markup = await asyncio.to_thread(self._format_streamers_view)
        elif action == "gifts_refresh":
            await query.answer("Aktualisiert")
            ident = None if val == "all" else val
            text, markup = await asyncio.to_thread(self._format_gifts_view, ident)

        if text and markup:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                if "not modified" not in str(exc).lower():
                    logger.warning(f"Fehler beim Aktualisieren der Telegram-Nachricht: {exc}")

    async def _cmd_add_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_STREAMERS_MANAGE):
            return

        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/add &lt;username&gt;</code>", parse_mode=ParseMode.HTML
            )
            return

        username = context.args[0].strip().lstrip("@").lower()
        profile = await asyncio.to_thread(fetch_tiktok_user_info, username)
        streamer = await asyncio.to_thread(
            upsert_streamer,
            username,
            profile.get("display_name") or username,
            profile.get("avatar_url"),
            profile.get("room_id"),
            profile.get("follower_count"),
            profile.get("is_live"),
            True,
        )
        monitor_manager.start_tracking(streamer["id"], streamer["username"], auto_reconnect=True)
        await update.effective_message.reply_text(
            f"Streamer <b>@{html.escape(streamer['username'])}</b> gespeichert; Live-Worker gestartet.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_track_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_STREAMERS_MANAGE):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/track &lt;username&gt;</code>", parse_mode=ParseMode.HTML
            )
            return
        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, context.args[0])
        if not s_row:
            await update.effective_message.reply_text("Streamer nicht gefunden.")
            return
        res = monitor_manager.start_tracking(s_row["id"], s_row["username"], auto_reconnect=True)
        await update.effective_message.reply_text(f"▸ {res.get('message')}")

    async def _cmd_stop_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_STREAMERS_MANAGE):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/stop &lt;username&gt;</code>", parse_mode=ParseMode.HTML
            )
            return
        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, context.args[0])
        if not s_row:
            await update.effective_message.reply_text("Streamer nicht gefunden.")
            return
        res = monitor_manager.stop_tracking(s_row["username"])
        await update.effective_message.reply_text(f"■ {res.get('message')}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_SYSTEM_VIEW):
            return
        diag = monitor_manager.get_all_diagnostics()
        workers = diag.get("workers", [])
        lines = [
            bf.header(9, "SYSTEM-STATUS"),
            bf.kv_table(
                [
                    ("MODUS", get_telegram_access_mode().upper()),
                    ("WORKER", str(diag["workers_running"])),
                    ("VERBUNDEN", str(diag["workers_connected"])),
                ]
            ),
            bf.rule(),
        ]
        for w in workers:
            worker_state = str(w["state"]).lower()
            state_glyph = bf.LIVE if worker_state in ("live", "connected", "streaming") else f"○ {worker_state.upper()}"
            lines.append(
                f"{state_glyph} · <b>@{html.escape(w['username'])}</b> · "
                f"{w['current_viewers']} Viewer · {w['coins_received_session']:,} Coins"
            )

        try:
            from system_service import get_system_health

            h = get_system_health()
            d = h.get("host", {}).get("disk", {})
            m = h.get("host", {}).get("memory", {})
            c = h.get("host", {}).get("cpu", {})
            lines.append("\n" + bf.eyebrow("SERVER-RESSOURCEN"))
            lines.append(
                bf.kv_table(
                    [
                        ("DISK", f"{d.get('percent', 0)}% · {d.get('used_gb', 0):.1f}/{d.get('total_gb', 0):.1f} GB"),
                        ("RAM", f"{m.get('percent', 0)}% · {m.get('used_mb', 0):.0f}/{m.get('total_mb', 0):.0f} MB"),
                        ("CPU", f"{c.get('percent', 0)}% · LOAD {c.get('load_1m', 0)}"),
                    ]
                )
            )
        except Exception:
            pass

        lines.append("\n" + bf.footer())
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _cmd_allow_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_USERS_MANAGE):
            return

        reply_msg = update.effective_message.reply_to_message
        ident: Optional[str] = None
        tg_id_override: Optional[int] = None
        uname_override: Optional[str] = None
        fname_override: Optional[str] = None
        role = ROLE_USER
        allowed_roles = ("viewer", "user", "moderator", "admin")

        if reply_msg and reply_msg.from_user and not reply_msg.from_user.is_bot:
            target_u = reply_msg.from_user
            ident = str(target_u.id)
            tg_id_override = int(target_u.id)
            uname_override = target_u.username or None
            fname_override = target_u.first_name or None
            if context.args and context.args[0].lower() in allowed_roles:
                role = context.args[0].lower()
        elif context.args:
            ident = context.args[0].strip()
            if len(context.args) > 1 and context.args[1].lower() in allowed_roles:
                role = context.args[1].lower()

        if not ident:
            await update.effective_message.reply_text(
                "Verwendung:\n"
                "• <code>/allow &lt;telegram_id_oder_@username&gt; [viewer|user|moderator|admin]</code>\n"
                "• Oder in einer Gruppe einfach auf die Nachricht einer Person mit <code>/allow</code> antworten!",
                parse_mode=ParseMode.HTML,
            )
            return

        role = normalize_role(role)

        row = await asyncio.to_thread(
            upsert_telegram_user_permission,
            ident,
            1,
            role,
            fname_override,
            "Freigeschaltet via /allow",
            tg_id_override,
            uname_override,
        )
        label = f"@{row['username']}" if row.get("username") else str(row.get("telegram_id"))
        self._log("INFO", f"Telegram-Nutzer {label} als {role.upper()} freigeschaltet.")
        await update.effective_message.reply_text(
            f"<b>@{html.escape(label)}</b> · ID <code>{row.get('telegram_id') or 'PENDING'}</code> "
            f"· Rolle <code>{role.upper()}</code> freigeschaltet.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_revoke_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_USERS_MANAGE):
            return

        reply_msg = update.effective_message.reply_to_message
        ident: Optional[str] = None
        tg_id_override: Optional[int] = None
        uname_override: Optional[str] = None

        if reply_msg and reply_msg.from_user and not reply_msg.from_user.is_bot:
            target_u = reply_msg.from_user
            ident = str(target_u.id)
            tg_id_override = int(target_u.id)
            uname_override = target_u.username or None
        elif context.args:
            ident = context.args[0].strip()

        if not ident:
            await update.effective_message.reply_text(
                "Verwendung:\n"
                "• <code>/revoke &lt;telegram_id_oder_@username&gt;</code>\n"
                "• Oder in einer Gruppe auf die Nachricht einer Person mit <code>/revoke</code> antworten.",
                parse_mode=ParseMode.HTML,
            )
            return

        row = await asyncio.to_thread(
            upsert_telegram_user_permission,
            ident,
            -1,
            "user",
            None,
            "Gesperrt via /revoke",
            tg_id_override,
            uname_override,
        )
        label = f"@{row['username']}" if row.get("username") else str(row.get("telegram_id"))
        self._log("INFO", f"Telegram-Nutzer {label} wurde gesperrt.")
        await update.effective_message.reply_text(
            f"Zugriff für <b>{html.escape(label)}</b> entzogen.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_USERS_MANAGE):
            return

        users = await asyncio.to_thread(list_telegram_users)
        mode = await asyncio.to_thread(get_telegram_access_mode)
        lines = [
            bf.eyebrow("NUTZERVERWALTUNG"),
            bf.kv_table([("MODUS", mode.upper()), ("ERFASST", str(len(users)))]),
            bf.rule(),
        ]
        for u in users[:30]:
            st = int(u.get("is_allowed", 0))
            badge = "✓" if st == 1 else ("…" if st == 0 else "×")
            role_tag = f" [{role_label(u.get('role')).upper()}]"
            uname = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "-")
            tg_id = u.get("telegram_id") or "-"
            lines.append(
                f"{badge} <code>{tg_id}</code> · <b>{html.escape(uname)}</b>{role_tag}"
            )
        lines.append(bf.footer())
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            not update.effective_message
            or not update.effective_chat
            or not update.effective_user
        ):
            return
        if not await self._authorize(update, require_permission=PERM_BOT_STREAMERS_MANAGE):
            return

        chat = update.effective_chat
        chat_id = int(chat.id)
        chat_title = (
            (chat.title or str(chat_id))
            if self._is_group_chat(update)
            else "Privatchat"
        )
        tg_user = update.effective_user
        args = context.args or []

        if not args or args[0].lower() in ("list", "status", "show"):
            subscriptions = await asyncio.to_thread(
                list_streamer_alert_subscriptions,
                chat_id=chat_id,
            )
            if not subscriptions:
                await update.effective_message.reply_text(
                    bf.eyebrow("LIVE-ALERTS")
                    + "\n\nFür diesen Chat sind noch keine Streamer-Alerts aktiv.\n"
                    "Aktivieren mit <code>/alert &lt;@username&gt;</code>.\n"
                    + bf.footer(),
                    parse_mode=ParseMode.HTML,
                )
                return
            lines = [
                bf.eyebrow("LIVE-ALERTS · DIESER CHAT"),
                bf.rule(),
            ]
            for sub in subscriptions:
                uname = str(sub.get("streamer_username") or "").lstrip("@")
                live_tag = " " + bf.LIVE if int(sub.get("streamer_is_live") or 0) else ""
                lines.append(f"▪ <b>@{html.escape(uname)}</b>{live_tag}")
            lines.append(
                "\nEntfernen mit <code>/alert off &lt;@username&gt;</code>.\n" + bf.footer()
            )
            await update.effective_message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.HTML
            )
            return

        action = "add"
        target = args[0]
        first = target.lower()
        off_words = ("off", "remove", "del", "delete", "stop", "aus")
        on_words = ("on", "add", "set", "an")
        if first in off_words:
            action = "remove"
            target = args[1] if len(args) > 1 else ""
        elif first in on_words:
            target = args[1] if len(args) > 1 else ""
        elif len(args) > 1 and args[1].lower() in off_words:
            action = "remove"
        elif len(args) > 1 and args[1].lower() in on_words:
            action = "add"

        if not target:
            await update.effective_message.reply_text(
                "Verwendung:\n"
                "• <code>/alert &lt;@username&gt;</code> – Live-Alert in diesem Chat aktivieren\n"
                "• <code>/alert off &lt;@username&gt;</code> – Live-Alert deaktivieren\n"
                "• <code>/alert list</code> – aktive Alerts anzeigen",
                parse_mode=ParseMode.HTML,
            )
            return

        streamer = await asyncio.to_thread(get_streamer_by_id_or_username, target)
        if not streamer:
            await update.effective_message.reply_text(
                f"Streamer <code>{html.escape(str(target).lstrip('@'))}</code> nicht gefunden.\n"
                "Zuerst mit <code>/add &lt;username&gt;</code> anlegen.",
                parse_mode=ParseMode.HTML,
            )
            return

        uname = str(streamer.get("username") or target).lstrip("@")
        if action == "remove":
            removed = await asyncio.to_thread(
                remove_streamer_alert,
                int(streamer["id"]),
                chat_id,
            )
            if removed:
                msg = f"Live-Alert für <b>@{html.escape(uname)}</b> deaktiviert."
            else:
                msg = f"Für <b>@{html.escape(uname)}</b> war kein Live-Alert aktiv."
            await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

        await asyncio.to_thread(
            add_streamer_alert,
            int(streamer["id"]),
            chat_id,
            chat_title,
            int(tg_user.id),
            (tg_user.username or "").lstrip("@"),
        )
        warning = ""
        if not int(streamer.get("auto_monitor") or 0):
            warning = (
                "\n\n<i>Hinweis: Der Streamer ist nicht für Auto-Monitoring markiert. "
                f"Überwachung starten mit</i> <code>/track @{html.escape(uname)}</code>."
            )
        await update.effective_message.reply_text(
            f"Live-Alert für <b>@{html.escape(uname)}</b> aktiviert."
            f"{warning}",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_access_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_permission=PERM_BOT_SETTINGS_MANAGE):
            return

        if not context.args or context.args[0].lower() not in ("whitelist", "public"):
            curr = await asyncio.to_thread(get_telegram_access_mode)
            await update.effective_message.reply_text(
                bf.eyebrow("ZUGRIFFSMODUS")
                + f"\n\nAktuell: <b>{curr.upper()}</b>\n\n"
                "▪ <code>/mode whitelist</code> — nur freigeschaltete Personen\n"
                "▪ <code>/mode public</code> — alle Nutzer als Viewer\n"
                + bf.footer(),
                parse_mode=ParseMode.HTML,
            )
            return

        new_mode = await asyncio.to_thread(set_telegram_access_mode, context.args[0].lower())
        self._log("INFO", f"Telegram-Zugriffsmodus geändert auf: {new_mode.upper()}")
        await update.effective_message.reply_text(
            f"Zugriffsmodus: <b>{new_mode.upper()}</b>.",
            parse_mode=ParseMode.HTML,
        )


telegram_bot_service = TelegramBotService()
