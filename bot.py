"""
TokTracker - Dedizierter Telegram Bot Service
=============================================
Dieser Service läuft als eigenständiger Prozess / Docker-Container (toktracker_bot)
und steuert die gesamte Telegram-Bot-Integration:
- Empfangen von Bot-Befehlen (/start, /report, /streamer, /whitelist etc.)
- 2FA- und 1-Klick-Admin-Web-Login-Genehmigungen per Telegram-Push
- Automatisierte periodische 24h-Reports und Speicherplatzüberwachung

Bietet eine interne HTTP-API auf Port 5002 für Healthchecks, Bot-Diagnosen
und das Versenden von Login-Challenges und Reports aus dem Web-Dashboard.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, Query
from pydantic import BaseModel

from config import config
from database import init_db
from telegram_service import admin_auth_manager, telegram_bot_service

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] toktracker_bot: %(message)s",
)
logger = logging.getLogger("toktracker_bot")

BOT_SERVICE_PORT = int(os.getenv("BOT_PORT", "5002"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TokTracker Bot-Service startet...")
    init_db()

    # Telegram Bot starten
    await telegram_bot_service.start()

    yield

    # Shutdown
    logger.info("TokTracker Bot-Service fährt herunter...")
    await telegram_bot_service.stop()


app = FastAPI(
    title="TokTracker Telegram Bot Service",
    description="Interner Telegram Bot Service & 2FA Auth Daemon",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check():
    diag = telegram_bot_service.get_diagnostics()
    return {
        "ok": True,
        "service": "toktracker_bot",
        "state": diag.get("state", "offline"),
        "bot_username": diag.get("bot_username", ""),
    }


@app.get("/api/diagnostics", tags=["Diagnostics"])
async def get_diagnostics():
    """Liefert die Telegram-Bot-Diagnose für das Web-Dashboard."""
    return telegram_bot_service.get_diagnostics()


class ChallengeNotificationRequest(BaseModel):
    identifier_hint: Optional[str] = None
    client_info: str = "Web-Browser"


@app.post("/api/notify-challenge", tags=["2FA Auth"])
async def notify_admin_challenge(payload: ChallengeNotificationRequest):
    """
    Sendet sofort eine Login-Push-Benachrichtigung mit Inline-Buttons an alle registrierten Telegram-Admins.
    """
    res = await telegram_bot_service.send_admin_login_challenge(
        identifier_hint=payload.identifier_hint,
        client_info=payload.client_info,
    )
    return {"ok": True, "result": res}


class ReportRequest(BaseModel):
    chat_id: Optional[int] = None
    hours: int = 24


@app.post("/api/send-report", tags=["Reports"])
async def send_report(payload: ReportRequest):
    """Löst den sofortigen Versand eines Umsatzreports an einen Telegram-Chat aus."""
    res = await telegram_bot_service.send_report_now(
        chat_id=payload.chat_id,
        hours=payload.hours,
    )
    return {"ok": True, "result": res}


def main():
    logger.info("Starte Telegram Bot Service auf Port %d...", BOT_SERVICE_PORT)
    uvicorn.run(app, host="0.0.0.0", port=BOT_SERVICE_PORT, log_level="info")


if __name__ == "__main__":
    main()
