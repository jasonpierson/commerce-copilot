from __future__ import annotations

import argparse

from app.api.db import connect, require_dsn

try:
    from scripts.seed_domain_data import INCIDENTS, LOCATIONS, PRODUCTS, USERS, stable_uuid
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution
    from seed_domain_data import INCIDENTS, LOCATIONS, PRODUCTS, USERS, stable_uuid


def demo_user_ids() -> list[str]:
    return [stable_uuid("user", row["email"]) for row in USERS]


def demo_product_ids() -> list[str]:
    return [stable_uuid("product", row["sku"]) for row in PRODUCTS]


def demo_location_ids() -> list[str]:
    return [stable_uuid("location", row["location_code"]) for row in LOCATIONS]


def demo_incident_ids() -> list[str]:
    return [stable_uuid("incident", row["incident_code"]) for row in INCIDENTS]


def table_counts(conn) -> list[tuple[str, dict[str, list[str]]]]:
    user_ids = demo_user_ids()
    product_ids = demo_product_ids()
    location_ids = demo_location_ids()
    incident_ids = demo_incident_ids()
    seed_target_ids = incident_ids + product_ids + location_ids

    return [
        (
            "audit_events",
            {
                "sql": """
                    select count(*)
                    from public.audit_events
                    where user_id::text = any(%(user_ids)s)
                       or target_id = any(%(seed_target_ids)s)
                """,
                "params": {"user_ids": user_ids, "seed_target_ids": seed_target_ids},
            },
        ),
        (
            "approvals",
            {
                "sql": """
                    select count(*)
                    from public.approvals
                    where target_id = any(%(incident_ids)s)
                       or requested_by_user_id::text = any(%(user_ids)s)
                       or approver_user_id::text = any(%(user_ids)s)
                """,
                "params": {"incident_ids": incident_ids, "user_ids": user_ids},
            },
        ),
        (
            "incident_events",
            {
                "sql": """
                    select count(*)
                    from public.incident_events
                    where incident_id::text = any(%(incident_ids)s)
                """,
                "params": {"incident_ids": incident_ids},
            },
        ),
        (
            "incidents",
            {
                "sql": """
                    select count(*)
                    from public.incidents
                    where id::text = any(%(incident_ids)s)
                """,
                "params": {"incident_ids": incident_ids},
            },
        ),
        (
            "inventory",
            {
                "sql": """
                    select count(*)
                    from public.inventory
                    where product_id::text = any(%(product_ids)s)
                       or location_id::text = any(%(location_ids)s)
                """,
                "params": {"product_ids": product_ids, "location_ids": location_ids},
            },
        ),
        (
            "products",
            {
                "sql": """
                    select count(*)
                    from public.products
                    where id::text = any(%(product_ids)s)
                """,
                "params": {"product_ids": product_ids},
            },
        ),
        (
            "locations",
            {
                "sql": """
                    select count(*)
                    from public.locations
                    where id::text = any(%(location_ids)s)
                """,
                "params": {"location_ids": location_ids},
            },
        ),
        (
            "users",
            {
                "sql": """
                    select count(*)
                    from public.users
                    where id::text = any(%(user_ids)s)
                """,
                "params": {"user_ids": user_ids},
            },
        ),
    ]


def delete_specs() -> list[tuple[str, dict[str, list[str]]]]:
    user_ids = demo_user_ids()
    product_ids = demo_product_ids()
    location_ids = demo_location_ids()
    incident_ids = demo_incident_ids()
    seed_target_ids = incident_ids + product_ids + location_ids

    return [
        (
            "audit_events",
            {
                "sql": """
                    delete from public.audit_events
                    where user_id::text = any(%(user_ids)s)
                       or target_id = any(%(seed_target_ids)s)
                """,
                "params": {"user_ids": user_ids, "seed_target_ids": seed_target_ids},
            },
        ),
        (
            "approvals",
            {
                "sql": """
                    delete from public.approvals
                    where target_id = any(%(incident_ids)s)
                       or requested_by_user_id::text = any(%(user_ids)s)
                       or approver_user_id::text = any(%(user_ids)s)
                """,
                "params": {"incident_ids": incident_ids, "user_ids": user_ids},
            },
        ),
        (
            "incident_events",
            {
                "sql": """
                    delete from public.incident_events
                    where incident_id::text = any(%(incident_ids)s)
                """,
                "params": {"incident_ids": incident_ids},
            },
        ),
        (
            "incidents",
            {
                "sql": """
                    delete from public.incidents
                    where id::text = any(%(incident_ids)s)
                """,
                "params": {"incident_ids": incident_ids},
            },
        ),
        (
            "inventory",
            {
                "sql": """
                    delete from public.inventory
                    where product_id::text = any(%(product_ids)s)
                       or location_id::text = any(%(location_ids)s)
                """,
                "params": {"product_ids": product_ids, "location_ids": location_ids},
            },
        ),
        (
            "products",
            {
                "sql": """
                    delete from public.products
                    where id::text = any(%(product_ids)s)
                """,
                "params": {"product_ids": product_ids},
            },
        ),
        (
            "locations",
            {
                "sql": """
                    delete from public.locations
                    where id::text = any(%(location_ids)s)
                """,
                "params": {"location_ids": location_ids},
            },
        ),
        (
            "users",
            {
                "sql": """
                    delete from public.users
                    where id::text = any(%(user_ids)s)
                """,
                "params": {"user_ids": user_ids},
            },
        ),
    ]


def print_counts(conn) -> None:
    print("Demo cleanup scope:")
    with conn.cursor() as cur:
        for table_name, spec in table_counts(conn):
            cur.execute(spec["sql"], spec["params"])
            count = cur.fetchone()["count"]
            print(f"- {table_name}: {count} row(s)")


def apply_cleanup(conn) -> None:
    print("Deleting demo rows:")
    with conn.cursor() as cur:
        for table_name, spec in delete_specs():
            cur.execute(spec["sql"], spec["params"])
            deleted = cur.rowcount
            print(f"- {table_name}: deleted {deleted} row(s)")
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or delete demo approvals and seeded operational data."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the demo data. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()

    require_dsn()
    with connect() as conn:
        print_counts(conn)
        if not args.apply:
            print("\nDry run only. Re-run with --apply to delete the demo rows above.")
            return

        print()
        apply_cleanup(conn)


if __name__ == "__main__":
    main()
