"""
TokTracker - Revenue-Berechnung für TikTok-LIVE-Gifts.

Die hier berechneten Werte sind bewusst als Schätzung modelliert:
- `diamond_count` aus dem TikTok-Event entspricht dem Coin-Preis des Gifts.
- Der Coin-Preis ist regionalen Bundle-/Store-Schwankungen unterworfen.
- Der Creator-Anteil, Agency-/Payout-Abzüge und Steuern sind konfigurierbar.
- Historische Events speichern ihre Faktoren als Snapshot, damit spätere
  Profiländerungen die Vergangenheit nicht rückwirkend verändern.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Sinnvolle Defaults für ein deutsches Standardprofil.
DEFAULT_COIN_PRICE_USD = 0.0105
DEFAULT_CREATOR_SHARE = 0.50
DEFAULT_FX_RATE = 0.92
DEFAULT_COIN_PRICE_UNCERTAINTY = 0.10
DEFAULT_CREATOR_SHARE_UNCERTAINTY = 0.05
DEFAULT_AGENCY_MAX = 0.15
DEFAULT_TAX_MAX = 0.30
DEFAULT_FX_UNCERTAINTY = 0.02


def _float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Normalisiert ein DB-Profil (inkl. Decimal/String-Werten) zu Floats."""
    p = profile or {}
    return {
        "coin_price_usd": max(0.0, _float(p.get("coin_price_usd"), DEFAULT_COIN_PRICE_USD)),
        "creator_share_pct": _clamp(
            _float(p.get("creator_share_pct"), DEFAULT_CREATOR_SHARE), 0.0, 1.0
        ),
        "agency_share_pct": _clamp(
            _float(p.get("agency_share_pct"), 0.0), 0.0, 0.95
        ),
        "payout_fee_pct": _clamp(
            _float(p.get("payout_fee_pct"), 0.0), 0.0, 0.95
        ),
        "tax_pct": _clamp(_float(p.get("tax_pct"), 0.0), 0.0, 0.95),
        "fx_rate": max(0.0, _float(p.get("fx_rate"), DEFAULT_FX_RATE)),
        "coin_price_uncertainty_pct": _clamp(
            _float(
                p.get("coin_price_uncertainty_pct"),
                DEFAULT_COIN_PRICE_UNCERTAINTY,
            ),
            0.0,
            0.95,
        ),
        "creator_share_uncertainty_pct": _clamp(
            _float(
                p.get("creator_share_uncertainty_pct"),
                DEFAULT_CREATOR_SHARE_UNCERTAINTY,
            ),
            0.0,
            0.95,
        ),
        "agency_share_max_pct": _clamp(
            _float(p.get("agency_share_max_pct"), DEFAULT_AGENCY_MAX), 0.0, 0.95
        ),
        "tax_max_pct": _clamp(
            _float(p.get("tax_max_pct"), DEFAULT_TAX_MAX), 0.0, 0.95
        ),
        "fx_uncertainty_pct": _clamp(
            _float(p.get("fx_uncertainty_pct"), DEFAULT_FX_UNCERTAINTY),
            0.0,
            0.95,
        ),
    }


def compute_gift_revenue(
    total_coins: int,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """
    Berechnet Brutto/Netto sowie eine realistische Bandbreite für ein Gift.

    Rückgabe (alle Werte auf 4 Nachkommastellen gerundet):
    usd_net, eur_net, usd_gross, eur_gross,
    usd_net_low, usd_net_high, eur_net_low, eur_net_high
    """
    coins = max(0, int(total_coins or 0))
    p = normalize_profile(profile)

    coin_price = p["coin_price_usd"]
    creator_share = p["creator_share_pct"]
    agency = p["agency_share_pct"]
    payout_fee = p["payout_fee_pct"]
    tax = p["tax_pct"]
    fx = p["fx_rate"]

    gross_usd = coins * coin_price
    net_usd = gross_usd * creator_share * (1.0 - agency) * (1.0 - payout_fee) * (1.0 - tax)
    net_eur = net_usd * fx

    coin_low = coin_price * (1.0 - p["coin_price_uncertainty_pct"])
    coin_high = coin_price * (1.0 + p["coin_price_uncertainty_pct"])
    share_low = creator_share * (1.0 - p["creator_share_uncertainty_pct"])
    share_high = creator_share * (1.0 + p["creator_share_uncertainty_pct"])
    agency_high = max(agency, p["agency_share_max_pct"])
    tax_high = max(tax, p["tax_max_pct"])
    fx_low = fx * (1.0 - p["fx_uncertainty_pct"])
    fx_high = fx * (1.0 + p["fx_uncertainty_pct"])

    common_low = (1.0 - payout_fee) * (1.0 - tax_high)
    common_high = (1.0 - payout_fee) * (1.0 - tax)
    net_usd_low = coins * coin_low * share_low * (1.0 - agency_high) * common_low
    net_usd_high = coins * coin_high * share_high * (1.0 - agency) * common_high

    return {
        "usd_net": round(net_usd, 4),
        "eur_net": round(net_eur, 4),
        "usd_gross": round(gross_usd, 4),
        "eur_gross": round(gross_usd * fx, 4),
        "usd_net_low": round(net_usd_low, 4),
        "usd_net_high": round(net_usd_high, 4),
        "eur_net_low": round(net_usd_low * fx_low, 4),
        "eur_net_high": round(net_usd_high * fx_high, 4),
    }


def revenue_range(
    usd_net: float,
    eur_net: float,
    usd_net_low: Optional[float],
    usd_net_high: Optional[float],
    eur_net_low: Optional[float],
    eur_net_high: Optional[float],
) -> Dict[str, float]:
    """Fallback für Legacy-Daten ohne gespeicherte Bandbreite."""
    return {
        "usd_net": float(usd_net or 0.0),
        "eur_net": float(eur_net or 0.0),
        "usd_net_low": float(usd_net_low if usd_net_low is not None else usd_net or 0.0),
        "usd_net_high": float(usd_net_high if usd_net_high is not None else usd_net or 0.0),
        "eur_net_low": float(eur_net_low if eur_net_low is not None else eur_net or 0.0),
        "eur_net_high": float(eur_net_high if eur_net_high is not None else eur_net or 0.0),
    }
