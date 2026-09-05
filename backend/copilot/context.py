"""
context.py – Assembles a structured analytics context for the Gemini copilot.

This context is the single source of truth passed to the LLM so it can
answer questions by citing concrete, pre-computed numbers.
"""

from __future__ import annotations
from datetime import timedelta
from typing import Any

from backend.data.seed import TODAY
from backend.analytics.inventory import (
    compute_inventory_status,
    low_stock_products,
    overstock_products,
    slow_movers,
    stockout_risk_products,
)
from backend.analytics.sales import (
    period_summary,
    month_over_month,
    top_products_by_revenue,
    detect_anomalies,
    aggregate_by_category,
)
from backend.analytics.alerts import generate_all_alerts, alerts_summary


def build_copilot_context(
    products: list[dict[str, Any]],
    sales: list[dict[str, Any]],
    products_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute all deterministic analytics and return a rich context dict.
    This is called on every /api/copilot request, ensuring fresh numbers.
    """
    # Index sales by product
    sales_by_product: dict[str, list[dict]] = {}
    for r in sales:
        sales_by_product.setdefault(r["product_id"], []).append(r)

    # Inventory enrichment
    inventory = compute_inventory_status(products, sales_by_product)

    # Alerts
    alerts = generate_all_alerts(inventory, sales_by_product, products_by_id)

    # Last 30 days of sales for category totals
    cutoff_30 = (TODAY - timedelta(days=30)).isoformat()
    sales_30d = [r for r in sales if r["date"] >= cutoff_30]

    return {
        "summary_30d": period_summary(sales, 30),
        "summary_7d":  period_summary(sales, 7),
        "summary_90d": period_summary(sales, 90),
        "mom": month_over_month(sales),
        "top_products_30d": top_products_by_revenue(sales, products_by_id, 30, 10),
        "category_totals_30d": aggregate_by_category(sales_30d, products_by_id),
        "inventory": {
            "low_stock":     low_stock_products(inventory),
            "overstock":     overstock_products(inventory),
            "slow_movers":   slow_movers(inventory),
            "stockout_risk": stockout_risk_products(inventory),
            "all":           inventory,
        },
        "alerts":        alerts,
        "alerts_summary": alerts_summary(alerts),
        "anomalies":     detect_anomalies(sales_by_product),
    }
