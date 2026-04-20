from __future__ import annotations

from dataclasses import dataclass

from app.api.db import connect, require_dsn
from app.api.schemas import InventoryResult, ProductMatch


@dataclass(slots=True)
class InventoryLookupOutcome:
    answer: str
    product: ProductMatch | None
    inventory_results: list[InventoryResult]


@dataclass(slots=True)
class InventoryService:
    dsn: str

    @classmethod
    def from_env(cls) -> "InventoryService":
        return cls(dsn=require_dsn())

    def _resolve_product(self, product_query: str) -> ProductMatch | None:
        sql = """
        select
            id::text as product_id,
            sku,
            product_name,
            category,
            brand,
            status
        from public.products
        where is_active = true
          and (
            product_name ilike %(contains_query)s
            or sku ilike %(contains_query)s
          )
        order by
            case
                when lower(product_name) = lower(%(raw_query)s) then 0
                when lower(sku) = lower(%(raw_query)s) then 1
                else 2
            end,
            length(product_name),
            product_name
        limit 1
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "raw_query": product_query.strip(),
                        "contains_query": f"%{product_query.strip()}%",
                    },
                )
                row = cur.fetchone()

        if not row:
            return None

        return ProductMatch(**row)

    def _load_inventory(self, product_id: str) -> list[InventoryResult]:
        sql = """
        select
            l.location_code,
            l.location_name,
            l.region,
            i.quantity_available,
            i.inventory_status
        from public.inventory i
        join public.locations l
          on l.id = i.location_id
        where i.product_id::text = %(product_id)s
        order by i.quantity_available desc, l.location_name asc
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"product_id": product_id})
                rows = cur.fetchall()

        return [InventoryResult(**row) for row in rows]

    def lookup_inventory(self, product_query: str) -> InventoryLookupOutcome:
        product = self._resolve_product(product_query)
        if not product:
            return InventoryLookupOutcome(
                answer=(
                    f"I couldn't find a product matching '{product_query}' in the structured catalog data."
                ),
                product=None,
                inventory_results=[],
            )

        inventory_results = self._load_inventory(product.product_id)
        if not inventory_results:
            return InventoryLookupOutcome(
                answer=(
                    f"I found {product.product_name}, but there are no inventory rows available for it yet."
                ),
                product=product,
                inventory_results=[],
            )

        available_locations = [
            result for result in inventory_results if result.quantity_available > 0
        ]
        if available_locations:
            answer = (
                f"{product.product_name} is currently available in "
                f"{len(available_locations)} location(s)."
            )
        else:
            answer = f"{product.product_name} is currently out of stock across all tracked locations."

        return InventoryLookupOutcome(
            answer=answer,
            product=product,
            inventory_results=inventory_results,
        )
