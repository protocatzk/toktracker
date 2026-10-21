import csv
import io
from flask import Flask, Response, jsonify, render_template, request
from database import (
    clear_demo_data,
    delete_streamer,
    get_dashboard_overview,
    get_db,
    get_settings,
    get_streamer_detail,
    init_db,
    record_gift_event,
    seed_demo_data,
    update_settings,
    upsert_streamer,
)
from tiktok_service import TIKTOKLIVE_AVAILABLE, fetch_tiktok_user_info, monitor_manager

app = Flask(__name__)

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

init_db()
with get_db() as _conn:
    _count = _conn.execute("SELECT COUNT(*) FROM streamers").fetchone()[0]
    if _count == 0:
        seed_demo_data()


@app.route("/")
def index():
    return render_template(
        "index.html",
        tiktoklive_available=TIKTOKLIVE_AVAILABLE,
        gift_catalog=TIKTOK_GIFT_CATALOG,
    )


@app.route("/api/overview", methods=["GET"])
def api_overview():
    period = request.args.get("period", "all")
    data = get_dashboard_overview(period=period)
    for s in data["streamers"]:
        uname = s["username"]
        s["is_tracking_active"] = monitor_manager.is_tracking(uname)
        s["monitor_status"] = monitor_manager.get_status(uname)
        s["worker_diagnostics"] = monitor_manager.get_worker_diagnostics(uname)
    data["system"] = monitor_manager.get_all_diagnostics()
    data["gift_catalog"] = TIKTOK_GIFT_CATALOG
    return jsonify(data)


@app.route("/api/system/status", methods=["GET"])
def api_system_status():
    """Backend-Diagnose-Endpoint für alle TikTokLive-Worker und Hintergrundprozesse."""
    return jsonify(monitor_manager.get_all_diagnostics())


@app.route("/api/streamers/<int:streamer_id>", methods=["GET"])
def api_streamer_detail(streamer_id: int):
    period = request.args.get("period", "all")
    detail = get_streamer_detail(streamer_id, period=period)
    if not detail:
        return jsonify({"error": "Streamer nicht gefunden"}), 404
    uname = detail["streamer"]["username"]
    detail["streamer"]["is_tracking_active"] = monitor_manager.is_tracking(uname)
    detail["streamer"]["monitor_status"] = monitor_manager.get_status(uname)
    detail["streamer"]["worker_diagnostics"] = monitor_manager.get_worker_diagnostics(uname)
    return jsonify(detail)


@app.route("/api/streamers", methods=["POST"])
def api_add_streamer():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip().lstrip("@").lower()
    auto_track = bool(payload.get("auto_track", False))
    auto_reconnect = bool(payload.get("auto_reconnect", True))

    if not username:
        return jsonify({"error": "Bitte einen gültigen TikTok @username eingeben."}), 400

    profile = fetch_tiktok_user_info(username)
    display_name = payload.get("display_name") or profile.get("display_name") or username

    streamer = upsert_streamer(
        username=username,
        display_name=display_name,
        avatar_url=profile.get("avatar_url"),
        room_id=profile.get("room_id"),
        follower_count=profile.get("follower_count"),
        is_live=profile.get("is_live"),
        auto_monitor=auto_track and auto_reconnect,
    )

    track_info = None
    if auto_track:
        track_info = monitor_manager.start_tracking(
            streamer["id"], streamer["username"], auto_reconnect=auto_reconnect
        )

    return jsonify(
        {
            "ok": True,
            "streamer": streamer,
            "profile_fetched": profile,
            "tracking": track_info,
        }
    )


@app.route("/api/streamers/<int:streamer_id>/refresh", methods=["POST"])
def api_refresh_streamer(streamer_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Streamer nicht gefunden"}), 404

    profile = fetch_tiktok_user_info(row["username"])
    updated = upsert_streamer(
        username=row["username"],
        display_name=profile.get("display_name") or row["display_name"],
        avatar_url=profile.get("avatar_url") or row["avatar_url"],
        room_id=profile.get("room_id"),
        follower_count=profile.get("follower_count") or row["follower_count"],
        is_live=profile.get("is_live"),
    )
    return jsonify({"ok": True, "streamer": updated, "profile": profile})


@app.route("/api/streamers/<int:streamer_id>/track", methods=["POST"])
def api_toggle_tracking(streamer_id: int):
    payload = request.get_json(silent=True) or {}
    action = payload.get("action", "toggle")
    auto_reconnect = bool(payload.get("auto_reconnect", True))

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Streamer nicht gefunden"}), 404

    username = row["username"]
    currently_tracking = monitor_manager.is_tracking(username)

    if action == "stop" or (action == "toggle" and currently_tracking):
        res = monitor_manager.stop_tracking(username)
    else:
        res = monitor_manager.start_tracking(
            streamer_id, username, auto_reconnect=auto_reconnect
        )

    return jsonify(res)


@app.route("/api/streamers/<int:streamer_id>", methods=["DELETE"])
def api_delete_streamer(streamer_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM streamers WHERE id = ?", (streamer_id,)
        ).fetchone()
    if row:
        monitor_manager.stop_tracking(row["username"])

    deleted = delete_streamer(streamer_id)
    if not deleted:
        return jsonify({"error": "Streamer nicht gefunden"}), 404
    return jsonify({"ok": True})


@app.route("/api/gifts", methods=["POST"])
def api_record_gift():
    payload = request.get_json(silent=True) or {}
    streamer_id = payload.get("streamer_id")
    username = payload.get("username")

    if not streamer_id and username:
        s = upsert_streamer(username=username)
        streamer_id = s["id"]

    if not streamer_id:
        return jsonify({"error": "streamer_id oder username erforderlich."}), 400

    gift_name = (payload.get("gift_name") or "Rose").strip()
    diamond_count = int(payload.get("diamond_count") or 1)
    repeat_count = int(payload.get("repeat_count") or 1)
    sender_username = (payload.get("sender_username") or "live_viewer").strip().lstrip("@")
    sender_nickname = (payload.get("sender_nickname") or sender_username).strip()
    source = payload.get("source") or "manual"

    event, created = record_gift_event(
        streamer_id=int(streamer_id),
        sender_username=sender_username,
        sender_nickname=sender_nickname,
        gift_name=gift_name,
        diamond_count=diamond_count,
        repeat_count=repeat_count,
        source=source,
    )
    return jsonify({"ok": True, "created": created, "event": event})


@app.route("/api/export/gifts.csv", methods=["GET"])
def api_export_gifts_csv():
    """CSV-Export aller erfassten Gift-Events (optional gefiltert nach streamer_id)."""
    streamer_id = request.args.get("streamer_id", type=int)
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
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=tiktok_gifts_export.csv"},
    )


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify(get_settings())
    payload = request.get_json(silent=True) or {}
    updated = update_settings(payload)
    return jsonify({"ok": True, "settings": updated})


@app.route("/api/demo/seed", methods=["POST"])
def api_seed_demo():
    seed_demo_data()
    return jsonify({"ok": True, "message": "Demo-Daten geladen."})


@app.route("/api/demo/clear", methods=["POST"])
def api_clear_demo():
    removed = clear_demo_data()
    return jsonify({"ok": True, "removed": removed})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
