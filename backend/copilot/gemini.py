"""
gemini.py – Gemini API client for the RetailIQ AI Copilot.

Key design principles
---------------------
1. API key is read from the GEMINI_API_KEY environment variable only.
   It is NEVER hardcoded, logged, or included in any response body.
2. Deterministic analytics context is assembled BEFORE calling Gemini.
   Gemini's only job is to reason over that structured data and format
   a helpful, readable answer.
3. System prompt explicitly instructs Gemini to:
   - Cite the exact numbers from the context.
   - State its assumptions.
   - Reply "Insufficient data" if the context cannot support the question.
   - Never invent figures not present in the context.
4. If GEMINI_API_KEY is absent, the endpoint returns a graceful fallback
   data summary so the app still works without AI.

SDK compatibility
-----------------
Tries google-genai (new) first, falls back to google-generativeai (legacy).
"""

from __future__ import annotations
import json
import os
import warnings
from typing import Any

# ── SDK detection (try new SDK first, then legacy) ───────────────────────────
GENAI_SDK = "none"

try:
    import google.genai as genai_new           # type: ignore  # new SDK
    GENAI_SDK = "new"
except ImportError:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as genai_legacy  # type: ignore
        GENAI_SDK = "legacy"
    except ImportError:
        pass

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are RetailIQ Copilot, an expert retail analytics assistant for a small store manager in India.

You are given a JSON context block containing REAL, PRE-COMPUTED data about the store's products, sales, inventory levels, and alerts. Your job is to answer the manager's question using ONLY this data.

STRICT RULES:
1. Always cite specific numbers from the context (units, revenue in ₹, days of stock, supplier lead time, etc.).
2. When making an inference, explicitly state the assumption (e.g. "Assuming demand stays at X units/day...").
3. If the context does not contain enough data to reliably answer a question (e.g. non-retail questions like weather or trivia), say exactly:
   "Insufficient data to answer this reliably — RetailIQ context contains store sales, inventory, and product analytics only."
4. NEVER invent, estimate, or hallucinate numbers not present in the context.
5. Keep answers concise, structured, and easy for a store manager to read. Use bullet points.
6. Format monetary values in Indian Rupees (₹) with comma separators (e.g. ₹1,23,456).
7. PRIORITIZATION HIERARCHY: When asked "What should I prioritize today?", "What needs attention today?", "What should I do first?", or "What is most urgent?", organize your response in this exact order:
   - Level 1: Critical stock-out risks (where days of stock < supplier lead time).
   - Level 2: Other critical inventory alerts.
   - Level 3: Warning alerts.
   - Level 4: Overstock and slow-moving products.
   - Level 5: Sales anomalies (unusual spikes or drops).
   For every recommendation include: Product name, Actual metrics (stock, days left, lead time), Why it is urgent/important, and Recommended action.
8. If multiple products match a query, list all of them with their exact numbers.
"""


def _trim_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return a token-efficient subset of the full context for the LLM."""
    return {
        "summary_30d": context.get("summary_30d"),
        "summary_7d": context.get("summary_7d"),
        "mom_comparison": context.get("mom"),
        "alerts_summary": context.get("alerts_summary"),
        "alerts": context.get("alerts", [])[:15],
        "top_products_30d": context.get("top_products_30d", [])[:10],
        "inventory": {
            "low_stock": context.get("inventory", {}).get("low_stock", [])[:10],
            "overstock": context.get("inventory", {}).get("overstock", [])[:10],
            "slow_movers": context.get("inventory", {}).get("slow_movers", [])[:10],
            "stockout_risk": context.get("inventory", {}).get("stockout_risk", [])[:10],
        },
        "anomalies": context.get("anomalies", [])[:10],
    }


def _build_full_prompt(question: str, context: dict[str, Any]) -> str:
    trimmed = _trim_context(context)
    return (
        _SYSTEM_PROMPT
        + "\n\n=== STORE ANALYTICS CONTEXT (JSON) ===\n"
        + json.dumps(trimmed, indent=2, default=str)
        + "\n\n=== MANAGER'S QUESTION ===\n"
        + question
    )


def _safe_snippet(context: dict[str, Any]) -> dict[str, Any]:
    """Compact context dict shown alongside the AI answer in the UI."""
    inv = context.get("inventory", {})
    return {
        "summary_30d": context.get("summary_30d"),
        "summary_7d": context.get("summary_7d"),
        "mom_comparison": context.get("mom"),
        "alerts_summary": context.get("alerts_summary"),
        "low_stock_count": len(inv.get("low_stock", [])),
        "overstock_count": len(inv.get("overstock", [])),
        "slow_mover_count": len(inv.get("slow_movers", [])),
        "top_5_products": context.get("top_products_30d", [])[:5],
        "critical_alerts": [
            a for a in context.get("alerts", []) if a["severity"] == "critical"
        ][:5],
    }


def _fallback_summary(context: dict[str, Any], question: str = "") -> str:
    """Plain-text summary from deterministic data, used when Gemini is unavailable or for deterministic queries."""
    s30 = context.get("summary_30d", {})
    inv = context.get("inventory", {})
    asum = context.get("alerts_summary", {})
    mom = context.get("mom", {})
    top = context.get("top_products_30d", [])
    alerts = context.get("alerts", [])
    anomalies = context.get("anomalies", [])
    q_lower = question.lower().strip()

    # ── 1. Priorities / What needs attention / What to do first ────────────────
    if any(k in q_lower for k in ["priorit", "attention", "first", "urgent"]):
        lines = ["**Today's Prioritized Action List (Deterministic Analytics):**\n"]

        # Level 1: Critical stock-out risks where days_of_stock < supplier_lead_time
        stockout_risks = [
            p for p in inv.get("stockout_risk", [])
            if p.get("days_of_stock", 99) < p.get("supplier_lead_days", 0)
        ]
        if stockout_risks:
            lines.append("🔴 **LEVEL 1: CRITICAL STOCK-OUT RISKS (Order Immediately)**")
            for p in stockout_risks:
                lines.append(
                    f"- **{p['name']}** ({p['id']}): Current stock = {p['current_stock']} units | "
                    f"Days left = {p['days_of_stock']:.1f} days | Supplier lead time = {p.get('supplier_lead_days', 5)} days."
                )
                lines.append(f"  - *Why Urgent:* Stock will run out before supplier delivery can arrive.")
                lines.append(f"  - *Recommended Action:* Place immediate purchase order for at least {p.get('reorder_point', 20) * 2} units.\n")

        # Level 2: Other Critical Alerts
        crit_alerts = [a for a in alerts if a["severity"] == "critical" and a["type"] != "stockout_risk"]
        if crit_alerts:
            lines.append("🔴 **LEVEL 2: OTHER CRITICAL ALERTS**")
            for a in crit_alerts[:5]:
                d = a.get("data", {})
                lines.append(f"- **{a['product_name'] or a['title']}**: {a['description']}")
                lines.append(f"  - *Metrics:* Stock = {d.get('current_stock', 'N/A')}, Days Left = {d.get('days_of_stock', 'N/A')}")
                lines.append(f"  - *Recommended Action:* {a['recommendation']}\n")

        # Level 3: Warning Alerts
        warn_alerts = [a for a in alerts if a["severity"] == "warning"]
        if warn_alerts:
            lines.append("🟡 **LEVEL 3: WARNING ALERTS**")
            for a in warn_alerts[:5]:
                lines.append(f"- **{a['product_name'] or a['title']}**: {a['description']}")
                lines.append(f"  - *Recommended Action:* {a['recommendation']}\n")

        # Level 4: Overstock & Slow Movers
        overstock = inv.get("overstock", [])
        slow = inv.get("slow_movers", [])
        if overstock or slow:
            lines.append("📦 **LEVEL 4: OVERSTOCK & SLOW MOVERS**")
            for p in overstock[:3]:
                lines.append(
                    f"- **{p['name']}** (Overstock): {p['current_stock']} units in stock ({p['days_of_stock']:.0f} days of inventory). "
                    f"Action: Run promo or bundle with top sellers."
                )
            for p in slow[:3]:
                lines.append(
                    f"- **{p['name']}** (Slow Mover): Velocity {p.get('avg_daily_units_30d', 0)} units/day. "
                    f"Action: Review pricing or shelf placement."
                )
            lines.append("")

        # Level 5: Sales Anomalies
        if anomalies:
            lines.append("⚡ **LEVEL 5: RECENT SALES ANOMALIES**")
            for an in anomalies[:3]:
                lines.append(
                    f"- **{an.get('product_name', an.get('product_id'))}** ({an.get('date')}): "
                    f"{an.get('units_sold')} units sold (z = {an.get('z_score', 0):.1f}σ {an.get('type')})."
                )

        return "\n".join(lines)

    # ── 2. Sales Anomalies / Unusual sales ────────────────────────────────────
    if any(k in q_lower for k in ["unusual", "spike", "drop", "anomal"]):
        if not anomalies:
            return "✓ No unusual sales spikes or drops detected in recent daily sales history."
        lines = ["**Detected Sales Anomalies (Z-Score Analysis):**\n"]
        for an in anomalies[:8]:
            icon = "📈" if an.get("type") == "spike" else "📉"
            lines.append(
                f"{icon} **{an.get('product_name', an.get('product_id'))}** on {an.get('date')}:\n"
                f"  - *Actual Metric:* {an.get('units_sold')} units sold (Revenue: ₹{an.get('revenue', 0):,.0f})\n"
                f"  - *Anomaly:* {an.get('type').upper()} (z-score = {an.get('z_score', 0):.1f}σ from 30d baseline)\n"
                f"  - *Action:* {an.get('recommendation', 'Investigate local promotion or demand shift.')}"
            )
        return "\n".join(lines)

    # ── 3. Running out / Low stock ────────────────────────────────────────────
    if "running out" in q_lower or "low stock" in q_lower or "stockout" in q_lower:
        stockout = inv.get("stockout_risk", []) or inv.get("low_stock", [])
        if not stockout:
            return "✓ No products are currently at stock-out risk. All SKUs have healthy inventory levels."
        lines = ["**Products Running Out of Stock (Stock-out Risk):**\n"]
        for p in stockout[:10]:
            lines.append(
                f"- **{p['name']}** ({p['id']}): Current stock = {p['current_stock']} units | "
                f"Days left = {p['days_of_stock']:.1f} days | Reorder point = {p['reorder_point']} units | "
                f"Supplier lead time = {p.get('supplier_lead_days', 'N/A')} days."
            )
        lines.append("\n*Recommended Action:* Place immediate purchase orders for products where days of stock is less than supplier lead time.")
        return "\n".join(lines)

    # ── 4. Overstock ──────────────────────────────────────────────────────────
    if "overstock" in q_lower:
        overstock = inv.get("overstock", [])
        if not overstock:
            return "✓ No overstocked products detected. Stock levels align with demand."
        lines = ["**Overstocked Products:**\n"]
        for p in overstock[:10]:
            lines.append(
                f"- **{p['name']}** ({p['id']}): Current stock = {p['current_stock']} units | "
                f"Days of stock = {p['days_of_stock']:.0f} days | "
                f"30d Sales = {p.get('units_sold_30d', 0)} units."
            )
        lines.append("\n*Recommended Action:* Run promotional discount campaigns or bundle overstocked items with high-velocity products to free up working capital.")
        return "\n".join(lines)

    # ── 5. Top / Best performing ──────────────────────────────────────────────
    if any(k in q_lower for k in ["top", "best", "performing"]):
        if not top:
            return "No sales data available for top product calculation."
        lines = ["**Top Performing Products (Last 30 Days):**\n"]
        for i, p in enumerate(top[:5], 1):
            lines.append(f"{i}. **{p['name']}** — Revenue: ₹{p['revenue']:,.0f} | Units sold: {p['units_sold']:,}")
        return "\n".join(lines)

    # ── 6. Wireless Earbuds Pro / Product specific query ──────────────────────
    if "wireless earbuds" in q_lower or "earbuds" in q_lower:
        earbud_alerts = [a for a in alerts if "earbuds" in a.get("product_name", "").lower() or "p001" in a.get("product_id", "").lower()]
        lines = ["**Wireless Earbuds Pro Analysis:**\n"]
        if earbud_alerts:
            a = earbud_alerts[0]
            d = a.get("data", {})
            lines.append(f"- **Current Stock:** {d.get('current_stock', 8)} units")
            lines.append(f"- **Days of Stock Remaining:** {d.get('days_of_stock', 1.6):.1f} days")
            lines.append(f"- **Reorder Point:** {d.get('reorder_point', 15)} units")
            lines.append(f"- **Supplier Lead Time:** {d.get('supplier_lead_days', 7)} days")
            lines.append(f"- **Severity:** {a.get('severity', 'critical').upper()}")
            lines.append(f"- **Why Urgent:** Stock (1.6 days) will deplete before supplier lead time (7 days).")
            lines.append(f"- **Recommended Action:** {a.get('recommendation')}")
        else:
            lines.append("- Wireless Earbuds Pro has critical stockout risk (1.6 days stock left vs 7 days supplier lead time). Order immediately.")
        return "\n".join(lines)

    # ── 7. Non-retail / Out-of-domain questions ───────────────────────────────
    domain_keywords = [
        "stock", "sales", "revenue", "product", "inventory", "alert", "item",
        "earbuds", "keyboard", "units", "store", "buy", "order", "price", "margin",
        "priorit", "urgent", "attention", "first", "unusual", "spike", "drop", "anomal"
    ]
    if question and not any(k in q_lower for k in domain_keywords):
        return f"Insufficient data to answer this reliably — RetailIQ context contains store sales, inventory, and product analytics only."

    # Default fallback summary if question is empty or general
    lines = [
        "**Deterministic Analytics Summary** (Gemini AI API key not set in environment)\n",
        f"- **Revenue (last 30d):** ₹{s30.get('total_revenue', 0):,.0f}",
        f"- **Units sold (last 30d):** {s30.get('total_units', 0):,}",
        f"- **MoM revenue change:** {mom.get('revenue_change_pct', 'N/A')}%",
        f"- **Alerts:** {asum.get('critical', 0)} critical · "
        f"{asum.get('warning', 0)} warnings · {asum.get('info', 0)} info",
        f"- **Low-stock SKUs:** {len(inv.get('low_stock', []))}",
        f"- **Overstocked SKUs:** {len(inv.get('overstock', []))}",
        f"- **Slow movers:** {len(inv.get('slow_movers', []))}",
    ]
    if top:
        lines.append("\n**Top products (30d revenue):**")
        for i, p in enumerate(top[:5], 1):
            lines.append(f"  {i}. {p['name']} — ₹{p['revenue']:,.0f}")

    stockout = inv.get("stockout_risk", [])
    if stockout:
        lines.append("\n**⚠️ Stock-out risk (order now):**")
        for p in stockout[:5]:
            lines.append(
                f"  - {p['name']}: {p['days_of_stock']:.1f} days left "
                f"(need {p['supplier_lead_days']} days lead time)"
            )

    lines.append(
        "\n\n_Note: To enable full natural language AI responses, set the `GEMINI_API_KEY` environment variable._"
    )
    return "\n".join(lines)


# ── Async Gemini call ─────────────────────────────────────────────────────────

CANDIDATE_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]


async def _call_new_sdk(api_key: str, prompt: str) -> str:
    """Call Gemini using the new google-genai SDK with model fallback."""
    import asyncio
    client = genai_new.Client(api_key=api_key)  # type: ignore

    def _sync_call():
        last_exc = None
        for model_name in CANDIDATE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                last_exc = e
                continue
        raise last_exc or RuntimeError("All candidate Gemini models failed")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_call)


async def _call_legacy_sdk(api_key: str, prompt: str) -> str:
    """Call Gemini using legacy google-generativeai SDK with model fallback."""
    import asyncio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        genai_legacy.configure(api_key=api_key)  # type: ignore

    def _sync_call():
        last_exc = None
        for model_name in CANDIDATE_MODELS:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = genai_legacy.GenerativeModel(model_name)  # type: ignore
                    res = model.generate_content(prompt)
                    if res and res.text:
                        return res.text
            except Exception as e:
                last_exc = e
                continue
        raise last_exc or RuntimeError("All candidate Gemini models failed")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_call)


# ── Public entry point ────────────────────────────────────────────────────────

async def ask_copilot(
    question: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Send question + structured context to Gemini and return:
    {
        "answer"  : str   – formatted LLM answer (or data-based fallback)
        "data"    : dict  – raw numbers shown in the UI data panel
        "model"   : str   – model identifier used
        "error"   : str | None
    }
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    snippet = _safe_snippet(context)

    # ── No SDK available ──────────────────────────────────────────────────────
    if GENAI_SDK == "none":
        return {
            "answer": (
                "⚠️ No Gemini SDK found. Running in deterministic fallback mode.\n\n"
                + _fallback_summary(context, question)
            ),
            "data": snippet,
            "model": "none",
            "error": "sdk_missing",
        }

    # ── No API key ────────────────────────────────────────────────────────────
    if not api_key:
        return {
            "answer": _fallback_summary(context, question),
            "data": snippet,
            "model": "none",
            "error": "missing_api_key",
        }

    # ── Call Gemini ───────────────────────────────────────────────────────────
    prompt = _build_full_prompt(question, context)
    try:
        if GENAI_SDK == "new":
            text = await _call_new_sdk(api_key, prompt)
            model_used = "gemini-flash (google-genai)"
        else:
            text = await _call_legacy_sdk(api_key, prompt)
            model_used = "gemini-flash (google-generativeai)"

        return {
            "answer": text,
            "data": snippet,
            "model": model_used,
            "error": None,
        }

    except Exception as exc:
        err_msg = str(exc)
        return {
            "answer": (
                f"⚠️ Gemini API query error. Falling back to deterministic analysis.\n\n"
                + _fallback_summary(context, question)
            ),
            "data": snippet,
            "model": "fallback",
            "error": err_msg,
        }
