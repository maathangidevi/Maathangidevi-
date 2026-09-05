"""
seed.py – Generates realistic, deterministic sample data for RetailIQ.

Design decisions
----------------
* Random seed is fixed (42) so results are reproducible across restarts.
* 30 SKUs across 6 categories with realistic price ranges and lead times.
* 90 days of daily sales with:
    - Base demand per SKU
    - Weekly seasonality (weekends ~30% higher for FMCG/clothing)
    - Gaussian noise
    - 2–4 deliberate spike/drop events per SKU
* Inventory set to create intentional low-stock, overstock, and normal states.
"""

import math
import random
from datetime import date, timedelta
from typing import Any

# ─── Reproducible RNG ────────────────────────────────────────────────────────
RNG = random.Random(42)
TODAY = date(2026, 9, 5)         # fixed reference date matching deployment context
HISTORY_DAYS = 90

# ─── Product catalogue ────────────────────────────────────────────────────────
PRODUCTS_RAW: list[dict[str, Any]] = [
    # Electronics
    {"id": "P001", "name": "Wireless Earbuds Pro",     "category": "Electronics",  "unit_price": 2499.00, "cost_price": 1400.00, "reorder_point": 15, "supplier_lead_days": 7,  "base_daily_demand": 4.0},
    {"id": "P002", "name": "USB-C Fast Charger 65W",   "category": "Electronics",  "unit_price":  699.00, "cost_price":  320.00, "reorder_point": 20, "supplier_lead_days": 5,  "base_daily_demand": 7.0},
    {"id": "P003", "name": "Mechanical Keyboard",      "category": "Electronics",  "unit_price": 3299.00, "cost_price": 1900.00, "reorder_point": 10, "supplier_lead_days": 10, "base_daily_demand": 2.0},
    {"id": "P004", "name": "Smart LED Desk Lamp",      "category": "Electronics",  "unit_price": 1199.00, "cost_price":  600.00, "reorder_point": 12, "supplier_lead_days": 7,  "base_daily_demand": 3.0},
    {"id": "P005", "name": "Portable Power Bank 20K",  "category": "Electronics",  "unit_price": 1599.00, "cost_price":  850.00, "reorder_point": 18, "supplier_lead_days": 6,  "base_daily_demand": 5.5},

    # Clothing
    {"id": "P006", "name": "Men's Classic Polo Tee",   "category": "Clothing",     "unit_price":  599.00, "cost_price":  220.00, "reorder_point": 25, "supplier_lead_days": 14, "base_daily_demand": 8.0},
    {"id": "P007", "name": "Women's Kurta Set",         "category": "Clothing",     "unit_price":  899.00, "cost_price":  350.00, "reorder_point": 20, "supplier_lead_days": 14, "base_daily_demand": 6.0},
    {"id": "P008", "name": "Denim Jeans – Slim Fit",   "category": "Clothing",     "unit_price": 1299.00, "cost_price":  600.00, "reorder_point": 15, "supplier_lead_days": 12, "base_daily_demand": 4.5},
    {"id": "P009", "name": "Sports Ankle Socks (6pk)", "category": "Clothing",     "unit_price":  249.00, "cost_price":   90.00, "reorder_point": 30, "supplier_lead_days": 7,  "base_daily_demand": 12.0},
    {"id": "P010", "name": "Winter Hoodie",            "category": "Clothing",     "unit_price": 1499.00, "cost_price":  700.00, "reorder_point": 20, "supplier_lead_days": 14, "base_daily_demand": 3.0},

    # FMCG / Grocery
    {"id": "P011", "name": "Organic Oats 1kg",         "category": "FMCG",         "unit_price":  179.00, "cost_price":   90.00, "reorder_point": 40, "supplier_lead_days": 3,  "base_daily_demand": 18.0},
    {"id": "P012", "name": "Cold Pressed Olive Oil 1L","category": "FMCG",         "unit_price":  549.00, "cost_price":  280.00, "reorder_point": 20, "supplier_lead_days": 5,  "base_daily_demand": 7.0},
    {"id": "P013", "name": "Mixed Nuts & Dry Fruits",  "category": "FMCG",         "unit_price":  399.00, "cost_price":  200.00, "reorder_point": 25, "supplier_lead_days": 4,  "base_daily_demand": 10.0},
    {"id": "P014", "name": "Instant Coffee 200g",      "category": "FMCG",         "unit_price":  329.00, "cost_price":  150.00, "reorder_point": 30, "supplier_lead_days": 3,  "base_daily_demand": 14.0},
    {"id": "P015", "name": "Protein Bar Variety Pack", "category": "FMCG",         "unit_price":  499.00, "cost_price":  230.00, "reorder_point": 35, "supplier_lead_days": 5,  "base_daily_demand": 16.0},

    # Personal Care
    {"id": "P016", "name": "Vitamin C Serum 30ml",     "category": "Personal Care","unit_price":  899.00, "cost_price":  380.00, "reorder_point": 15, "supplier_lead_days": 7,  "base_daily_demand": 5.0},
    {"id": "P017", "name": "SPF 50+ Sunscreen 100ml",  "category": "Personal Care","unit_price":  399.00, "cost_price":  160.00, "reorder_point": 20, "supplier_lead_days": 5,  "base_daily_demand": 9.0},
    {"id": "P018", "name": "Bamboo Toothbrush Set",    "category": "Personal Care","unit_price":  199.00, "cost_price":   75.00, "reorder_point": 25, "supplier_lead_days": 5,  "base_daily_demand": 11.0},
    {"id": "P019", "name": "Herbal Hair Oil 200ml",    "category": "Personal Care","unit_price":  249.00, "cost_price":   95.00, "reorder_point": 20, "supplier_lead_days": 6,  "base_daily_demand": 8.0},
    {"id": "P020", "name": "Activated Charcoal Soap",  "category": "Personal Care","unit_price":  149.00, "cost_price":   55.00, "reorder_point": 30, "supplier_lead_days": 4,  "base_daily_demand": 13.0},

    # Stationery & Office
    {"id": "P021", "name": "Premium Ballpoint Pens 10pk","category": "Stationery", "unit_price":  149.00, "cost_price":   55.00, "reorder_point": 30, "supplier_lead_days": 5,  "base_daily_demand": 10.0},
    {"id": "P022", "name": "A4 Spiral Notebook",       "category": "Stationery",   "unit_price":   99.00, "cost_price":   38.00, "reorder_point": 40, "supplier_lead_days": 4,  "base_daily_demand": 14.0},
    {"id": "P023", "name": "Sticky Notes Assorted",    "category": "Stationery",   "unit_price":   79.00, "cost_price":   28.00, "reorder_point": 30, "supplier_lead_days": 4,  "base_daily_demand": 9.0},
    {"id": "P024", "name": "Desk Organiser Set",       "category": "Stationery",   "unit_price":  699.00, "cost_price":  280.00, "reorder_point": 10, "supplier_lead_days": 8,  "base_daily_demand": 2.5},
    {"id": "P025", "name": "Whiteboard Markers 6pk",   "category": "Stationery",   "unit_price":  199.00, "cost_price":   70.00, "reorder_point": 25, "supplier_lead_days": 4,  "base_daily_demand": 6.0},

    # Home & Kitchen
    {"id": "P026", "name": "Stainless Steel Water Bottle","category": "Home",      "unit_price":  599.00, "cost_price":  240.00, "reorder_point": 15, "supplier_lead_days": 7,  "base_daily_demand": 5.0},
    {"id": "P027", "name": "Beeswax Food Wraps 3pk",   "category": "Home",         "unit_price":  349.00, "cost_price":  140.00, "reorder_point": 20, "supplier_lead_days": 6,  "base_daily_demand": 6.5},
    {"id": "P028", "name": "Silicone Kitchen Spatula Set","category": "Home",      "unit_price":  449.00, "cost_price":  170.00, "reorder_point": 15, "supplier_lead_days": 7,  "base_daily_demand": 4.0},
    {"id": "P029", "name": "Airtight Glass Containers 3pc","category": "Home",     "unit_price":  799.00, "cost_price":  330.00, "reorder_point": 12, "supplier_lead_days": 8,  "base_daily_demand": 3.0},
    {"id": "P030", "name": "Bamboo Cutting Board",     "category": "Home",         "unit_price":  499.00, "cost_price":  200.00, "reorder_point": 10, "supplier_lead_days": 7,  "base_daily_demand": 2.5},
]

# Weekend uplift per category (multiplier on base demand)
WEEKEND_UPLIFT = {
    "Electronics":   1.20,
    "Clothing":      1.35,
    "FMCG":          1.25,
    "Personal Care": 1.20,
    "Stationery":    0.75,
    "Home":          1.30,
}

# ─── Spike / drop injection per product ──────────────────────────────────────
# Format: (product_id, day_offset_from_today, multiplier)
# Positive multiplier > 1 → spike; 0 < multiplier < 1 → drop
EVENTS: list[tuple[str, int, float]] = [
    ("P001", -5,  4.0),   # viral review → spike
    ("P001", -4,  3.5),
    ("P006", -10, 3.8),   # fashion sale
    ("P006", -9,  3.2),
    ("P011", -3,  2.8),   # weekend FMCG rush
    ("P015", -7,  3.5),   # fitness challenge trend
    ("P015", -6,  3.0),
    ("P003", -20, 0.2),   # supply shortage drop
    ("P003", -19, 0.15),
    ("P022", -15, 2.5),   # back-to-school
    ("P022", -14, 2.2),
    ("P017", -60, 3.0),   # summer sunscreen rush
    ("P017", -59, 2.8),
    ("P014", -2,  0.3),   # competitor restocked (drop)
    ("P028", -25, 2.2),   # kitchen pop-up event
    ("P009", -8,  3.0),   # sports event nearby
]


def _build_event_map() -> dict[tuple[str, date], float]:
    m: dict[tuple[str, date], float] = {}
    for pid, offset, mult in EVENTS:
        d = TODAY + timedelta(days=offset)
        if d >= TODAY - timedelta(days=HISTORY_DAYS):
            m[(pid, d)] = mult
    return m


def generate_daily_sales() -> list[dict[str, Any]]:
    """
    Returns list of dicts:
      {product_id, date, units_sold, revenue}
    covering the last HISTORY_DAYS days.
    """
    event_map = _build_event_map()
    records: list[dict[str, Any]] = []

    for p in PRODUCTS_RAW:
        pid = p["id"]
        base = p["base_daily_demand"]
        price = p["unit_price"]
        cat = p["category"]
        uplift = WEEKEND_UPLIFT[cat]

        for d_offset in range(-HISTORY_DAYS, 0):
            sale_date = TODAY + timedelta(days=d_offset)
            dow = sale_date.weekday()  # 0=Mon … 6=Sun

            # Weekend multiplier
            wk_mult = uplift if dow >= 5 else 1.0

            # Gaussian noise: std ≈ 25% of base
            noise_mult = max(0.05, RNG.gauss(1.0, 0.25))

            # Spike / drop event
            event_mult = event_map.get((pid, sale_date), 1.0)

            raw = base * wk_mult * noise_mult * event_mult
            units = max(0, round(raw))
            revenue = round(units * price, 2)

            records.append({
                "product_id": pid,
                "date": sale_date.isoformat(),
                "units_sold": units,
                "revenue": revenue,
            })

    return records


def _compute_avg_daily_demand(sales: list[dict]) -> dict[str, float]:
    """Compute average daily units sold per product over all history."""
    totals: dict[str, list[int]] = {}
    for r in sales:
        totals.setdefault(r["product_id"], []).append(r["units_sold"])
    return {pid: (sum(v) / len(v)) for pid, v in totals.items()}


def _set_stock_scenarios(
    products: list[dict],
    avg_demand: dict[str, float],
) -> list[dict]:
    """
    Assign current_stock to create realistic scenarios:
      P001, P002 → near stock-out (< reorder_point)
      P010, P024 → overstock (> 3× 30-day demand)
      P003       → critically low (< 3 days of stock)
      rest       → normal (1–3 weeks of demand)
    """
    forced: dict[str, int] = {
        "P001": 8,    # low – earbuds viral demand
        "P002": 12,   # low – chargers
        "P003": 4,    # critical – mechanical keyboards
        "P009": 18,   # low – socks
        "P010": 420,  # overstock – winter hoodie (wrong season)
        "P024": 185,  # overstock – desk organiser
        "P030": 145,  # overstock – cutting board
        "P014": 7,    # low – coffee ran low
        "P019": 11,   # low – herbal oil
    }

    for p in products:
        pid = p["id"]
        if pid in forced:
            p["current_stock"] = forced[pid]
        else:
            # Normal: 10–21 days of average demand
            days = RNG.randint(10, 21)
            avg = avg_demand.get(pid, p["base_daily_demand"])
            p["current_stock"] = max(5, round(avg * days))

    return products


def generate_products(sales: list[dict]) -> list[dict]:
    """Return product catalogue with current_stock and derived fields."""
    avg_demand = _compute_avg_daily_demand(sales)
    products = [dict(p) for p in PRODUCTS_RAW]
    products = _set_stock_scenarios(products, avg_demand)

    for p in products:
        pid = p["id"]
        p["avg_daily_demand"] = round(avg_demand.get(pid, p["base_daily_demand"]), 2)
    return products


def generate_store_info() -> dict[str, Any]:
    return {
        "name": "NexusTiq24 Flagship Store",
        "location": "Bengaluru, Karnataka",
        "manager": "Arjun Sharma",
        "store_id": "STR-001",
        "opening_date": "2023-03-15",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
    }
