from __future__ import annotations

import base64
from dataclasses import dataclass
import os
import secrets

from fastapi.responses import JSONResponse

from app.api.schemas import SupportedUserRole


@dataclass(slots=True)
class DemoPrincipal:
    user_id: str
    user_role: SupportedUserRole


DEMO_PASSWORD_HEADER = "X-Demo-Password"
DEMO_AUTH_REALM = "CommerceOpsCopilot Demo"


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


def get_demo_access_password() -> str:
    return os.getenv("DEMO_ACCESS_PASSWORD", "").strip()


def demo_access_enabled() -> bool:
    return bool(get_demo_access_password())


def build_demo_access_headers(password: str | None) -> dict[str, str]:
    if not password:
        return {}

    token = base64.b64encode(f"demo:{password}".encode("utf-8")).decode("ascii")
    return {
        DEMO_PASSWORD_HEADER: password,
        "Authorization": f"Basic {token}",
    }


def _extract_basic_password(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    scheme, _, encoded = authorization_header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None
    _, separator, password = decoded.partition(":")
    if not separator:
        return None
    return password


def is_demo_access_allowed(
    *,
    authorization_header: str | None,
    password_header: str | None,
) -> bool:
    expected_password = get_demo_access_password()
    if not expected_password:
        return True

    for candidate in (password_header, _extract_basic_password(authorization_header)):
        if candidate and secrets.compare_digest(candidate, expected_password):
            return True
    return False


def demo_access_denied_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{DEMO_AUTH_REALM}"'},
        content={
            "status": "error",
            "error": {
                "code": "DEMO_ACCESS_REQUIRED",
                "message": (
                    f"Provide the demo password using Basic auth or the {DEMO_PASSWORD_HEADER} header."
                ),
                "details": {"header": DEMO_PASSWORD_HEADER},
            },
        },
    )


def can_decide_approvals(role: SupportedUserRole) -> bool:
    """Return True if the role is allowed to decide approvals.

    Centralized to keep permission boundaries obvious in one place.
    """
    return role in {"ops_manager", "admin"}
