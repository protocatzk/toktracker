"""
TokTracker - Revenue-Profile & Snapshot-Berechnung.

Ein Revenue-Profil bündelt die Annahmen für Brutto-Coinpreis, Creator-Anteil,
Agency-/Payout-/Steuer-Abzüge, FX-Kurs und die Unsicherheitsbandbreite.
Streamer können ein eigenes Profil erhalten; ohne Zuordnung gilt das
Standardprofil.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.db._base import get_db

_DEFAULT_PROFILE = {
    "name": "DE Standard",
    "gross_region": "DE",
    "creator_region": "DE",
    "coin_price_usd": 0.0105,
    "creator_share_pct": 0.50,
    "agency_share_pct": 0.0,
    "payout_fee_pct": 0.0,
    "tax_pct": 0.0,
    "coin_price_uncertainty_pct": 0.10,
    "creator_share_uncertainty_pct": 0.05,
    "agency_share_max_pct": 0.10,
    "tax_max_pct": 0.20,
    "fx_rate": 0.92,
    "fx_uncertainty_pct": 0.02,
    "is_default": 1,
    "valid_from": "2026-11-01T00:00:00",
}

_PAKISTAN_PROFILE = {
    **_DEFAULT_PROFILE,
    "name": "Pakistan (DE-Zuschauer)",
    "creator_region": "PK",
    "is_default": 0,
}

_CACHE_TTL_SECONDS = 60.0
_profile_cache: Dict[int, tuple[float, Dict[str, Any]]] = {}
_profile_cache_lock = threading.Lock()


def _invalidate_profile_cache() -> None:
    with _profile_cache_lock:
        _profile_cache.clear()
    try:
        from shared.db.analytics import invalidate_overview_cache

        invalidate_overview_cache()
    except Exception:
        pass


def _profile_insert(profile: Dict[str, Any]) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO revenue_profiles (
                name, gross_region, creator_region,
                coin_price_usd, creator_share_pct, agency_share_pct,
                payout_fee_pct, tax_pct,
                coin_price_uncertainty_pct, creator_share_uncertainty_pct,
                agency_share_max_pct, tax_max_pct,
                fx_rate, fx_uncertainty_pct,
                is_default, valid_from, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile["name"],
                profile["gross_region"],
                profile["creator_region"],
                float(profile["coin_price_usd"]),
                float(profile["creator_share_pct"]),
                float(profile["agency_share_pct"]),
                float(profile["payout_fee_pct"]),
                float(profile["tax_pct"]),
                float(profile["coin_price_uncertainty_pct"]),
                float(profile["creator_share_uncertainty_pct"]),
                float(profile["agency_share_max_pct"]),
                float(profile["tax_max_pct"]),
                float(profile["fx_rate"]),
                float(profile["fx_uncertainty_pct"]),
                int(profile.get("is_default") or 0),
                profile["valid_from"],
                now,
            ),
        )
        return int(cur.lastrowid)


def ensure_revenue_profiles() -> None:
    """Legt Default-Profile an und ordnet Streamern ohne Profil das Default zu."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, is_default FROM revenue_profiles ORDER BY id").fetchall()

    if not rows:
        _profile_insert(_DEFAULT_PROFILE)
        _profile_insert(_PAKISTAN_PROFILE)

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, is_default FROM revenue_profiles ORDER BY id"
        ).fetchall()
        if rows and not any(int(r["is_default"] or 0) for r in rows):
            conn.execute(
                "UPDATE revenue_profiles SET is_default = 1 WHERE id = ?",
                (int(rows[0]["id"]),),
            )
        default_row = conn.execute(
            "SELECT id FROM revenue_profiles WHERE is_default = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if default_row:
            conn.execute(
                """
                UPDATE streamers
                SET revenue_profile_id = ?
                WHERE revenue_profile_id IS NULL
                """,
                (int(default_row["id"]),),
            )
    _invalidate_profile_cache()


def list_revenue_profiles() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM revenue_profiles ORDER BY is_default DESC, name ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_revenue_profile(profile_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM revenue_profiles WHERE id = ?", (int(profile_id),)
        ).fetchone()
        return dict(row) if row else None


def get_default_revenue_profile() -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM revenue_profiles WHERE is_default = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM revenue_profiles ORDER BY id LIMIT 1"
            ).fetchone()
        return dict(row) if row else None


def get_revenue_profile_for_streamer(streamer_id: int) -> Optional[Dict[str, Any]]:
    """Liefert das Streamer-Profil mit kurzem In-Process-Cache."""
    now = time.monotonic()
    with _profile_cache_lock:
        cached = _profile_cache.get(int(streamer_id))
        if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1].copy()

    profile: Optional[Dict[str, Any]] = None
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT p.*
            FROM streamers s
            JOIN revenue_profiles p ON p.id = s.revenue_profile_id
            WHERE s.id = ?
            """,
            (int(streamer_id),),
        ).fetchone()
        if row:
            profile = dict(row)
    if profile is None:
        profile = get_default_revenue_profile()

    if profile is not None:
        with _profile_cache_lock:
            _profile_cache[int(streamer_id)] = (now, profile.copy())
    return profile


def update_revenue_profile(profile_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {
        "name": str,
        "gross_region": str,
        "creator_region": str,
        "coin_price_usd": float,
        "creator_share_pct": float,
        "agency_share_pct": float,
        "payout_fee_pct": float,
        "tax_pct": float,
        "coin_price_uncertainty_pct": float,
        "creator_share_uncertainty_pct": float,
        "agency_share_max_pct": float,
        "tax_max_pct": float,
        "fx_rate": float,
        "fx_uncertainty_pct": float,
        "is_default": int,
    }
    updates = []
    params: List[Any] = []
    for key, caster in allowed.items():
        if key not in data or data[key] is None:
            continue
        updates.append(f"{key} = ?")
        params.append(caster(data[key]))
    if not updates:
        return get_revenue_profile(profile_id)

    with get_db() as conn:
        if int(data.get("is_default") or 0) == 1:
            conn.execute("UPDATE revenue_profiles SET is_default = 0")
        params.append(int(profile_id))
        conn.execute(
            f"UPDATE revenue_profiles SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
    _invalidate_profile_cache()
    return get_revenue_profile(profile_id)


def assign_streamer_revenue_profile(streamer_id: int, profile_id: Optional[int]) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE streamers SET revenue_profile_id = ? WHERE id = ?",
            (int(profile_id) if profile_id else None, int(streamer_id)),
        )
        ok = (getattr(cur, "rowcount", 0) or 0) > 0
        if not ok:
            # MySQL meldet rowcount=0, wenn der Wert bereits identisch ist.
            ok = (
                conn.execute(
                    "SELECT id FROM streamers WHERE id = ?", (int(streamer_id),)
                ).fetchone()
                is not None
            )
    _invalidate_profile_cache()
    return ok


def revenue_profile_summary(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Sichere, JSON-freundliche Kurzfassung für API/UI."""
    if not profile:
        return {}
    return {
        "id": int(profile.get("id") or 0),
        "name": profile.get("name") or "",
        "gross_region": profile.get("gross_region") or "",
        "creator_region": profile.get("creator_region") or "",
        "coin_price_usd": float(profile.get("coin_price_usd") or 0.0),
        "creator_share_pct": float(profile.get("creator_share_pct") or 0.0),
        "agency_share_pct": float(profile.get("agency_share_pct") or 0.0),
        "payout_fee_pct": float(profile.get("payout_fee_pct") or 0.0),
        "tax_pct": float(profile.get("tax_pct") or 0.0),
        "fx_rate": float(profile.get("fx_rate") or 0.0),
        "coin_price_uncertainty_pct": float(
            profile.get("coin_price_uncertainty_pct") or 0.0
        ),
        "creator_share_uncertainty_pct": float(
            profile.get("creator_share_uncertainty_pct") or 0.0
        ),
        "agency_share_max_pct": float(profile.get("agency_share_max_pct") or 0.0),
        "tax_max_pct": float(profile.get("tax_max_pct") or 0.0),
        "fx_uncertainty_pct": float(profile.get("fx_uncertainty_pct") or 0.0),
        "valid_from": profile.get("valid_from") or "",
        "is_default": int(profile.get("is_default") or 0),
    }
