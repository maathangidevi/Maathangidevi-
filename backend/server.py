"""
server.py – FastAPI application for RetailIQ.

Endpoints
---------
GET  /                  → serves frontend index.html
GET  /api/dashboard     → KPI summary cards
GET  /api/products      → full product catalogue with inventory status
GET  /api/sales         → daily sales series + aggregations
GET  /api/alerts        → prioritised alert list
POST /api/copilot       → AI copilot (Gemini-backed with deterministic context)
"""

from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.data.store import get_store
from backend.analytics.inventory import compute_inventory_status
from backend.analytics.sales import (
    period_summary,
    month_over_month,
    top_products_by_revenue,
    daily_revenue_series,
    aggregate_by_category,
    detect_anomalies,
)
from backend.analytics.alerts import generate_all_alerts, alerts_summary
from backend.copilot.context import build_copilot_context
from backend.copilot.gemini import ask_copilot

# ─── App setup ────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(
    title="RetailIQ API",
    description="NexusTiq24 Retail Sales & Inventory Copilot – PS03",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets (CSS, JS)
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
if (FRONTEND_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_sales_by_product(sales: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for r in sales:
        result[r["product_id"]].append(r)
    return dict(result)


def _get_inventory(store) -> list[dict]:
    sbp = _get_sales_by_product(store.sales)
    return compute_inventory_status(store.products, sbp)


# ─── Frontend route ───────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "RetailIQ API is running. Frontend not found."})


# ─── API: Dashboard ───────────────────────────────────────────────────────────

@app.get("/api/dashboard", tags=["Dashboard"])
async def get_dashboard() -> JSONResponse:
    """
    Returns all KPI cards for the dashboard:
    - Revenue (30d, 7d, MoM %)
    - Units sold
    - Inventory health (low-stock count, overstock count)
    - Alert summary
    - Top 5 products by revenue (30d)
    - Category breakdown (30d)
    - Daily revenue series (90d) for the chart
    """
    store = get_store()
    sbp = _get_sales_by_product(store.sales)
    inventory = compute_inventory_status(store.products, sbp)
    alerts = generate_all_alerts(inventory, sbp, store.products_by_id)

    s30 = period_summary(store.sales, 30)
    s7 = period_summary(store.sales, 7)
    s90 = period_summary(store.sales, 90)
    mom = month_over_month(store.sales)
    top5 = top_products_by_revenue(store.sales, store.products_by_id, 30, 5)
    series = daily_revenue_series(store.sales, 90)
    cat_totals = aggregate_by_category(store.sales, store.products_by_id)

    low_stock_list = [p for p in inventory if p["is_low_stock"]]
    overstock_list = [p for p in inventory if p["is_overstock"]]
    slow_list = [p for p in inventory if p["is_slow_mover"]]
    critical_alerts = [a for a in alerts if a["severity"] == "critical"]

    # Total gross profit (cost price known)
    total_revenue_30d = s30["total_revenue"]
    cost_30d = sum(
        r["units_sold"] * store.products_by_id.get(r["product_id"], {}).get("cost_price", 0)
        for r in store.sales
        if r["date"] >= (
            __import__("datetime").date.fromisoformat(min(x["date"] for x in store.sales))
        ).isoformat()
    )

    # Simpler: compute gross margin from 30d sales
    cost_30d_accurate = 0.0
    from backend.data.seed import TODAY
    from datetime import timedelta
    cutoff_30 = (TODAY - timedelta(days=30)).isoformat()
    for r in store.sales:
        if r["date"] >= cutoff_30:
            p = store.products_by_id.get(r["product_id"], {})
            cost_30d_accurate += r["units_sold"] * p.get("cost_price", 0)
    gross_margin_30d = round(total_revenue_30d - cost_30d_accurate, 2)
    gross_margin_pct = round(gross_margin_30d / total_revenue_30d * 100, 1) if total_revenue_30d else 0

    return JSONResponse({
        "store": store.store_info,
        "kpis": {
            "revenue_30d": s30["total_revenue"],
            "revenue_7d": s7["total_revenue"],
            "revenue_90d": s90["total_revenue"],
            "units_30d": s30["total_units"],
            "units_7d": s7["total_units"],
            "avg_daily_revenue_30d": s30["avg_daily_revenue"],
            "gross_margin_30d": gross_margin_30d,
            "gross_margin_pct_30d": gross_margin_pct,
            "mom_revenue_change_pct": mom["revenue_change_pct"],
            "mom_units_change_pct": mom["units_change_pct"],
            "mom_detail": mom,
        },
        "inventory_health": {
            "low_stock_count": len(low_stock_list),
            "overstock_count": len(overstock_list),
            "slow_mover_count": len(slow_list),
            "total_products": len(store.products),
            "healthy_count": len(store.products) - len(low_stock_list) - len(overstock_list),
            "low_stock_products": [
                {"id": p["id"], "name": p["name"], "current_stock": p["current_stock"],
                 "days_of_stock": p["days_of_stock"], "reorder_point": p["reorder_point"],
                 "stock_status": p["stock_status"]}
                for p in sorted(low_stock_list, key=lambda x: x["days_of_stock"])[:5]
            ],
            "overstock_products": [
                {"id": p["id"], "name": p["name"], "current_stock": p["current_stock"],
                 "days_of_stock": p["days_of_stock"]}
                for p in overstock_list[:5]
            ],
        },
        "alerts_summary": alerts_summary(alerts),
        "critical_alerts": critical_alerts[:5],
        "top_products_30d": top5,
        "category_breakdown_30d": [
            {"category": k, "units_sold": v["units_sold"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(cat_totals.items(), key=lambda x: -x[1]["revenue"])
        ],
        "daily_series_90d": series,
    })


# ─── API: Products ────────────────────────────────────────────────────────────

@app.get("/api/products", tags=["Products"])
async def get_products(
    category: str | None = None,
    status: str | None = None,
) -> JSONResponse:
    """
    Returns enriched product list with inventory analytics.
    Optional query params:
      category – filter by category name
      status   – 'low' | 'critical' | 'overstock' | 'normal' | 'slow_mover'
    """
    store = get_store()
    sbp = _get_sales_by_product(store.sales)
    inventory = compute_inventory_status(store.products, sbp)

    # Apply filters
    if category:
        inventory = [p for p in inventory if p["category"].lower() == category.lower()]
    if status == "low":
        inventory = [p for p in inventory if p["is_low_stock"]]
    elif status == "critical":
        inventory = [p for p in inventory if p["stock_status"] == "critical"]
    elif status == "overstock":
        inventory = [p for p in inventory if p["is_overstock"]]
    elif status == "slow_mover":
        inventory = [p for p in inventory if p["is_slow_mover"]]
    elif status == "normal":
        inventory = [p for p in inventory if p["stock_status"] == "normal"]

    # Add last 30d sales per product
    enriched = []
    from datetime import timedelta
    from backend.data.seed import TODAY
    cutoff = (TODAY - timedelta(days=30)).isoformat()
    for p in inventory:
        pid = p["id"]
        recent_sales = [r for r in sbp.get(pid, []) if r["date"] >= cutoff]
        p["units_sold_30d"] = sum(r["units_sold"] for r in recent_sales)
        p["revenue_30d"] = round(sum(r["revenue"] for r in recent_sales), 2)
        enriched.append(p)

    return JSONResponse({
        "total": len(enriched),
        "products": enriched,
        "categories": list({p["category"] for p in store.products}),
    })


# ─── API: Sales ───────────────────────────────────────────────────────────────

@app.get("/api/sales", tags=["Sales"])
async def get_sales(
    days: int = 90,
    product_id: str | None = None,
) -> JSONResponse:
    """
    Returns sales analytics.
    Optional params:
      days       – history window (7 | 30 | 90)
      product_id – filter to single product
    """
    if days not in (7, 30, 60, 90):
        raise HTTPException(status_code=400, detail="days must be 7, 30, 60, or 90")

    store = get_store()
    sales = store.sales

    if product_id:
        if product_id not in store.products_by_id:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        sales = store.sales_for(product_id)

    sbp = _get_sales_by_product(sales)
    series = daily_revenue_series(sales, days)
    s_period = period_summary(sales, days)
    mom = month_over_month(sales)
    anomalies = detect_anomalies(sbp)
    top10 = top_products_by_revenue(sales, store.products_by_id, days, 10)
    cat_totals = aggregate_by_category(sales, store.products_by_id)

    return JSONResponse({
        "period_days": days,
        "product_id": product_id,
        "summary": s_period,
        "mom_comparison": mom,
        "daily_series": series,
        "top_products": top10,
        "category_totals": [
            {"category": k, "units_sold": v["units_sold"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(cat_totals.items(), key=lambda x: -x[1]["revenue"])
        ],
        "anomalies": anomalies[:20],
    })


# ─── API: Alerts ──────────────────────────────────────────────────────────────

@app.get("/api/alerts", tags=["Alerts"])
async def get_alerts(severity: str | None = None) -> JSONResponse:
    """
    Returns prioritised alerts.
    Optional param:
      severity – 'critical' | 'warning' | 'info'
    """
    store = get_store()
    sbp = _get_sales_by_product(store.sales)
    inventory = compute_inventory_status(store.products, sbp)
    alerts = generate_all_alerts(inventory, sbp, store.products_by_id)

    if severity:
        allowed = {"critical", "warning", "info"}
        if severity not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"severity must be one of {allowed}",
            )
        alerts = [a for a in alerts if a["severity"] == severity]

    return JSONResponse({
        "total": len(alerts),
        "summary": alerts_summary(alerts),
        "alerts": alerts,
    })


# ─── API: Copilot ─────────────────────────────────────────────────────────────

class CopilotRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


@app.post("/api/copilot", tags=["Copilot"])
async def copilot(req: CopilotRequest) -> JSONResponse:
    """
    AI Copilot endpoint.
    Runs deterministic analytics first, then sends context + question to Gemini.
    Always returns raw data alongside the AI answer.
    """
    store = get_store()
    context = build_copilot_context(
        store.products,
        store.sales,
        store.products_by_id,
    )
    context["store_info"] = store.store_info

    result = await ask_copilot(req.question, context)
    return JSONResponse(result)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health() -> JSONResponse:
    store = get_store()
    return JSONResponse({
        "status": "ok",
        "products": len(store.products),
        "sales_records": len(store.sales),
        "store": store.store_info.get("name"),
    })


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    """Pre-warm the data store so first request is fast."""
    get_store()
    print("[RetailIQ] Data store ready. Server listening on http://0.0.0.0:8000")
