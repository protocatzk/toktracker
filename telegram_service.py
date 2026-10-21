import asyncio
import html
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional

try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
    )
    PTB_AVAILABLE = True
except ImportError:
    PTB_AVAILABLE = False
    Update = Any  # type: ignore
    ContextTypes = Any  # type: ignore

from config import config
from database import (
    build_streamer_bot_report,
    get_db,
    get_settings,
    get_streamer_by_id_or_username,
    upsert_streamer,
)
from tiktok_service import fetch_tiktok_user_info, monitor_manager

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
        f"📋 *TikTok Streamer Einnahmen-Report ({hours}h)*",
        f"🕒 Stand: `{now.strftime('%d.%m.%Y %H:%M')}`",
        f"💰 *Gesamt Netto ({hours}h):* `{total_period_eur_net:,.2f} €` (`${total_period_usd_net:,.2f}`)",
        f"🪙 *Gesamt Coins ({hours}h):* `{total_period_coins:,}` ({total_gifts_sent:,} Gifts)",
        f"📡 *Streamer:* {len(cards)} überwacht ({live_now} aktuell LIVE)",
        "────────────────────────",
    ]
    html_lines = [
        f"<b>📋 TikTok Streamer Einnahmen-Report ({hours}h)</b>",
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
    `python-telegram-bot` (v22+) SDKs inkl. `JobQueue` für den automatischen 24h-Bericht.

    WICHTIG (Fehlertoleranz):
    - Wenn kein Token gesetzt ist, das Token ungültig ist oder Telegram nicht erreichbar ist,
      fängt dieser Service alle Fehler intern ab.
    - Die FastAPI-Anwendung und das Web-Interface starten und laufen IMMER unabhängig weiter!
    """

    def __init__(self) -> None:
        self._app: Optional[Any] = None
        self._state: str = "disabled"  # disabled | starting | running | error | stopped
        self._last_error: str = ""
        self._bot_username: str = ""
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
        return {
            "sdk_available": PTB_AVAILABLE,
            "state": self._state,
            "bot_username": self._bot_username,
            "has_token": bool(config.telegram_bot_token),
            "default_chat_id": config.telegram_chat_id,
            "started_at": self._started_at,
            "last_report_sent_at": self._last_report_sent_at,
            "last_error": self._last_error,
            "logs": list(self._logs)[:15],
        }

    async def start(self) -> None:
        """
        Startet den Telegram-Bot asynchron im Hintergrund.
        Wirft NIEMALS eine Exception nach außen, damit FastAPI garantiert hochfährt.
        """
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

            # Befehls-Handler registrieren
            self._app.add_handler(CommandHandler(["start", "help"], self._cmd_help))
            self._app.add_handler(CommandHandler("report", self._cmd_report))
            self._app.add_handler(CommandHandler(["streamer", "stats"], self._cmd_streamer))
            self._app.add_handler(CommandHandler("add", self._cmd_add_streamer))
            self._app.add_handler(CommandHandler("track", self._cmd_track_streamer))
            self._app.add_handler(CommandHandler("stop", self._cmd_stop_streamer))
            self._app.add_handler(CommandHandler("status", self._cmd_status))

            await self._app.initialize()
            bot_me = await self._app.bot.get_me()
            self._bot_username = f"@{bot_me.username}" if bot_me.username else str(bot_me.id)

            await self._app.start()
            if self._app.updater:
                await self._app.updater.start_polling(drop_pending_updates=True)

            # 24h wiederkehrenden Bericht-Job in der offiziellen PTB JobQueue planen
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
            self._log("INFO", f"Telegram-Bot ({self._bot_username}) erfolgreich gestartet!")

        except Exception as exc:
            self._state = "error"
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._log(
                "ERROR",
                f"Telegram-Bot konnte nicht gestartet werden ({self._last_error}). FastAPI & Web laufen weiter.",
            )
            await self._safe_cleanup()

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

    async def send_report_now(
        self, chat_id: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        """Sendet den 24h-Bericht sofort an die konfigurierte oder übergebene Chat-ID."""
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
            report = generate_full_report_data(hours=hours)
            await self._app.bot.send_message(
                chat_id=target_chat,
                text=report["telegram_html"],
                parse_mode=ParseMode.HTML,
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
            report = generate_full_report_data(hours=24)
            await context.bot.send_message(
                chat_id=target_chat,
                text=report["telegram_html"],
                parse_mode=ParseMode.HTML,
            )
            self._last_report_sent_at = datetime.now().isoformat(timespec="seconds")
            self._log("INFO", f"Automatischer 24h-Bericht an Chat {target_chat} gesendet.")
        except Exception as exc:
            self._log("ERROR", f"Fehler im 24h-Report-Job: {exc}")

    # =================================================================
    # TELEGRAM BOT COMMAND HANDLERS
    # =================================================================

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        text = (
            "<b>🤖 TikTok Streamer Earnings Bot</b>\n\n"
            f"Deine aktuelle Chat-ID: <code>{chat_id}</code>\n"
            "<i>(Trage diese als TELEGRAM_CHAT_ID in die .env ein für den automatischen 24h-Bericht)</i>\n\n"
            "<b>Verfügbare Befehle:</b>\n"
            "• <code>/report</code> oder <code>/report 24</code> – Gesamtbericht aller Streamer (Standard 24h)\n"
            "• <code>/streamer &lt;username&gt; [stunden]</code> – Einzelabfrage für einen Streamer\n"
            "• <code>/add &lt;username&gt;</code> – Streamer hinzufügen &amp; Tracking starten\n"
            "• <code>/track &lt;username&gt;</code> – Live-Worker für Streamer starten\n"
            "• <code>/stop &lt;username&gt;</code> – Live-Worker für Streamer stoppen\n"
            "• <code>/status</code> – Laufzeit-Status aller TikTokLive-Worker"
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        hours = 24
        if context.args and context.args[0].isdigit():
            hours = max(1, min(720, int(context.args[0])))

        report = await asyncio.to_thread(generate_full_report_data, hours, False)
        await update.effective_message.reply_text(
            report["telegram_html"], parse_mode=ParseMode.HTML
        )

    async def _cmd_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message:
            return
        if not context.args:
            await update.effective_message.reply_text(
                "Bitte einen TikTok-Username angeben, z.B.:\n<code>/streamer arbrita.a</code>",
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
            f"<b>📊 Streamer-Einzelabfrage: {html.escape(card['display_name'])}</b> (@{html.escape(uname)})\n"
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
        if not update.effective_message or not context.args:
            return
        s_row = await asyncio.to_thread(get_streamer_by_id_or_username, context.args[0])
        if not s_row:
            await update.effective_message.reply_text("❌ Streamer nicht gefunden.")
            return
        res = monitor_manager.start_tracking(s_row["id"], s_row["username"], auto_reconnect=True)
        await update.effective_message.reply_text(f"▶️ {res.get('message')}")

    async def _cmd_stop_streamer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not context.args:
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
        diag = monitor_manager.get_all_diagnostics()
        workers = diag.get("workers", [])
        lines = [
            "<b>⚙️ Backend &amp; Worker Status</b>",
            f"Aktive Worker: <b>{diag['workers_running']}</b> ({diag['workers_connected']} im Stream verbunden)",
        ]
        for w in workers:
            lines.append(
                f"• <b>@{html.escape(w['username'])}</b>: <code>{w['state']}</code> "
                f"(Viewers: {w['current_viewers']}, Session-Coins: {w['coins_received_session']:,})"
            )
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


telegram_bot_service = TelegramBotService()
