from __future__ import annotations

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.api.db import connect, require_dsn


def stable_uuid(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"gcop:{kind}:{key}"))


USERS = [
    {
        "email": "support.analyst@demo.local",
        "full_name": "Morgan Support",
        "role": "support_analyst",
        "is_active": True,
    },
    {
        "email": "eng.support@demo.local",
        "full_name": "Alex Kim",
        "role": "engineering_support",
        "is_active": True,
    },
    {
        "email": "ops.manager@demo.local",
        "full_name": "Dana Lee",
        "role": "ops_manager",
        "is_active": True,
    },
    {
        "email": "admin@demo.local",
        "full_name": "Jordan Admin",
        "role": "admin",
        "is_active": True,
    },
]


PRODUCTS = [
    {
        "sku": "PX-100",
        "product_name": "Phantom X Shoes",
        "category": "Footwear",
        "brand": "Phantom",
        "status": "active",
        "price": Decimal("129.99"),
        "is_active": True,
    },
    {
        "sku": "SR-210",
        "product_name": "Summit Trail Runner",
        "category": "Footwear",
        "brand": "Summit",
        "status": "active",
        "price": Decimal("149.00"),
        "is_active": True,
    },
    {
        "sku": "AV-550",
        "product_name": "AeroFlex Jacket",
        "category": "Apparel",
        "brand": "Aero",
        "status": "active",
        "price": Decimal("119.00"),
        "is_active": True,
    },
    {
        "sku": "OR-440",
        "product_name": "Orbit Commuter Backpack",
        "category": "Accessories",
        "brand": "Orbit",
        "status": "active",
        "price": Decimal("79.50"),
        "is_active": True,
    },
    {
        "sku": "NV-330",
        "product_name": "Nova Jogger",
        "category": "Apparel",
        "brand": "Nova",
        "status": "active",
        "price": Decimal("89.00"),
        "is_active": True,
    },
]

LOCATIONS = [
    {
        "location_code": "CHI-FC",
        "location_name": "Chicago Fulfillment Center",
        "location_type": "fulfillment_center",
        "region": "Midwest",
        "is_active": True,
    },
    {
        "location_code": "DAL-DC",
        "location_name": "Dallas Distribution Center",
        "location_type": "distribution_center",
        "region": "South",
        "is_active": True,
    },
    {
        "location_code": "REN-FC",
        "location_name": "Reno Fulfillment Center",
        "location_type": "fulfillment_center",
        "region": "West",
        "is_active": True,
    },
    {
        "location_code": "ATL-DC",
        "location_name": "Atlanta Distribution Center",
        "location_type": "distribution_center",
        "region": "Southeast",
        "is_active": True,
    },
    {
        "location_code": "NWK-FC",
        "location_name": "Newark Fulfillment Center",
        "location_type": "fulfillment_center",
        "region": "Northeast",
        "is_active": True,
    },
]

INVENTORY = [
    {"sku": "PX-100", "location_code": "CHI-FC", "on_hand": 30, "available": 24, "reserved": 6, "inventory_status": "in_stock"},
    {"sku": "PX-100", "location_code": "DAL-DC", "on_hand": 18, "available": 12, "reserved": 6, "inventory_status": "in_stock"},
    {"sku": "PX-100", "location_code": "REN-FC", "on_hand": 6, "available": 3, "reserved": 3, "inventory_status": "low_stock"},
    {"sku": "PX-100", "location_code": "NWK-FC", "on_hand": 0, "available": 0, "reserved": 0, "inventory_status": "out_of_stock"},
    {"sku": "SR-210", "location_code": "CHI-FC", "on_hand": 9, "available": 5, "reserved": 4, "inventory_status": "low_stock"},
    {"sku": "SR-210", "location_code": "ATL-DC", "on_hand": 16, "available": 11, "reserved": 5, "inventory_status": "in_stock"},
    {"sku": "AV-550", "location_code": "DAL-DC", "on_hand": 22, "available": 18, "reserved": 4, "inventory_status": "in_stock"},
    {"sku": "AV-550", "location_code": "NWK-FC", "on_hand": 8, "available": 6, "reserved": 2, "inventory_status": "in_stock"},
    {"sku": "OR-440", "location_code": "REN-FC", "on_hand": 14, "available": 10, "reserved": 4, "inventory_status": "in_stock"},
    {"sku": "OR-440", "location_code": "ATL-DC", "on_hand": 5, "available": 1, "reserved": 4, "inventory_status": "low_stock"},
    {"sku": "NV-330", "location_code": "CHI-FC", "on_hand": 0, "available": 0, "reserved": 0, "inventory_status": "out_of_stock"},
    {"sku": "NV-330", "location_code": "DAL-DC", "on_hand": 4, "available": 0, "reserved": 4, "inventory_status": "out_of_stock"},
]

INCIDENTS = [
    {
        "incident_code": "INC-1042",
        "title": "Mobile Checkout Failure",
        "status": "resolved",
        "severity": "sev2",
        "service_area": "checkout",
        "summary": "A mobile-only checkout issue caused intermittent failures after the payment step until the checkout configuration was rolled back.",
        "customer_impact": "Customers experienced intermittent checkout failures and elevated abandonment on mobile web.",
        "start_time": "2026-04-12T13:00:00Z",
        "resolved_time": "2026-04-12T13:42:00Z",
    },
    {
        "incident_code": "INC-1077",
        "title": "Inventory Feed Sync Delay",
        "status": "investigating",
        "severity": "sev3",
        "service_area": "inventory",
        "summary": "Structured inventory updates are arriving late for a subset of footwear SKUs.",
        "customer_impact": "Availability indicators may lag current stock by several minutes for affected products.",
        "start_time": "2026-04-18T09:10:00Z",
        "resolved_time": None,
    },
    {
        "incident_code": "INC-1091",
        "title": "Payment Authorization Timeout",
        "status": "mitigated",
        "severity": "sev1",
        "service_area": "payments",
        "summary": "Payment authorization calls timed out for a large share of checkout attempts before a provider failover restored stability.",
        "customer_impact": "Customers saw checkout failures and duplicate retry attempts during the incident window.",
        "start_time": "2026-04-19T16:05:00Z",
        "resolved_time": None,
    },
]

INCIDENT_EVENTS = [
    ("INC-1042", "2026-04-12T13:05:00Z", "investigation_started", "Alex Kim", "Checkout failures reproduced on mobile web."),
    ("INC-1042", "2026-04-12T13:11:00Z", "impact_assessed", "Alex Kim", "Elevated abandonment and support contacts confirmed for mobile checkout."),
    ("INC-1042", "2026-04-12T13:18:00Z", "mitigation_started", "Priya Shah", "Rolled back the mobile checkout configuration flag tied to the payment step."),
    ("INC-1042", "2026-04-12T13:24:00Z", "monitoring", "Priya Shah", "Error rate dropped after rollback but remained intermittent for several minutes."),
    ("INC-1042", "2026-04-12T13:31:00Z", "support_guidance_updated", "Taylor Chen", "Support guidance updated with a desktop fallback only for affected customers."),
    ("INC-1042", "2026-04-12T13:42:00Z", "resolved", "Alex Kim", "Mobile checkout error rates returned to baseline and the incident was resolved."),
    ("INC-1077", "2026-04-18T09:15:00Z", "investigation_started", "Morgan Lee", "Inventory sync lag confirmed for newly updated footwear SKUs."),
    ("INC-1077", "2026-04-18T09:29:00Z", "scope_identified", "Morgan Lee", "Lag is isolated to the downstream sync job feeding structured availability records."),
    ("INC-1077", "2026-04-18T09:44:00Z", "workaround_defined", "Jordan Patel", "Commerce Ops asked support to avoid exact restock commitments until sync latency normalizes."),
    ("INC-1091", "2026-04-19T16:09:00Z", "investigation_started", "Sam Rivera", "Payment provider timeouts reproduced in checkout logs and alerting."),
    ("INC-1091", "2026-04-19T16:17:00Z", "mitigation_started", "Sam Rivera", "Traffic shifted to the backup authorization route for high-failure card types."),
    ("INC-1091", "2026-04-19T16:31:00Z", "customer_impact_updated", "Casey Nguyen", "Support guidance refreshed with retry limits and payment-workaround messaging."),
]


def upsert_users(conn) -> None:
    sql = """
    insert into public.users (
        id,
        email,
        full_name,
        role,
        is_active
    ) values (
        %(id)s,
        %(email)s,
        %(full_name)s,
        %(role)s,
        %(is_active)s
    )
    on conflict (email) do update set
        full_name = excluded.full_name,
        role = excluded.role,
        is_active = excluded.is_active
    """
    with conn.cursor() as cur:
        for row in USERS:
            cur.execute(sql, {"id": stable_uuid("user", row["email"]), **row})


def upsert_products(conn) -> None:
    sql = """
    insert into public.products (
        id,
        sku,
        product_name,
        category,
        brand,
        status,
        price,
        is_active
    ) values (
        %(id)s,
        %(sku)s,
        %(product_name)s,
        %(category)s,
        %(brand)s,
        %(status)s,
        %(price)s,
        %(is_active)s
    )
    on conflict (sku) do update set
        product_name = excluded.product_name,
        category = excluded.category,
        brand = excluded.brand,
        status = excluded.status,
        price = excluded.price,
        is_active = excluded.is_active,
        updated_at = now()
    """
    with conn.cursor() as cur:
        for row in PRODUCTS:
            cur.execute(sql, {"id": stable_uuid("product", row["sku"]), **row})


def upsert_locations(conn) -> None:
    sql = """
    insert into public.locations (
        id,
        location_code,
        location_name,
        location_type,
        region,
        is_active
    ) values (
        %(id)s,
        %(location_code)s,
        %(location_name)s,
        %(location_type)s,
        %(region)s,
        %(is_active)s
    )
    on conflict (location_code) do update set
        location_name = excluded.location_name,
        location_type = excluded.location_type,
        region = excluded.region,
        is_active = excluded.is_active
    """
    with conn.cursor() as cur:
        for row in LOCATIONS:
            cur.execute(sql, {"id": stable_uuid("location", row["location_code"]), **row})


def upsert_inventory(conn) -> None:
    sql = """
    insert into public.inventory (
        id,
        product_id,
        location_id,
        quantity_on_hand,
        quantity_available,
        quantity_reserved,
        inventory_status
    ) values (
        %(id)s,
        %(product_id)s,
        %(location_id)s,
        %(quantity_on_hand)s,
        %(quantity_available)s,
        %(quantity_reserved)s,
        %(inventory_status)s
    )
    on conflict (product_id, location_id) do update set
        quantity_on_hand = excluded.quantity_on_hand,
        quantity_available = excluded.quantity_available,
        quantity_reserved = excluded.quantity_reserved,
        inventory_status = excluded.inventory_status,
        updated_at = now()
    """
    with conn.cursor() as cur:
        for row in INVENTORY:
            cur.execute(
                sql,
                {
                    "id": stable_uuid("inventory", f"{row['sku']}:{row['location_code']}"),
                    "product_id": stable_uuid("product", row["sku"]),
                    "location_id": stable_uuid("location", row["location_code"]),
                    "quantity_on_hand": row["on_hand"],
                    "quantity_available": row["available"],
                    "quantity_reserved": row["reserved"],
                    "inventory_status": row["inventory_status"],
                },
            )


def upsert_incidents(conn) -> None:
    sql = """
    insert into public.incidents (
        id,
        incident_code,
        title,
        status,
        severity,
        service_area,
        summary,
        customer_impact,
        start_time,
        resolved_time
    ) values (
        %(id)s,
        %(incident_code)s,
        %(title)s,
        %(status)s,
        %(severity)s,
        %(service_area)s,
        %(summary)s,
        %(customer_impact)s,
        %(start_time)s,
        %(resolved_time)s
    )
    on conflict (incident_code) do update set
        title = excluded.title,
        status = excluded.status,
        severity = excluded.severity,
        service_area = excluded.service_area,
        summary = excluded.summary,
        customer_impact = excluded.customer_impact,
        start_time = excluded.start_time,
        resolved_time = excluded.resolved_time,
        updated_at = now()
    """
    with conn.cursor() as cur:
        for row in INCIDENTS:
            cur.execute(sql, {"id": stable_uuid("incident", row["incident_code"]), **row})


def upsert_incident_events(conn) -> None:
    sql = """
    insert into public.incident_events (
        id,
        incident_id,
        event_time,
        event_type,
        actor,
        event_summary
    ) values (
        %(id)s,
        %(incident_id)s,
        %(event_time)s,
        %(event_type)s,
        %(actor)s,
        %(event_summary)s
    )
    on conflict (id) do update set
        event_time = excluded.event_time,
        event_type = excluded.event_type,
        actor = excluded.actor,
        event_summary = excluded.event_summary
    """
    with conn.cursor() as cur:
        for incident_code, event_time, event_type, actor, event_summary in INCIDENT_EVENTS:
            cur.execute(
                sql,
                {
                    "id": stable_uuid("incident_event", f"{incident_code}:{event_time}:{event_type}"),
                    "incident_id": stable_uuid("incident", incident_code),
                    "event_time": event_time,
                    "event_type": event_type,
                    "actor": actor,
                    "event_summary": event_summary,
                },
            )


def main() -> None:
    require_dsn()
    with connect() as conn:
        upsert_users(conn)
        upsert_products(conn)
        upsert_locations(conn)
        upsert_inventory(conn)
        upsert_incidents(conn)
        upsert_incident_events(conn)
        conn.commit()

    print("Seeded users, products, locations, inventory, incidents, and incident_events.")
    print(f"- users: {len(USERS)}")
    print(f"- products: {len(PRODUCTS)}")
    print(f"- locations: {len(LOCATIONS)}")
    print(f"- inventory rows: {len(INVENTORY)}")
    print(f"- incidents: {len(INCIDENTS)}")
    print(f"- incident events: {len(INCIDENT_EVENTS)}")


if __name__ == "__main__":
    main()
