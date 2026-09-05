"""
alerts.py – Prioritised alert generation for RetailIQ.

Each alert has:
  id          : unique stable identifier
  severity    : 'critical' | 'warning' | 'info'
  type        : alert category string
  title       : short human headline
  description : detailed sentence with concrete numbers
  product_id  : (optional) affected product
  product_name: (optional)
  data        : dict of raw numbers supporting the alert
  assumptions : list of strings describing what was assumed
  recommendation : actionable instruction

Alerts are fully deterministic. The LLM copilot uses these as context.
"""

from __future__ import annotations
from typing import Any

from backend.analytics.inventory import (
    stockout_risk_products,
    overstock_products,
    slow_movers,
    low_stock_products,
)
from backend.analytics.sales import detect_anomalies


def _alert_id(prefix: str, product_id: str | None, suffix: str = "") -> str:
    parts = [prefix]
    if product_id:
        parts.append(product_id)
    if suffix:
        parts.append(suffix)
    return "_".join(parts).lower()


# ─── Individual alert builders ─────────────────────────────────────────────────

def _stockout_alerts(inventory: list[dict]) -> list[dict[str, Any]]:
    alerts = []
    for p in stockout_risk_products(inventory):
        dos = p["days_of_stock"]
        lead = p["supplier_lead_days"]
        shortfall = p.get("shortfall_units", 0)
        severity = "critical" if dos < lead else "warning"
        alerts.append({
            "id": _alert_id("stockout", p["id"]),
            "severity": severity,
            "type": "stockout_risk",
            "title": f"Stock-out risk: {p['name']}",
            "description": (
                f"{p['name']} has {p['current_stock']} units left "
                f"({dos:.1f} days of stock). Supplier lead time is {lead} days. "
                f"Estimated shortfall before restock: {shortfall} units."
            ),
            "product_id": p["id"],
            "product_name": p["name"],
            "data": {
                "current_stock": p["current_stock"],
                "days_of_stock": dos,
                "avg_daily_units_30d": p["avg_daily_units_30d"],
                "supplier_lead_days": lead,
                "reorder_point": p["reorder_point"],
                "shortfall_units": shortfall,
            },
            "assumptions": [
                f"Future demand equals the 30-day average of {p['avg_daily_units_30d']} units/day.",
                "No emergency restock or inter-store transfer assumed.",
                f"Supplier lead time is exactly {lead} days (no delays).",
            ],
            "recommendation": (
                f"Place a purchase order immediately for at least "
                f"{max(shortfall, p['reorder_point'])} units of {p['name']}. "
                f"If the supplier cannot deliver in {lead} days, consider an emergency sourcing option."
            ),
        })
    return alerts


def _overstock_alerts(inventory: list[dict]) -> list[dict[str, Any]]:
    alerts = []
    for p in overstock_products(inventory):
        dos = p["days_of_stock"]
        capital_locked = round(p["current_stock"] * p["cost_price"], 2)
        alerts.append({
            "id": _alert_id("overstock", p["id"]),
            "severity": "warning",
            "type": "overstock",
            "title": f"Overstock: {p['name']}",
            "description": (
                f"{p['name']} has {p['current_stock']} units in stock "
                f"({dos:.0f} days of supply at current demand). "
                f"Capital locked: ₹{capital_locked:,.2f}."
            ),
            "product_id": p["id"],
            "product_name": p["name"],
            "data": {
                "current_stock": p["current_stock"],
                "days_of_stock": dos,
                "avg_daily_units_30d": p["avg_daily_units_30d"],
                "capital_locked_inr": capital_locked,
                "cost_price": p["cost_price"],
            },
            "assumptions": [
                f"Demand remains at 30-day average of {p['avg_daily_units_30d']} units/day.",
                "No seasonal demand surge expected in the near term.",
                "Capital lock-up calculated at cost price, not retail price.",
            ],
            "recommendation": (
                f"Consider a promotional discount or bundle offer for {p['name']} "
                f"to accelerate sell-through. Pause any pending reorder for this SKU. "
                f"Target reducing stock to a 30-day level "
                f"({round(p['avg_daily_units_30d'] * 30)} units)."
            ),
        })
    return alerts


def _slow_mover_alerts(inventory: list[dict]) -> list[dict[str, Any]]:
    alerts = []
    for p in slow_movers(inventory):
        alerts.append({
            "id": _alert_id("slowmover", p["id"]),
            "severity": "info",
            "type": "slow_mover",
            "title": f"Slow mover: {p['name']}",
            "description": (
                f"{p['name']} sold an average of {p['avg_daily_units_30d']} units/day "
                f"in the last 30 days — significantly below the {p['category']} category average. "
                f"Current stock: {p['current_stock']} units."
            ),
            "product_id": p["id"],
            "product_name": p["name"],
            "data": {
                "avg_daily_units_30d": p["avg_daily_units_30d"],
                "current_stock": p["current_stock"],
                "category": p["category"],
            },
            "assumptions": [
                "Slow-mover threshold: product demand < 25% of category average daily demand.",
                "Comparison is within the same category only.",
            ],
            "recommendation": (
                f"Review pricing, placement, and marketing for {p['name']}. "
                "Consider a limited-time discount or cross-promotion. "
                "If slow movement persists for another 2 weeks, evaluate clearance pricing."
            ),
        })
    return alerts


def _anomaly_alerts(
    sales_by_product: dict[str, list[dict]],
    products_by_id: dict[str, dict],
) -> list[dict[str, Any]]:
    alerts = []
    anomalies = detect_anomalies(sales_by_product)
    for event in anomalies[:10]:  # cap to top-10 most recent
        pid = event["product_id"]
        p = products_by_id.get(pid, {})
        pname = p.get("name", pid)
        if event["type"] == "spike":
            severity = "info"
            rec = (
                f"Investigate the cause of the spike for {pname}. "
                "If demand is sustainably higher, increase the reorder point and stock level. "
                "Check if a promotion, event, or viral moment drove this."
            )
        else:
            severity = "warning"
            rec = (
                f"Investigate the sales drop for {pname}. "
                "Check for competitor activity, shelf availability, pricing changes, or quality complaints. "
                "Consider a targeted promotion if the drop persists."
            )
        alerts.append({
            "id": _alert_id(event["type"], pid, event["date"]),
            "severity": severity,
            "type": f"sales_{event['type']}",
            "title": f"Sales {event['type']}: {pname}",
            "description": event["description"],
            "product_id": pid,
            "product_name": pname,
            "data": {
                "date": event["date"],
                "units_sold": event["units_sold"],
                "baseline_mean": event["baseline_mean"],
                "baseline_std": event["baseline_std"],
                "z_score": event["z_score"],
            },
            "assumptions": [
                f"Baseline: 30-day mean = {event['baseline_mean']} units, "
                f"σ = {event['baseline_std']} units.",
                f"Spike threshold: z > {2.0}; Drop threshold: z < -{1.8}.",
                "Baseline window excludes the most recent 7 days to avoid contamination.",
            ],
            "recommendation": rec,
        })
    return alerts


# ─── Public entry point ───────────────────────────────────────────────────────

def generate_all_alerts(
    inventory: list[dict[str, Any]],
    sales_by_product: dict[str, list[dict[str, Any]]],
    products_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Produce the full prioritised alert list.
    Order: critical → warning → info.
    """
    severity_rank = {"critical": 0, "warning": 1, "info": 2}

    all_alerts: list[dict[str, Any]] = []
    all_alerts.extend(_stockout_alerts(inventory))
    all_alerts.extend(_overstock_alerts(inventory))
    all_alerts.extend(_slow_mover_alerts(inventory))
    all_alerts.extend(_anomaly_alerts(sales_by_product, products_by_id))

    return sorted(all_alerts, key=lambda a: severity_rank.get(a["severity"], 99))


def alerts_summary(alerts: list[dict[str, Any]]) -> dict[str, int]:
    """Return count of alerts by severity."""
    return {
        "critical": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning": sum(1 for a in alerts if a["severity"] == "warning"),
        "info": sum(1 for a in alerts if a["severity"] == "info"),
        "total": len(alerts),
    }
