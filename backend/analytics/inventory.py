"""
inventory.py – Pure deterministic inventory analytics for RetailIQ.

All functions take product dicts and sales records; no I/O or LLM calls.

Key thresholds (can be tuned without touching business logic):
  LOW_STOCK_THRESHOLD       product.current_stock < product.reorder_point
  CRITICAL_DAYS_THRESHOLD   days_of_stock < supplier_lead_days + 2
  OVERSTOCK_DAYS_THRESHOLD  days_of_stock > 90
  SLOW_MOVER_RATIO          last_30d_units < 0.25 × category_avg_30d
"""

from __future__ import annotations
from statistics import mean, stdev
from collections import defaultdict
from typing import Any


# ─── Thresholds ──────────────────────────────────────────────────────────────
OVERSTOCK_DAYS_THRESHOLD = 90      # > 90 days of stock = overstock
SLOW_MOVER_RATIO = 0.25            # < 25% of category avg = slow mover
CRITICAL_DAYS_THRESHOLD_EXTRA = 2  # lead time + 2 safety buffer


def _avg_daily_units(sales: list[dict], days: int = 30) -> float:
    """Average daily units sold over last `days` days, minimum of 1 record."""
    if not sales:
        return 0.0
    sorted_sales = sorted(sales, key=lambda s: s["date"], reverse=True)
    recent = sorted_sales[:days]
    total_units = sum(r["units_sold"] for r in recent)
    return total_units / max(len(recent), 1)


def _days_of_stock(current_stock: int, avg_daily: float) -> float:
    """How many days current stock will last at current demand."""
    if avg_daily <= 0:
        return float("inf")
    return current_stock / avg_daily


def compute_inventory_status(
    products: list[dict[str, Any]],
    sales_by_product: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Enrich each product with inventory analytics fields.

    Added keys
    ----------
    avg_daily_units_30d : float
    days_of_stock       : float  (inf → 'effectively unlimited')
    stock_status        : 'critical' | 'low' | 'overstock' | 'normal'
    is_low_stock        : bool
    is_overstock        : bool
    is_slow_mover       : bool   (computed after category aggregation)
    reorder_urgency     : 'critical' | 'soon' | 'ok'
    """
    # First pass: compute avg_daily and days_of_stock
    enriched = []
    for p in products:
        pid = p["id"]
        sales = sales_by_product.get(pid, [])
        avg_30 = _avg_daily_units(sales, 30)
        dos = _days_of_stock(p["current_stock"], avg_30)
        lead = p["supplier_lead_days"]

        if avg_30 == 0:
            stock_status = "normal"
            reorder_urgency = "ok"
        elif dos < lead + CRITICAL_DAYS_THRESHOLD_EXTRA:
            stock_status = "critical"
            reorder_urgency = "critical"
        elif p["current_stock"] < p["reorder_point"]:
            stock_status = "low"
            reorder_urgency = "soon"
        elif dos > OVERSTOCK_DAYS_THRESHOLD:
            stock_status = "overstock"
            reorder_urgency = "ok"
        else:
            stock_status = "normal"
            reorder_urgency = "ok"

        enriched.append({
            **p,
            "avg_daily_units_30d": round(avg_30, 2),
            "days_of_stock": round(dos, 1) if dos != float("inf") else 999,
            "stock_status": stock_status,
            "is_low_stock": stock_status in ("low", "critical"),
            "is_overstock": stock_status == "overstock",
            "reorder_urgency": reorder_urgency,
            "is_slow_mover": False,  # filled in second pass
        })

    # Second pass: slow-mover detection per category
    cat_avgs: dict[str, list[float]] = defaultdict(list)
    for ep in enriched:
        cat_avgs[ep["category"]].append(ep["avg_daily_units_30d"])

    cat_mean: dict[str, float] = {
        cat: mean(vals) for cat, vals in cat_avgs.items() if vals
    }

    for ep in enriched:
        cat_avg = cat_mean.get(ep["category"], 0)
        if cat_avg > 0 and ep["avg_daily_units_30d"] < cat_avg * SLOW_MOVER_RATIO:
            ep["is_slow_mover"] = True

    return enriched


def low_stock_products(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return products with is_low_stock=True, sorted by days_of_stock asc."""
    return sorted(
        [p for p in inventory if p["is_low_stock"]],
        key=lambda p: p["days_of_stock"],
    )


def overstock_products(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return products with is_overstock=True, sorted by days_of_stock desc."""
    return sorted(
        [p for p in inventory if p["is_overstock"]],
        key=lambda p: -p["days_of_stock"],
    )


def slow_movers(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in inventory if p["is_slow_mover"]]


def stockout_risk_products(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Products predicted to stock-out before the next resupply arrives,
    sorted by urgency.
    """
    at_risk = []
    for p in inventory:
        dos = p["days_of_stock"]
        lead = p["supplier_lead_days"]
        if dos <= lead + CRITICAL_DAYS_THRESHOLD_EXTRA and p["avg_daily_units_30d"] > 0:
            at_risk.append({
                **p,
                "estimated_stockout_in_days": round(dos, 1),
                "shortfall_units": round(
                    max(0, (lead + CRITICAL_DAYS_THRESHOLD_EXTRA - dos) * p["avg_daily_units_30d"])
                ),
            })
    return sorted(at_risk, key=lambda p: p["days_of_stock"])
