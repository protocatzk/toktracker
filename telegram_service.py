import asyncio
import html
import logging
import os
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional

try:
    from telegram import (
        BotCommand,
        BotCommandScopeAllGroupChats,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeDefault,
        Update,
    )
    from telegram.constants import ChatType, ParseMode
    from telegram.ext import (
        Application,
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

from config import BASE_DIR, config
from database import (
    build_streamer_bot_report,
    check_telegram_user_access,
    get_db,
    get_settings,
    get_streamer_by_id_or_username,
    get_telegram_access_mode,
    list_telegram_users,
    set_telegram_access_mode,
    upsert_streamer,
    upsert_telegram_user_permission,
)
from tiktok_service import fetch_tiktok_user_info, monitor_manager

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
        f"📋 *toktracker – Streamer Einnahmen-Report ({hours}h)*",
        f"🕒 Stand: `{now.strftime('%d.%m.%Y %H:%M')}`",
        f"💰 *Gesamt Netto ({hours}h):* `{total_period_eur_net:,.2f} €` (`${total_period_usd_net:,.2f}`)",
        f"🪙 *Gesamt Coins ({hours}h):* `{total_period_coins:,}` ({total_gifts_sent:,} Gifts)",
        f"📡 *Streamer:* {len(cards)} überwacht ({live_now} aktuell LIVE)",
        "────────────────────────",
    ]
    html_lines = [
        f"<b>📋 toktracker – Streamer Einnahmen-Report ({hours}h)</b>",
        f"🕒 Stand: <code>{now.strftime('%d.%m.%Y %H:%M')}</code>",
        f"💰 <b>Gesamt Netto ({hours}h):</b> <code>{total_period_eur_net:,.2f} €</code> (<code>${total_period_usd_net:,.2f}</code>)",
        f"🪙 <b>Gesamt Coins ({hours}h):</b> <code>{total_period_coins:,}</code> ({total_gifts_sent:,} Gifts)",
        f"📡 <b>Streamer:</b> {len(cards)} überwacht ({live_now} aktuell LIVE)",
        "────────────────────────",
    ]

    for idx, c in enumerate(cards, start=1):
        status_dot = "🟢" if c["is_live"] else "⚪"
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
            f"*{idx}. {c['display_name']}* (@{c['username']}) {status_dot}\n"
            f"   • {hours}h Netto: *{c['period_eur_net']:,.2f} €* (`${c['period_usd_net']:,.2f}`) | `{c['period_coins']:,}` Coins\n"
            f"   • Top Gift: {top_g} | Top Gifter: {top_u}\n"
            f"   • All-Time: {c['alltime_eur_net']:,.2f} € ({c['alltime_coins']:,} Coins)"
        )
        html_lines.append(
            f"<b>{idx}. {html.escape(str(c['display_name']))}</b> (@{html.escape(str(c['username']))}) {status_dot}\n"
            f"   • {hours}h Netto: <b>{c['period_eur_net']:,.2f} €</b> (<code>${c['period_usd_net']:,.2f}</code>) | <code>{c['period_coins']:,}</code> Coins\n"
            f"   • Top Gift: {html.escape(top_g)} | Top Gifter: {html.escape(top_u)}\n"
            f"   • All-Time: {c['alltime_eur_net']:,.2f} € ({c['alltime_coins']:,} Coins)"
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
    Gruppen-Support (`/befehl@BotName` & `@BotName befehl`) sowie mehrstufiger
    Zugriffskontrolle (`whitelist` per `[@]username` oder `id` vs. `public`).

    WICHTIG (Fehlertoleranz):
    - Wenn kein Token gesetzt ist, das Token ungültig ist oder Telegram nicht erreichbar ist,
      fängt dieser Service alle Fehler intern ab.
    - Die FastAPI-Anwendung und das Web-Interface starten und laufen IMMER unabhängig weiter!
    """

    def __init__(self) -> None:
        self._app: Optional[Any] = None
        self._state: str = "disabled"
        self._last_error: str = ""
        self._bot_username: str = ""
        self._bot_username_raw: str = ""
        self._started_at: Optional[str] = None
        self._last_report_sent_at: Optional[str] = None
        self._logs: Deque[Dict[str, str]] = deque(maxlen=40)

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
            builder = Application.builder().token(token)
            self._app = builder.build()

            # Lese-Befehle (für Whitelist-Nutzer per @username/ID bzw. im Public-Modus für alle Nutzer; in Privatchats & Gruppen)
            self._app.add_handler(CommandHandler(["start", "help"], self._cmd_help))
            self._app.add_handler(CommandHandler(["id", "whoami"], self._cmd_whoami))
            self._app.add_handler(CommandHandler("report", self._cmd_report))
            self._app.add_handler(CommandHandler(["streamer", "stats"], self._cmd_streamer))
            self._app.add_handler(CommandHandler("status", self._cmd_status))

            # Schreib- & Verwaltungs-Befehle (immer nur für Admins – funktioniert auch in Gruppen!)
            self._app.add_handler(CommandHandler("add", self._cmd_add_streamer))
            self._app.add_handler(CommandHandler("track", self._cmd_track_streamer))
            self._app.add_handler(CommandHandler("stop", self._cmd_stop_streamer))
            self._app.add_handler(CommandHandler("allow", self._cmd_allow_user))
            self._app.add_handler(CommandHandler("revoke", self._cmd_revoke_user))
            self._app.add_handler(CommandHandler("users", self._cmd_list_users))
            self._app.add_handler(CommandHandler("mode", self._cmd_access_mode))

            # Gruppen-Mention-Handler: Erlaubt Aufrufe wie "@DeinBot report" oder "@DeinBot streamer <username>" in Gruppen
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

            # Befehlsmenü automatisch bei Telegram für Privatchats UND Gruppen registrieren
            await self._register_bot_commands()

            await self._app.start()
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

            self._state = "running"
            self._started_at = datetime.now().isoformat(timespec="seconds")
            self._log(
                "INFO",
                f"toktracker Telegram-Bot ({self._bot_username}) gestartet [Modus: {get_telegram_access_mode().upper()}, Gruppen-Support: AKTIV].",
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
            BotCommand("report", "24h-Gesamtbericht aller überwachten Streamer abrufen"),
            BotCommand("streamer", "Einzelabfrage für einen Streamer"),
            BotCommand("status", "Laufzeit-Status aller aktiven TikTokLive-Worker prüfen"),
            BotCommand("id", "Eigene Telegram-ID, Gruppen-ID & Berechtigungsstatus anzeigen"),
            BotCommand("help", "Hilfe & verfügbare Befehle anzeigen"),
            BotCommand("add", "[Admin] Streamer hinzufügen & Live-Worker starten"),
            BotCommand("track", "[Admin] Live-Überwachung für einen Streamer starten"),
            BotCommand("stop", "[Admin] Live-Überwachung für einen Streamer stoppen"),
            BotCommand("allow", "[Admin] Nutzer per ID, @username oder Reply freischalten"),
            BotCommand("revoke", "[Admin] Nutzer-Berechtigung entziehen / sperren"),
            BotCommand("users", "[Admin] Freigeschaltete Nutzer & offene Anfragen auflisten"),
            BotCommand("mode", "[Admin] Zugriffsmodus wechseln (whitelist oder public)"),
        ]
        try:
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
            await self._app.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        except Exception as exc:
            self._log("INFO", f"Hinweis bei set_my_commands: {exc}")

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
    # ZUGRIFFSKONTROLLE & AUTORISIERUNG (PRIVATCHAT & GRUPPEN)
    # =================================================================

    @staticmethod
    def _is_group_chat(update: Update) -> bool:
        if not update.effective_chat:
            return False
        return update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

    async def _authorize(
        self, update: Update, require_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Prüft im Privatchat UND in Telegram-Gruppen, ob der aufrufende Nutzer (`effective_user`)
        per `[@]username` oder `telegram_id` auf der Whitelist steht.
        - Im 'whitelist'-Modus (Standard): Nur freigeschaltete Nutzer (`is_allowed == 1`).
          Unbekannte Nutzer (auch aus Gruppen!) werden automatisch als offene Anfrage (`is_allowed = 0`)
          in der Datenbank vermerkt und erhalten ihre ID/@username angezeigt.
        - Im 'public'-Modus: Alle nicht-gesperrten Nutzer dürfen Abfrage-Befehle nutzen;
          Verwaltungs-Befehle (`require_admin=True`) bleiben strikt auf Admins beschränkt.
        """
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
                "🔒 <b>toktracker · Zugriff beschränkt (Whitelist aktiv)</b>\n\n"
                "Du bist aktuell noch nicht für diesen Bot freigeschaltet.\n"
                f"• <b>Deine User-ID:</b> <code>{tg_user.id}</code>\n"
                f"• <b>Dein Username:</b> <code>{html.escape(uname_display)}</code>\n\n"
                f"<i>Ein Admin kann dich im Web-Interface, per Reply mit <code>/allow</code> oder mit {allow_hint} freischalten.</i>",
                parse_mode=ParseMode.HTML,
            )
            return None

        if require_admin and not access["is_admin"]:
            self._log(
                "INFO",
                f"Admin-Befehl verweigert für {uname_display} (ID: {tg_user.id}){chat_context}.",
            )
            await update.effective_message.reply_text(
                "⛔ <b>Keine Berechtigung:</b> Dieser Verwaltungsbefehl ist nur für Administratoren freigegeben.",
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
    ) -> None:
        """
        Sendet ein Banner-Bild aus /pictures zusammen mit dem Bericht (im Privatchat und in Gruppen).
        Falls die Caption länger als 1024 Zeichen ist (Telegram-Limit für Foto-Captions),
        wird erst das Banner und direkt darunter der vollständige Bericht gesendet.
        """
        if os.path.exists(banner_path):
            with open(banner_path, "rb") as photo_file:
                if len(html_text) <= 1000:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        caption=html_text,
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=reply_to_message_id,
                    )
                    return
                else:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_file,
                        reply_to_message_id=reply_to_message_id,
                    )

        await bot.send_message(
            chat_id=chat_id,
            text=html_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_to_message_id,
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

    # =================================================================
    # GRUPPEN-MENTION HANDLER ("@DeinBot report" oder "@DeinBot streamer <username>")
    # =================================================================

    async def _on_group_mention(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Erlaubt es berechtigten Nutzern in Gruppen, den Bot auch direkt per @BotUsername
        anzusprechen.
        """
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
        elif cmd in ("streamer", "stats", "info"):
            await self._cmd_streamer(update, context)
        elif cmd in ("status", "worker", "workers"):
            await self._cmd_status(update, context)
        elif cmd in ("id", "whoami"):
            await self._cmd_whoami(update, context)
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
        """Zeigt dem Nutzer seine eigene User-ID, seinen @username sowie (in Gruppen) die Gruppen-Chat-ID an."""
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
        role_label = (
            "Admin"
            if access["is_admin"]
            else ("Freigeschaltet" if access["allowed"] else "Gesperrt / Wartend")
        )
        group_line = ""
        if self._is_group_chat(update):
            group_line = (
                f"• <b>Gruppen-Name:</b> <code>{html.escape(tg_chat.title or '-')}</code>\n"
                f"• <b>Gruppen Chat-ID:</b> <code>{tg_chat.id}</code> <i>(für 24h-Report in Gruppe)</i>\n"
            )

        await update.effective_message.reply_text(
            f"👤 <b>toktracker · Telegram-Profil &amp; Chat-Info</b>\n"
            f"• <b>Deine User-ID:</b> <code>{tg_user.id}</code>\n"
            f"• <b>Dein Username:</b> <code>@{html.escape(tg_user.username or '-')}</code>\n"
            f"{group_line}"
            f"• <b>Dein Status:</b> <b>{role_label}</b> (Bot-Modus: <code>{access['mode']}</code>)",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat or not update.effective_user:
            return
        access = await self._authorize(update, require_admin=False)
        if not access:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        is_grp = self._is_group_chat(update)

        id_info = (
            f"📌 <b>User-ID:</b> <code>{user_id}</code> | <b>Gruppen-ID:</b> <code>{chat_id}</code>"
            if is_grp
            else f"📌 <b>Deine ID:</b> <code>{user_id}</code>"
        )

        admin_section = ""
        if access["is_admin"]:
            admin_section = (
                "\n\n<b>🔐 Admin-Befehle:</b>\n"
                "• <code>/add &lt;username&gt;</code> – Streamer hinzufügen &amp; Worker starten\n"
                "• <code>/track &lt;username&gt;</code> | <code>/stop &lt;username&gt;</code> – Worker steuern\n"
                "• <code>/allow &lt;id|@user&gt; [admin|user]</code> – Nutzer freischalten (oder per Reply!)\n"
                "• <code>/revoke &lt;id|@user&gt;</code> – Zugriff entziehen (oder per Reply!)\n"
                "• <code>/users</code> – Nutzerliste &amp; Anfragen anzeigen\n"
                "• <code>/mode &lt;whitelist|public&gt;</code> – Zugriffsmodus umschalten"
            )

        text = (
            "<b>🚀 Willkommen bei toktracker!</b>\n\n"
            "toktracker überwacht TikTok-Streamer in Echtzeit, erfasst alle Live-Geschenke "
            "(Coins &amp; Diamonds) und berechnet die Netto-Creator-Auszahlung in <b>EUR (€)</b> und <b>USD ($)</b>.\n\n"
            f"{id_info} | <b>Modus:</b> <code>{access['mode'].upper()}</code>\n\n"
            "<b>📋 Abfrage-Befehle (Privatchat &amp; Gruppe):</b>\n"
            "• <code>/report [stunden]</code> – Gesamtbericht aller Streamer\n"
            "• <code>/streamer &lt;username&gt; [stunden]</code> – Einzelabfrage pro Streamer\n"
            "• <code>/status</code> – Laufzeit-Status aller TikTokLive-Worker\n"
            "• <code>/id</code> – Eigene User-ID &amp; Gruppen-ID prüfen"
            f"{admin_section}"
        )
        await self._send_with_optional_banner(
            bot=context.bot,
            chat_id=chat_id,
            html_text=text,
            banner_path=WELCOME_BANNER_PATH,
            reply_to_message_id=update.effective_message.message_id if is_grp else None,
        )

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_chat:
            return
        if not await self._authorize(update, require_admin=False):
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
        if not await self._authorize(update, require_admin=False):
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
                f"❌ Streamer <code>@{html.escape(identifier)}</code> wurde nicht in der Datenbank gefunden.",
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

        live_str = "🟢 LIVE" if card["is_live"] else f"⚪ {card['worker_state'].upper()}"
        top_g = (
            ", ".join(
                f"{g['gift_name']} ({g['total_coins']:,})" for g in card["top_gifts"][:3]
            )
            or "Keine"
        )
        top_u = (
            ", ".join(
                f"@{u['sender_username']} ({u['total_coins']:,})"
                for u in card["top_gifters"][:3]
            )
            or "Keine"
        )

        msg = (
            f"<b>📊 toktracker · Streamer-Einzelabfrage: {html.escape(card['display_name'])}</b> (@{html.escape(uname)})\n"
            f"Status: <b>{live_str}</b> | Aktuelle Zuschauer: <code>{card['current_viewers']:,}</code>\n"
            "────────────────────────\n"
            f"<b>Zeitraum ({hours}h):</b>\n"
            f"• Netto-Auszahlung: <b>{card['period_eur_net']:,.2f} €</b> (<code>${card['period_usd_net']:,.2f}</code>)\n"
            f"• Brutto-Kaufwert: <code>{card['period_eur_gross']:,.2f} €</code>\n"
            f"• Coins / Diamonds: <b>{card['period_coins']:,}</b> ({card['period_gifts_sent']:,} Gifts von {card['period_unique_gifters']} Giftern)\n"
            f"• Peak Zuschauer ({hours}h): <code>{card['period_peak_viewers']:,}</code>\n"
            f"• Top Gifts: {html.escape(top_g)}\n"
            f"• Top Spender: {html.escape(top_u)}\n"
            "────────────────────────\n"
            f"<b>Gesamt (All-Time):</b> <code>{card['alltime_eur_net']:,.2f} €</code> (<code>{card['alltime_coins']:,}</code> Coins)"
        )
        await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def _cmd_add_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
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
            f"✅ Streamer <b>@{html.escape(streamer['username'])}</b> gespeichert und Live-Worker gestartet!",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_track_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/track &lt;username&gt;</code>", parse_mode=ParseMode.HTML
            )
            return
        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, context.args[0])
        if not s_row:
            await update.effective_message.reply_text("❌ Streamer nicht gefunden.")
            return
        res = monitor_manager.start_tracking(s_row["id"], s_row["username"], auto_reconnect=True)
        await update.effective_message.reply_text(f"▶️ {res.get('message')}")

    async def _cmd_stop_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Verwendung: <code>/stop &lt;username&gt;</code>", parse_mode=ParseMode.HTML
            )
            return
        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, context.args[0])
        if not s_row:
            await update.effective_message.reply_text("❌ Streamer nicht gefunden.")
            return
        res = monitor_manager.stop_tracking(s_row["username"])
        await update.effective_message.reply_text(f"⏹️ {res.get('message')}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=False):
            return
        diag = monitor_manager.get_all_diagnostics()
        workers = diag.get("workers", [])
        lines = [
            "<b>⚙️ toktracker · Backend &amp; Worker Status</b>",
            f"Zugriffsmodus: <code>{get_telegram_access_mode().upper()}</code>",
            f"Aktive Worker: <b>{diag['workers_running']}</b> ({diag['workers_connected']} im Stream verbunden)",
        ]
        for w in workers:
            lines.append(
                f"• <b>@{html.escape(w['username'])}</b>: <code>{w['state']}</code> "
                f"(Viewers: {w['current_viewers']}, Session-Coins: {w['coins_received_session']:,})"
            )
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    # =================================================================
    # ADMIN COMMANDS ZUR NUTZER- & MODUS-VERWALTUNG (INKL. GRUPPEN-REPLY)
    # =================================================================

    async def _cmd_allow_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Schaltet eine Person für den Bot frei:
        1. Per Argument: `/allow @username [user|admin]` oder `/allow <telegram_id> [user|admin]`
        2. Oder direkt in einer Gruppe per Reply auf eine Nachricht des Nutzers: `/allow [user|admin]`
        """
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
            return

        reply_msg = update.effective_message.reply_to_message
        ident: Optional[str] = None
        tg_id_override: Optional[int] = None
        uname_override: Optional[str] = None
        fname_override: Optional[str] = None
        role = "user"

        if reply_msg and reply_msg.from_user and not reply_msg.from_user.is_bot:
            target_u = reply_msg.from_user
            ident = str(target_u.id)
            tg_id_override = int(target_u.id)
            uname_override = target_u.username or None
            fname_override = target_u.first_name or None
            if context.args and context.args[0].lower() in ("user", "admin"):
                role = context.args[0].lower()
        elif context.args:
            ident = context.args[0].strip()
            if len(context.args) > 1 and context.args[1].lower() in ("user", "admin"):
                role = context.args[1].lower()

        if not ident:
            await update.effective_message.reply_text(
                "Verwendung:\n"
                "• <code>/allow &lt;telegram_id_oder_@username&gt; [user|admin]</code>\n"
                "• Oder in einer Gruppe einfach auf die Nachricht einer Person mit <code>/allow</code> antworten!",
                parse_mode=ParseMode.HTML,
            )
            return

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
            f"✅ Nutzer <b>{html.escape(label)}</b> (ID: <code>{row.get('telegram_id') or 'wird bei Nachricht verknüpft'}</code>) "
            f"wurde mit Rolle <code>{role.upper()}</code> für Privatchat &amp; Gruppen freigeschaltet!",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_revoke_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Entzieht einem Nutzer die Berechtigung per `/revoke @username`, `/revoke <telegram_id>`
        oder in einer Gruppe per Reply auf dessen Nachricht mit `/revoke`.
        """
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
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
            f"🚫 Zugriff für <b>{html.escape(label)}</b> wurde entzogen.",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
            return

        users = await asyncio.to_thread(list_telegram_users)
        mode = await asyncio.to_thread(get_telegram_access_mode)
        lines = [
            f"<b>👥 toktracker · Telegram-Nutzerverwaltung (Modus: {mode.upper()})</b>",
            f"Gesamt erfasst: <b>{len(users)}</b>",
            "────────────────────────",
        ]
        for u in users[:30]:
            st = int(u.get("is_allowed", 0))
            badge = "✅" if st == 1 else ("⏳" if st == 0 else "🚫")
            role_tag = " [ADMIN]" if u.get("role") == "admin" else ""
            uname = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "-")
            tg_id = u.get("telegram_id") or "-"
            lines.append(
                f"{badge} <code>{tg_id}</code> – <b>{html.escape(uname)}</b>{role_tag}"
            )
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _cmd_access_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not await self._authorize(update, require_admin=True):
            return

        if not context.args or context.args[0].lower() not in ("whitelist", "public"):
            curr = await asyncio.to_thread(get_telegram_access_mode)
            await update.effective_message.reply_text(
                f"🔐 Aktueller Zugriffsmodus: <b>{curr.upper()}</b>\n\n"
                "Umschalten mit:\n"
                "• <code>/mode whitelist</code> – Nur freigeschaltete Personen (@username oder ID) dürfen den Bot im Privatchat &amp; in Gruppen nutzen\n"
                "• <code>/mode public</code> – Alle Telegram-Nutzer dürfen Berichte abrufen (Admins verwalten weiterhin)",
                parse_mode=ParseMode.HTML,
            )
            return

        new_mode = await asyncio.to_thread(set_telegram_access_mode, context.args[0].lower())
        self._log("INFO", f"Telegram-Zugriffsmodus geändert auf: {new_mode.upper()}")
        await update.effective_message.reply_text(
            f"✅ Bot-Zugriffsmodus wurde auf <b>{new_mode.upper()}</b> umgestellt!",
            parse_mode=ParseMode.HTML,
        )


telegram_bot_service = TelegramBotService()
