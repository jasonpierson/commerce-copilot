from __future__ import annotations

import argparse
from typing import Any

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


def approval_count_specs() -> list[tuple[str, dict[str, Any]]]:
    user_ids = demo_user_ids()
    incident_ids = demo_incident_ids()

    return [
        (
            "approval_audit_events",
            {
                "sql": """
                    select count(*)
                    from public.audit_events
                    where event_type = any(%(event_types)s)
                      and (
                            user_id::text = any(%(user_ids)s)
                         or target_id = any(%(incident_ids)s)
                      )
                """,
                "params": {
                    "event_types": ["approval_requested", "approval_decided"],
                    "user_ids": user_ids,
                    "incident_ids": incident_ids,
                },
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
    ]


def seed_data_count_specs() -> list[tuple[str, dict[str, Any]]]:
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


def table_counts(scope: str) -> list[tuple[str, dict[str, Any]]]:
    if scope == "approvals":
        return approval_count_specs()
    return seed_data_count_specs()


def approval_delete_specs() -> list[tuple[str, dict[str, Any]]]:
    user_ids = demo_user_ids()
    incident_ids = demo_incident_ids()

    return [
        (
            "approval_audit_events",
            {
                "sql": """
                    delete from public.audit_events
                    where event_type = any(%(event_types)s)
                      and (
                            user_id::text = any(%(user_ids)s)
                         or target_id = any(%(incident_ids)s)
                      )
                """,
                "params": {
                    "event_types": ["approval_requested", "approval_decided"],
                    "user_ids": user_ids,
                    "incident_ids": incident_ids,
                },
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
    ]


def seed_data_delete_specs() -> list[tuple[str, dict[str, Any]]]:
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


def delete_specs(scope: str) -> list[tuple[str, dict[str, Any]]]:
    if scope == "approvals":
        return approval_delete_specs()
    return seed_data_delete_specs()


def print_counts(conn, scope: str) -> None:
    scope_label = "approval workflow artifacts only" if scope == "approvals" else "full seeded demo data"
    print(f"Demo cleanup scope ({scope_label}):")
    with conn.cursor() as cur:
        for table_name, spec in table_counts(scope):
            cur.execute(spec["sql"], spec["params"])
            count = cur.fetchone()["count"]
            print(f"- {table_name}: {count} row(s)")


def apply_cleanup(conn, scope: str) -> None:
    print("Deleting demo rows:")
    with conn.cursor() as cur:
        for table_name, spec in delete_specs(scope):
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
    parser.add_argument(
        "--scope",
        choices=("full", "approvals"),
        default="full",
        help="Choose whether to clean all seeded demo data or approval workflow artifacts only.",
    )
    args = parser.parse_args()

    require_dsn()
    with connect() as conn:
        print_counts(conn, args.scope)
        if not args.apply:
            print(
                "\nDry run only. Re-run with --apply to delete the demo rows above. "
                "Use --scope approvals to remove only approval workflow artifacts."
            )
            return

        print()
        apply_cleanup(conn, args.scope)


if __name__ == "__main__":
    main()
