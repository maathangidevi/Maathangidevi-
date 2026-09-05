"""
sales.py – Pure deterministic sales analytics for RetailIQ.

All computations are statistical / arithmetic; no LLM calls.

Spike/drop detection uses a rolling z-score against a 30-day baseline:
  z = (day_units - μ) / σ
  spike if z > SPIKE_Z_THRESHOLD
  drop  if z < -DROP_Z_THRESHOLD  (and μ > MIN_BASELINE_DEMAND)
"""

from __future__ import annotations
from datetime import date, timedelta
from collections import defaultdict
from statistics import mean, stdev, StatisticsError
from typing import Any

from backend.data.seed import TODAY

# ─── Thresholds ──────────────────────────────────────────────────────────────
SPIKE_Z_THRESHOLD = 2.0
DROP_Z_THRESHOLD = 1.8
MIN_BASELINE_DEMAND = 1.0  # ignore products with near-zero avg


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


# ─── Core aggregations ───────────────────────────────────────────────────────

def aggregate_by_day(sales: list[dict]) -> dict[str, dict[str, Any]]:
    """Return {date_str: {units, revenue}} summed across all products."""
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
    for r in sales:
        agg[r["date"]]["units_sold"] += r["units_sold"]
        agg[r["date"]]["revenue"] += r["revenue"]
    return dict(agg)


def aggregate_by_product(sales: list[dict]) -> dict[str, dict[str, Any]]:
    """Return {product_id: {units, revenue}} totals."""
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
    for r in sales:
        agg[r["product_id"]]["units_sold"] += r["units_sold"]
        agg[r["product_id"]]["revenue"] += r["revenue"]
    return {k: dict(v) for k, v in agg.items()}


def aggregate_by_category(
    sales: list[dict],
    products_by_id: dict[str, dict],
) -> dict[str, dict[str, Any]]:
    """Return {category: {units, revenue}} totals."""
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
    for r in sales:
        cat = products_by_id.get(r["product_id"], {}).get("category", "Unknown")
        agg[cat]["units_sold"] += r["units_sold"]
        agg[cat]["revenue"] += r["revenue"]
    return {k: dict(v) for k, v in agg.items()}


# ─── Period helpers ───────────────────────────────────────────────────────────

def _filter_days(sales: list[dict], days: int) -> list[dict]:
    cutoff = (TODAY - timedelta(days=days)).isoformat()
    return [r for r in sales if r["date"] >= cutoff]


def period_summary(sales: list[dict], days: int) -> dict[str, Any]:
    """Total units, revenue, and avg daily revenue for last `days` days."""
    recent = _filter_days(sales, days)
    total_units = sum(r["units_sold"] for r in recent)
    total_rev = sum(r["revenue"] for r in recent)
    return {
        "period_days": days,
        "total_units": total_units,
        "total_revenue": round(total_rev, 2),
        "avg_daily_revenue": round(total_rev / max(days, 1), 2),
        "record_count": len(recent),
    }


def month_over_month(sales: list[dict]) -> dict[str, Any]:
    """
    Compare last 30 days vs previous 30 days (days 31–60).
    Returns absolute and percentage change for units and revenue.
    """
    this_month = _filter_days(sales, 30)
    last_month = [
        r for r in sales
        if (TODAY - timedelta(days=60)).isoformat() <= r["date"]
        < (TODAY - timedelta(days=30)).isoformat()
    ]

    def totals(records: list[dict]) -> tuple[int, float]:
        return (
            sum(r["units_sold"] for r in records),
            round(sum(r["revenue"] for r in records), 2),
        )

    u_cur, r_cur = totals(this_month)
    u_prv, r_prv = totals(last_month)

    def pct(cur: float, prv: float) -> float | None:
        if prv == 0:
            return None
        return round((cur - prv) / prv * 100, 1)

    return {
        "current_30d": {"units": u_cur, "revenue": r_cur},
        "previous_30d": {"units": u_prv, "revenue": r_prv},
        "units_change_pct": pct(u_cur, u_prv),
        "revenue_change_pct": pct(r_cur, r_prv),
    }


# ─── Spike / drop detection ───────────────────────────────────────────────────

def detect_anomalies(
    sales_by_product: dict[str, list[dict]],
    lookback_days: int = 30,
    anomaly_window: int = 7,
) -> list[dict[str, Any]]:
    """
    For each product, compute z-score for the last `anomaly_window` days
    against a `lookback_days` baseline.  Return events where |z| exceeds
    threshold.

    Assumption: Baseline is the 30-day window immediately before the
    anomaly_window. Products with < 14 baseline days are skipped (insufficient
    data).
    """
    events: list[dict[str, Any]] = []

    for pid, sales in sales_by_product.items():
        sorted_s = sorted(sales, key=lambda r: r["date"])
        baseline_end = TODAY - timedelta(days=anomaly_window)
        baseline_start = baseline_end - timedelta(days=lookback_days)

        baseline = [
            r["units_sold"] for r in sorted_s
            if baseline_start.isoformat() <= r["date"] < baseline_end.isoformat()
        ]
        recent_days = [
            r for r in sorted_s
            if r["date"] >= (TODAY - timedelta(days=anomaly_window)).isoformat()
        ]

        if len(baseline) < 10:
            continue  # insufficient baseline data

        try:
            mu = mean(baseline)
            sd = stdev(baseline)
        except StatisticsError:
            continue

        if sd < 0.5 or mu < MIN_BASELINE_DEMAND:
            continue

        for r in recent_days:
            z = (r["units_sold"] - mu) / sd
            if z >= SPIKE_Z_THRESHOLD:
                events.append({
                    "product_id": pid,
                    "date": r["date"],
                    "type": "spike",
                    "units_sold": r["units_sold"],
                    "baseline_mean": round(mu, 2),
                    "baseline_std": round(sd, 2),
                    "z_score": round(z, 2),
                    "description": (
                        f"Sales of {r['units_sold']} units on {r['date']} "
                        f"are {round(z,1)}σ above the {lookback_days}-day mean "
                        f"of {round(mu,1)} units."
                    ),
                })
            elif z <= -DROP_Z_THRESHOLD:
                events.append({
                    "product_id": pid,
                    "date": r["date"],
                    "type": "drop",
                    "units_sold": r["units_sold"],
                    "baseline_mean": round(mu, 2),
                    "baseline_std": round(sd, 2),
                    "z_score": round(z, 2),
                    "description": (
                        f"Sales of {r['units_sold']} units on {r['date']} "
                        f"are {abs(round(z,1))}σ below the {lookback_days}-day mean "
                        f"of {round(mu,1)} units."
                    ),
                })

    return sorted(events, key=lambda e: e["date"], reverse=True)


# ─── Top performers ───────────────────────────────────────────────────────────

def top_products_by_revenue(
    sales: list[dict],
    products_by_id: dict[str, dict],
    days: int = 30,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Top N products by revenue in last `days` days."""
    recent = _filter_days(sales, days)
    agg = aggregate_by_product(recent)
    result = []
    for pid, totals in agg.items():
        p = products_by_id.get(pid, {})
        result.append({
            "product_id": pid,
            "name": p.get("name", "Unknown"),
            "category": p.get("category", "Unknown"),
            "units_sold": totals["units_sold"],
            "revenue": round(totals["revenue"], 2),
        })
    return sorted(result, key=lambda x: -x["revenue"])[:top_n]


def daily_revenue_series(sales: list[dict], days: int = 90) -> list[dict[str, Any]]:
    """
    Return sorted list of {date, units_sold, revenue} for last `days` days.
    Fills gaps (days with zero sales) automatically.
    """
    recent = _filter_days(sales, days)
    agg = aggregate_by_day(recent)

    result = []
    for d_offset in range(-days, 0):
        d = TODAY + timedelta(days=d_offset)
        key = d.isoformat()
        entry = agg.get(key, {"units_sold": 0, "revenue": 0.0})
        result.append({
            "date": key,
            "units_sold": entry["units_sold"],
            "revenue": round(entry["revenue"], 2),
        })
    return result
