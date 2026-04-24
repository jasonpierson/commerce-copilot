from __future__ import annotations

import base64
from dataclasses import dataclass
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import field
from typing import Pattern
import re

from fastapi.responses import JSONResponse

from app.api.schemas import SupportedUserRole


@dataclass(slots=True)
class DemoPrincipal:
    user_id: str
    user_role: SupportedUserRole


DEMO_PASSWORD_HEADER = "X-Demo-Password"
DEMO_AUTH_REALM = "CommerceOpsCopilot Demo"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    name: str
    method: str
    path_pattern: Pattern[str]
    limit: int
    window_seconds: int


@dataclass(slots=True)
class InMemoryRateLimiter:
    _requests: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, *, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        threshold = now - window_seconds
        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= threshold:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now))
                return False, retry_after
            bucket.append(now)
        return True, 0

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


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


def rate_limit_exceeded_response(*, rule_name: str, retry_after_seconds: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after_seconds)},
        content={
            "status": "error",
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests for this hosted demo. Please slow down and try again shortly.",
                "details": {
                    "rule": rule_name,
                    "retry_after_seconds": retry_after_seconds,
                },
            },
        },
    )


def current_rate_limit_rules() -> tuple[RateLimitRule, ...]:
    query_limit = int(os.getenv("QUERY_RATE_LIMIT_MAX_REQUESTS", "30"))
    query_window = int(os.getenv("QUERY_RATE_LIMIT_WINDOW_SECONDS", "60"))
    approval_limit = int(os.getenv("APPROVAL_RATE_LIMIT_MAX_REQUESTS", "10"))
    approval_window = int(os.getenv("APPROVAL_RATE_LIMIT_WINDOW_SECONDS", "60"))
    return (
        RateLimitRule(
            name="query",
            method="POST",
            path_pattern=re.compile(r"^/api/v1/query$"),
            limit=query_limit,
            window_seconds=query_window,
        ),
        RateLimitRule(
            name="approval_create",
            method="POST",
            path_pattern=re.compile(r"^/api/v1/escalations$"),
            limit=approval_limit,
            window_seconds=approval_window,
        ),
        RateLimitRule(
            name="approval_decision",
            method="POST",
            path_pattern=re.compile(r"^/api/v1/approvals/[^/]+/decision$"),
            limit=approval_limit,
            window_seconds=approval_window,
        ),
    )


def request_fingerprint(
    *,
    path: str,
    method: str,
    forwarded_for: str | None,
    client_host: str | None,
    user_id: str | None,
) -> str:
    forwarded_ip = (forwarded_for or "").split(",", 1)[0].strip()
    principal = (user_id or "").strip() or "anonymous"
    host = forwarded_ip or client_host or "unknown"
    return f"{method}:{path}:{host}:{principal}"


def can_decide_approvals(role: SupportedUserRole) -> bool:
    """Return True if the role is allowed to decide approvals.

    Centralized to keep permission boundaries obvious in one place.
    """
    return role in {"ops_manager", "admin"}
