"""
Revenue-Profile: Liste, Bearbeitung und Zuordnung zu Streamern.
"""

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from shared.api_deps import require_permission
from shared.database import (
    assign_streamer_revenue_profile,
    get_db,
    get_revenue_profile,
    init_db,
    list_revenue_profiles,
    revenue_profile_summary,
    update_revenue_profile,
)
from shared.permissions import PERM_SETTINGS_MANAGE, PERM_STREAMERS_MANAGE

router = APIRouter()


@router.get(
    "/api/revenue/profiles",
    tags=["Revenue"],
    dependencies=[Depends(require_permission(PERM_SETTINGS_MANAGE))],
)
def api_revenue_profiles():
    init_db()
    with get_db() as conn:
        streamer_rows = conn.execute(
            """
            SELECT id, username, display_name, revenue_profile_id
            FROM streamers
            ORDER BY username ASC
            """
        ).fetchall()
    return {
        "profiles": [revenue_profile_summary(p) for p in list_revenue_profiles()],
        "streamers": [
            {
                "id": int(s["id"]),
                "username": s["username"],
                "display_name": s.get("display_name") or s["username"],
                "revenue_profile_id": s.get("revenue_profile_id"),
            }
            for s in streamer_rows
        ],
    }


@router.post(
    "/api/revenue/profiles/{profile_id}",
    tags=["Revenue"],
    dependencies=[Depends(require_permission(PERM_SETTINGS_MANAGE))],
)
def api_update_revenue_profile(
    profile_id: int,
    payload: Dict[str, Any] = Body(...),
):
    init_db()
    updated = update_revenue_profile(profile_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Revenue-Profil nicht gefunden.")
    return {"ok": True, "profile": revenue_profile_summary(updated)}


@router.post(
    "/api/revenue/assign",
    tags=["Revenue"],
    dependencies=[Depends(require_permission(PERM_STREAMERS_MANAGE))],
)
def api_assign_revenue_profile(payload: Dict[str, Any] = Body(...)):
    init_db()
    raw_streamer_id = payload.get("streamer_id")
    if raw_streamer_id is None:
        raise HTTPException(status_code=400, detail="streamer_id fehlt oder ist ungültig.")
    try:
        streamer_id = int(raw_streamer_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="streamer_id fehlt oder ist ungültig.") from None
    profile_id = payload.get("profile_id")
    if profile_id is not None:
        try:
            profile_id = int(profile_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="profile_id ist ungültig.") from None
        if not get_revenue_profile(profile_id):
            raise HTTPException(status_code=404, detail="Revenue-Profil nicht gefunden.")
    if not assign_streamer_revenue_profile(streamer_id, profile_id):
        raise HTTPException(status_code=404, detail="Streamer nicht gefunden.")
    return {"ok": True}
