from __future__ import annotations

from dataclasses import dataclass

from app.api.schemas import SupportedUserRole


@dataclass(slots=True)
class DemoPrincipal:
    user_id: str
    user_role: SupportedUserRole


def resolve_demo_principal(
    *,
    header_user_id: str | None,
    header_user_role: SupportedUserRole | None,
    fallback_user_id: str,
    fallback_user_role: SupportedUserRole,
) -> DemoPrincipal:
    return DemoPrincipal(
        user_id=(header_user_id or fallback_user_id).strip(),
        user_role=header_user_role or fallback_user_role,
    )
