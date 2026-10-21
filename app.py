import csv
import io
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import config
from database import (
    build_streamer_bot_report,
    clear_demo_data,
    delete_streamer,
    delete_telegram_user,
    get_dashboard_overview,
    get_db,
    get_settings,
    get_streamer_by_id_or_username,
    get_streamer_detail,
    get_telegram_access_mode,
    init_db,
    list_telegram_users,
    record_gift_event,
    seed_demo_data,
    update_settings,
    upsert_streamer,
    upsert_telegram_user_permission,
)
from schemas import (
    DailyBotReportResponse,
    GiftCreateRequest,
    SettingsUpdateRequest,
    StreamerCreateRequest,
    StreamerReportCard,
    TelegramUserPermissionRequest,
    TrackActionRequest,
)
from telegram_service import generate_full_report_data, telegram_bot_service
from tiktok_service import TIKTOKLIVE_AVAILABLE, fetch_tiktok_user_info, monitor_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TIKTOK_GIFT_CATALOG = [
    {"id": 5655, "name": "Rose", "diamonds": 1},
    {"id": 5487, "name": "Finger Heart", "diamonds": 5},
    {"id": 5879, "name": "Doughnut", "diamonds": 30},
    {"id": 6104, "name": "Cap", "diamonds": 99},
    {"id": 5658, "name": "Corgi", "diamonds": 299},
    {"id": 5585, "name": "Money Gun", "diamonds": 500},
    {"id": 5827, "name": "Galaxy", "diamonds": 1000},
    {"id": 6267, "name": "Whale Diving", "diamonds": 2150},
    {"id": 5660, "name": "Sports Car", "diamonds": 7000},
    {"id": 6427, "name": "Sunset Speedway", "diamonds": 10000},
    {"id": 6369, "name": "Falcon", "diamonds": 10999},
    {"id": 7123, "name": "Dragon Flame", "diamonds": 26999},
    {"id": 5997, "name": "Lion", "diamonds": 29999},
    {"id": 9999, "name": "TikTok Universe", "diamonds": 44999},
]


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    FastAPI Lifespan:
    1. Initialisiert die Datenbank (SQLite oder MySQL)
    2. Startet automatisch alle TikTokLive-Worker für Streamer, die in der DB mit
       auto_monitor=1 oder is_tracking=1 markiert sind
    3. Startet optional den Telegram-Bot-Service (fehlertolerant isoliert: falls der Bot
       nicht starten kann, laufen FastAPI und das Web-Interface garantiert trotzdem weiter)
    """
    init_db()
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM streamers").fetchone()[0]
        if count == 0:
            seed_demo_data()

    monitor_manager.autostart_from_db()

    await telegram_bot_service.start()

    yield

    await telegram_bot_service.stop()
    monitor_manager.stop_all()


app = FastAPI(
    title="toktracker – Streamer Earnings & Bot API",
    description=(
        "toktracker Backend-Service zur Echtzeit-Erfassung von TikTokLive-Geschenken (Coins/Diamonds) "
        "mit fertigen 24h-Report- und Einzelabfrage-Endpoints, öffentlichem User-Panel sowie integriertem Telegram-Bot."
    ),
    version="2.4.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
if os.path.isdir(os.path.join(BASE_DIR, "pictures")):
    app.mount("/pictures", StaticFiles(directory=os.path.join(BASE_DIR, "pictures")), name="pictures")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    api_key: Optional[str] = Query(default=None, description="Optionaler API-Key per Query-Parameter"),
) -> None:
    configured_key = (config.api_key or get_settings().get("api_key") or "").strip()
    if not configured_key:
        return
    provided = (x_api_key or api_key or "").strip()
    if provided != configured_key:
        raise HTTPException(status_code=401, detail="Ungültiger oder fehlender API-Key (X-API-Key).")


def _enrich_streamer_card(streamer_row: Dict[str, Any], hours: int) -> StreamerReportCard:
    uname = streamer_row["username"]
    is_tracking = monitor_manager.is_tracking(uname)
    diag = monitor_manager.get_worker_diagnostics(uname)
    worker_state = diag["state"] if diag else ("live" if streamer_row.get("is_live") else "stopped")
    card_dict = build_streamer_bot_report(
        streamer_row=streamer_row,
        hours=hours,
        is_tracking_active=is_tracking,
        worker_state=worker_state,
    )
    return StreamerReportCard(**card_dict)


# =====================================================================
# 1. TOKTRACKER WEB-INTERFACE (ADMIN CONSOLE & PUBLIC USER PANEL)
# =====================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request):
    init_db()
    monitor_manager.autostart_from_db()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tiktoklive_available": TIKTOKLIVE_AVAILABLE,
            "gift_catalog": TIKTOK_GIFT_CATALOG,
            "env_summary": config.public_summary(),
            "telegram_diag": telegram_bot_service.get_diagnostics(),
        },
    )


@app.get("/public", response_class=HTMLResponse, include_in_schema=False)
@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def public_panel(request: Request):
    init_db()
    monitor_manager.autostart_from_db()
    tg_diag = telegram_bot_service.get_diagnostics()
    return templates.TemplateResponse(
        request=request,
        name="public.html",
        context={
            "telegram_bot_username": tg_diag.get("bot_username") or "",
            "telegram_state": tg_diag.get("state") or "offline",
        },
    )


# =====================================================================
# 1b. PUBLIC READ-ONLY API (FÜR DAS ÖFFENTLICHE USER-PANEL)
# =====================================================================

@app.get(
    "/api/public/overview",
    tags=["Public Panel API"],
    summary="Öffentliche Read-Only Übersicht für das User-Panel (ohne interne Logs/Whitelist)",
)
async def api_public_overview(period: str = Query("24h", description="all | today | 24h | 7d | 30d")):
    init_db()
    monitor_manager.autostart_from_db()
    raw = get_dashboard_overview(period=period)

    public_streamers = []
    for s in raw.get("streamers", []):
        uname = s["username"]
        public_streamers.append(
            {
                "id": s["id"],
                "username": uname,
                "display_name": s.get("display_name") or uname,
                "avatar_url": s.get("avatar_url") or "",
                "follower_count": s.get("follower_count") or 0,
                "current_viewers": s.get("current_viewers") or 0,
                "is_live": bool(s.get("is_live")),
                "is_tracking_active": monitor_manager.is_tracking(uname),
                "total_coins": s.get("total_coins") or 0,
                "gift_events_count": s.get("gift_events_count") or 0,
                "total_gifts_sent": s.get("total_gifts_sent") or 0,
                "unique_gifters": s.get("unique_gifters") or 0,
                "usd_net": s.get("usd_net") or 0.0,
                "eur_net": s.get("eur_net") or 0.0,
                "usd_gross": s.get("usd_gross") or 0.0,
                "eur_gross": s.get("eur_gross") or 0.0,
                "top_gift": s.get("top_gift"),
                "top_gifter": s.get("top_gifter"),
                "last_seen_at": s.get("last_seen_at"),
            }
        )

    cfg = raw.get("settings") or {}
    return {
        "period": raw.get("period", period),
        "totals": raw.get("totals", {}),
        "streamers": public_streamers,
        "recent_gifts": raw.get("recent_gifts", []),
        "rates": {
            "usd_per_diamond": cfg.get("usd_per_diamond", 0.005),
            "gross_usd_per_coin": cfg.get("gross_usd_per_coin", 0.0106),
            "usd_to_eur_rate": cfg.get("usd_to_eur_rate", 0.92),
        },
    }


@app.get(
    "/api/public/streamers/{identifier}",
    tags=["Public Panel API"],
    summary="Öffentliche Read-Only Detail-Auswertung eines Streamers",
)
async def api_public_streamer_detail(identifier: str, period: str = Query("24h")):
    init_db()
    s_row = get_streamer_by_id_or_username(identifier)
    if not s_row:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    detail = get_streamer_detail(s_row["id"], period=period)
    if not detail:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    s = detail["streamer"]
    uname = s["username"]
    return {
        "streamer": {
            "id": s["id"],
            "username": uname,
            "display_name": s.get("display_name") or uname,
            "avatar_url": s.get("avatar_url") or "",
            "follower_count": s.get("follower_count") or 0,
            "current_viewers": s.get("current_viewers") or 0,
            "is_live": bool(s.get("is_live")),
            "is_tracking_active": monitor_manager.is_tracking(uname),
        },
        "summary": detail.get("summary", {}),
        "gift_breakdown": detail.get("gift_breakdown", []),
        "top_gifters": detail.get("top_gifters", []),
        "sessions": detail.get("sessions", []),
    }


# =====================================================================
# 2. TELEGRAM-BOT SPEZIAL-ENDPOINTS (v1) – 24h Report, Einzelabfragen & Zugriffskontrolle
# =====================================================================

@app.get(
    "/api/v1/reports/daily",
    response_model=DailyBotReportResponse,
    tags=["Telegram Bot API"],
    summary="24h-Gesamtbericht über alle Streamer (für täglichen Telegram-Cronjob)",
    dependencies=[Depends(verify_api_key)],
)
async def api_v1_daily_report(
    hours: int = Query(24, ge=1, le=720, description="Auswertungszeitraum in Stunden (Standard: 24h)"),
    only_active: bool = Query(False, description="Wenn True, nur Streamer mit Einnahmen > 0 im Zeitraum"),
):
    init_db()
    report_data = generate_full_report_data(hours=hours, only_active=only_active)
    return DailyBotReportResponse(**report_data)


@app.post(
    "/api/v1/telegram/send-report",
    tags=["Telegram Bot API"],
    summary="Sendet den 24h-Bericht sofort über den integrierten Telegram-Bot",
    dependencies=[Depends(verify_api_key)],
)
async def api_v1_telegram_send_report(
    hours: int = Query(24, ge=1, le=720),
    chat_id: Optional[str] = Query(None, description="Optionale Ziel-Chat-ID (sonst TELEGRAM_CHAT_ID aus .env)"),
):
    init_db()
    res = await telegram_bot_service.send_report_now(chat_id=chat_id, hours=hours)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Senden fehlgeschlagen"))
    return res


@app.get(
    "/api/telegram/users",
    tags=["Telegram Bot API"],
    summary="Listet alle Telegram-Nutzer (Whitelist, Admins & offene Anfragen) sowie den Zugriffsmodus",
    dependencies=[Depends(verify_api_key)],
)
@app.get(
    "/api/v1/telegram/users",
    tags=["Telegram Bot API"],
    summary="Listet alle Telegram-Nutzer (Whitelist, Admins & offene Anfragen) sowie den Zugriffsmodus",
    dependencies=[Depends(verify_api_key)],
)
async def api_get_telegram_users():
    init_db()
    return {
        "access_mode": get_telegram_access_mode(),
        "users": list_telegram_users(),
    }


@app.post(
    "/api/telegram/users",
    tags=["Telegram Bot API"],
    summary="Fügt einen Telegram-Nutzer per ID oder @username zur Whitelist hinzu oder ändert seine Rolle",
    dependencies=[Depends(verify_api_key)],
)
@app.post(
    "/api/v1/telegram/users",
    tags=["Telegram Bot API"],
    summary="Fügt einen Telegram-Nutzer per ID oder @username zur Whitelist hinzu oder ändert seine Rolle",
    dependencies=[Depends(verify_api_key)],
)
async def api_upsert_telegram_user(payload: TelegramUserPermissionRequest):
    init_db()
    try:
        user_row = upsert_telegram_user_permission(
            identifier=payload.identifier,
            is_allowed=payload.is_allowed,
            role=payload.role,
            first_name=payload.first_name,
            note=payload.note,
        )
        return {"ok": True, "user": user_row, "access_mode": get_telegram_access_mode()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete(
    "/api/telegram/users/{record_id}",
    tags=["Telegram Bot API"],
    summary="Entfernt einen Telegram-Nutzer aus der Datenbank",
    dependencies=[Depends(verify_api_key)],
)
@app.delete(
    "/api/v1/telegram/users/{record_id}",
    tags=["Telegram Bot API"],
    summary="Entfernt einen Telegram-Nutzer aus der Datenbank",
    dependencies=[Depends(verify_api_key)],
)
async def api_delete_telegram_user(record_id: int):
    init_db()
    deleted = delete_telegram_user(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Telegram-Nutzer nicht gefunden.")
    return {"ok": True, "deleted_id": record_id}


@app.get(
    "/api/v1/streamers/{identifier}/report",
    response_model=StreamerReportCard,
    tags=["Telegram Bot API"],
    summary="Einzelabfrage für einen bestimmten Streamer per @username oder ID",
    dependencies=[Depends(verify_api_key)],
)
async def api_v1_streamer_single_report(
    identifier: str,
    hours: int = Query(24, ge=1, le=8760, description="Zeitraum in Stunden für die Auswertung (Standard: 24h)"),
):
    init_db()
    streamer = get_streamer_by_id_or_username(identifier)
    if not streamer:
        raise HTTPException(
            status_code=404,
            detail=f"Streamer '{identifier}' wurde nicht in der Datenbank gefunden.",
        )
    return _enrich_streamer_card(streamer, hours=hours)


# =====================================================================
# 3. ALLGEMEINE BACKEND- & MANAGEMENT-ENDPOINTS (auch unter /api/v1/...)
# =====================================================================

@app.get("/api/overview", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.get("/api/v1/overview", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_overview(period: str = Query("all", description="all | today | 24h | 7d | 30d")):
    init_db()
    monitor_manager.autostart_from_db()
    data = get_dashboard_overview(period=period)
    for s in data["streamers"]:
        uname = s["username"]
        s["is_tracking_active"] = monitor_manager.is_tracking(uname)
        s["monitor_status"] = monitor_manager.get_status(uname)
        s["worker_diagnostics"] = monitor_manager.get_worker_diagnostics(uname)
    sys_diag = monitor_manager.get_all_diagnostics()
    sys_diag["telegram_bot"] = telegram_bot_service.get_diagnostics()
    data["system"] = sys_diag
    data["gift_catalog"] = TIKTOK_GIFT_CATALOG
    return data


@app.get("/api/system/status", tags=["System & Workers"], dependencies=[Depends(verify_api_key)])
@app.get("/api/v1/system/status", tags=["System & Workers"], dependencies=[Depends(verify_api_key)])
async def api_system_status():
    diag = monitor_manager.get_all_diagnostics()
    diag["telegram_bot"] = telegram_bot_service.get_diagnostics()
    return diag


@app.get("/api/streamers/{identifier}", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.get("/api/v1/streamers/{identifier}", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_streamer_detail(identifier: str, period: str = Query("all")):
    init_db()
    s_row = get_streamer_by_id_or_username(identifier)
    if not s_row:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    detail = get_streamer_detail(s_row["id"], period=period)
    if not detail:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    uname = detail["streamer"]["username"]
    detail["streamer"]["is_tracking_active"] = monitor_manager.is_tracking(uname)
    detail["streamer"]["monitor_status"] = monitor_manager.get_status(uname)
    detail["streamer"]["worker_diagnostics"] = monitor_manager.get_worker_diagnostics(uname)
    return detail


@app.post("/api/streamers", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.post("/api/v1/streamers", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_add_streamer(payload: StreamerCreateRequest):
    init_db()
    username = payload.username.strip().lstrip("@").lower()
    if not username:
        raise HTTPException(status_code=400, detail="Bitte einen gültigen TikTok @username eingeben.")

    profile = fetch_tiktok_user_info(username)
    display_name = payload.display_name or profile.get("display_name") or username

    streamer = upsert_streamer(
        username=username,
        display_name=display_name,
        avatar_url=profile.get("avatar_url"),
        room_id=profile.get("room_id"),
        follower_count=profile.get("follower_count"),
        is_live=profile.get("is_live"),
        auto_monitor=payload.auto_track and payload.auto_reconnect,
    )

    track_info = None
    if payload.auto_track:
        track_info = monitor_manager.start_tracking(
            streamer["id"], streamer["username"], auto_reconnect=payload.auto_reconnect
        )

    return {
        "ok": True,
        "streamer": streamer,
        "profile_fetched": profile,
        "tracking": track_info,
    }


@app.post("/api/streamers/{identifier}/refresh", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.post("/api/v1/streamers/{identifier}/refresh", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_refresh_streamer(identifier: str):
    init_db()
    row = get_streamer_by_id_or_username(identifier)
    if not row:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    profile = fetch_tiktok_user_info(row["username"])
    updated = upsert_streamer(
        username=row["username"],
        display_name=profile.get("display_name") or row["display_name"],
        avatar_url=profile.get("avatar_url") or row["avatar_url"],
        room_id=profile.get("room_id"),
        follower_count=profile.get("follower_count") or row["follower_count"],
        is_live=profile.get("is_live"),
    )
    return {"ok": True, "streamer": updated, "profile": profile}


@app.post("/api/streamers/{identifier}/track", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.post("/api/v1/streamers/{identifier}/track", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_toggle_tracking(identifier: str, payload: Optional[TrackActionRequest] = None):
    init_db()
    req = payload or TrackActionRequest()
    row = get_streamer_by_id_or_username(identifier)
    if not row:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    username = row["username"]
    currently_tracking = monitor_manager.is_tracking(username)

    if req.action == "stop" or (req.action == "toggle" and currently_tracking):
        return monitor_manager.stop_tracking(username)
    return monitor_manager.start_tracking(
        row["id"], username, auto_reconnect=req.auto_reconnect
    )


@app.delete("/api/streamers/{identifier}", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.delete("/api/v1/streamers/{identifier}", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_delete_streamer(identifier: str):
    init_db()
    row = get_streamer_by_id_or_username(identifier)
    if not row:
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden")

    monitor_manager.stop_tracking(row["username"])
    delete_streamer(row["id"])
    return {"ok": True, "deleted_username": row["username"]}


@app.post("/api/gifts", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
@app.post("/api/v1/gifts", tags=["Telegram Bot API"], dependencies=[Depends(verify_api_key)])
async def api_record_gift(payload: GiftCreateRequest):
    init_db()
    streamer_id = payload.streamer_id
    if not streamer_id and payload.username:
        s = upsert_streamer(username=payload.username)
        streamer_id = s["id"]

    if not streamer_id:
        raise HTTPException(status_code=400, detail="streamer_id oder username erforderlich.")

    sender_username = payload.sender_username.strip().lstrip("@") or "live_viewer"
    sender_nickname = (payload.sender_nickname or sender_username).strip()

    event, created = record_gift_event(
        streamer_id=int(streamer_id),
        sender_username=sender_username,
        sender_nickname=sender_nickname,
        gift_name=payload.gift_name.strip(),
        diamond_count=payload.diamond_count,
        repeat_count=payload.repeat_count,
        source=payload.source,
    )
    return {"ok": True, "created": created, "event": event}


@app.get("/api/export/gifts.csv", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
async def api_export_gifts_csv(streamer_id: Optional[int] = Query(None)):
    init_db()
    with get_db() as conn:
        if streamer_id:
            rows = conn.execute(
                """
                SELECT g.*, s.username AS streamer_username
                FROM gift_events g
                JOIN streamers s ON s.id = g.streamer_id
                WHERE g.streamer_id = ?
                ORDER BY g.created_at DESC
                """,
                (streamer_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT g.*, s.username AS streamer_username
                FROM gift_events g
                JOIN streamers s ON s.id = g.streamer_id
                ORDER BY g.created_at DESC
                """
            ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "id",
            "created_at",
            "streamer_username",
            "session_id",
            "sender_username",
            "sender_nickname",
            "is_super_fan",
            "gift_id",
            "gift_name",
            "diamond_count",
            "repeat_count",
            "total_coins",
            "usd_net",
            "eur_net",
            "usd_gross",
            "eur_gross",
            "source",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["created_at"],
                r["streamer_username"],
                r["session_id"],
                r["sender_username"],
                r["sender_nickname"],
                r["is_super_fan"],
                r["gift_id"],
                r["gift_name"],
                r["diamond_count"],
                r["repeat_count"],
                r["total_coins"],
                r["usd_net"],
                r["eur_net"],
                r["usd_gross"],
                r["eur_gross"],
                r["source"],
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=toktracker_gifts_export.csv"},
    )


@app.get("/api/settings", tags=["System & Workers"], dependencies=[Depends(verify_api_key)])
async def api_get_settings():
    init_db()
    return get_settings()


@app.post("/api/settings", tags=["System & Workers"], dependencies=[Depends(verify_api_key)])
async def api_update_settings(payload: SettingsUpdateRequest):
    init_db()
    updated = update_settings(payload.model_dump(exclude_none=True))
    return {"ok": True, "settings": updated}


@app.post("/api/demo/seed", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
async def api_seed_demo():
    init_db()
    seed_demo_data()
    return {"ok": True, "message": "Demo-Daten geladen."}


@app.post("/api/demo/clear", tags=["Dashboard & Data"], dependencies=[Depends(verify_api_key)])
async def api_clear_demo():
    init_db()
    removed = clear_demo_data()
    return {"ok": True, "removed": removed}


if __name__ == "__main__":
    uvicorn.run("app:app", host=config.app_host, port=config.app_port, reload=False)
