"""
store.py – In-memory singleton data store for RetailIQ.

All data is seeded once at startup and held in memory.
Analytics modules read from DataStore; no mutation after init.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from backend.data.seed import (
    generate_daily_sales,
    generate_products,
    generate_store_info,
)


@dataclass
class DataStore:
    """Singleton in-memory store seeded at startup."""
    products: list[dict[str, Any]] = field(default_factory=list)
    sales: list[dict[str, Any]] = field(default_factory=list)
    store_info: dict[str, Any] = field(default_factory=dict)

    # Derived indices (built after seed)
    products_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)

    def initialise(self) -> None:
        """Seed all data. Call once at application startup."""
        self.sales = generate_daily_sales()
        self.products = generate_products(self.sales)
        self.store_info = generate_store_info()
        self.products_by_id = {p["id"]: p for p in self.products}
        print(
            f"[DataStore] Seeded {len(self.products)} products, "
            f"{len(self.sales)} sales records."
        )

    # ── Convenience accessors ────────────────────────────────────────────────

    def sales_for(self, product_id: str) -> list[dict[str, Any]]:
        return [s for s in self.sales if s["product_id"] == product_id]

    def sales_between(self, start: str, end: str) -> list[dict[str, Any]]:
        return [s for s in self.sales if start <= s["date"] <= end]

    def product(self, product_id: str) -> dict[str, Any] | None:
        return self.products_by_id.get(product_id)


# Module-level singleton
_store: DataStore | None = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
        _store.initialise()
    return _store
