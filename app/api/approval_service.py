from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from collections import Counter
from uuid import uuid4

from app.api.db import connect, require_dsn
from app.api.schemas import (
    ApprovalAuditEvent,
    ApprovalDashboardBucket,
    ApprovalDailyTrendBucket,
    ApprovalIncidentPressureMetric,
    ApprovalDashboardMetrics,
    ApprovalOldestPendingItemMetric,
    ApprovalPendingOwnerMetric,
    ApprovalRequesterLoadMetric,
    ApprovalRecord,
    ApprovalStatusValue,
    ApproverUserRole,
    SupportedUserRole,
    UserSummary,
)


class ApprovalNotFoundError(Exception):
    pass


class ApprovalPermissionError(Exception):
    pass


class ApprovalConflictError(Exception):
    pass


class ApprovalValidationError(Exception):
    pass


@dataclass(slots=True)
class ApprovalService:
    dsn: str

    @classmethod
    def from_env(cls) -> "ApprovalService":
        return cls(dsn=require_dsn())

    def _row_to_user(self, row, prefix: str) -> UserSummary | None:
        user_id = row.get(f"{prefix}_user_id")
        if not user_id:
            return None

        return UserSummary(
            user_id=user_id,
            full_name=row.get(f"{prefix}_full_name") or "Unknown User",
            role=row.get(f"{prefix}_role") or "support_analyst",
            email=row.get(f"{prefix}_email"),
        )

    def _next_step_for_status(self, status: ApprovalStatusValue) -> str:
        if status == "pending":
            return "Awaiting approver decision."
        if status == "approved":
            return "Approval granted. The escalation can now be executed by the workflow owner."
        return "Approval rejected. Review the decision notes and revise the request if needed."

    def _fetch_user_by_role(self, role: SupportedUserRole) -> UserSummary | None:
        sql = """
        select
            id::text as user_id,
            full_name,
            role,
            email
        from public.users
        where role = %(role)s
          and is_active = true
        order by created_at asc
        limit 1
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"role": role})
                row = cur.fetchone()

        if not row:
            return None

        return UserSummary(**row)

    def _resolve_user(self, user_id: str | None, fallback_role: SupportedUserRole) -> UserSummary:
        row = None
        if user_id:
            sql = """
            select
                id::text as user_id,
                full_name,
                role,
                email
            from public.users
            where id::text = %(user_id)s
               or lower(email) = lower(%(user_id)s)
            limit 1
            """
            with connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {"user_id": user_id.strip()})
                    row = cur.fetchone()

        if row:
            return UserSummary(**row)

        fallback = self._fetch_user_by_role(fallback_role)
        if fallback:
            return fallback

        raise ApprovalValidationError(
            f"No active user record is available for role '{fallback_role}'."
        )

    def _resolve_approver(self, preferred_roles: tuple[ApproverUserRole, ...]) -> UserSummary:
        for role in preferred_roles:
            approver = self._fetch_user_by_role(role)
            if approver:
                return approver

        raise ApprovalValidationError(
            "No active approver is available. Seed an ops manager or admin user first."
        )

    def _log_audit_event(
        self,
        *,
        event_type: str,
        user_id: str | None,
        request_id: str,
        route_type: str,
        tool_name: str,
        target_type: str,
        target_id: str,
        payload: dict,
    ) -> None:
        sql = """
        insert into public.audit_events (
            id,
            event_type,
            user_id,
            request_id,
            route_type,
            tool_name,
            target_type,
            target_id,
            event_payload_json
        ) values (
            %(id)s::uuid,
            %(event_type)s,
            %(user_id)s::uuid,
            %(request_id)s,
            %(route_type)s,
            %(tool_name)s,
            %(target_type)s,
            %(target_id)s,
            %(event_payload_json)s::jsonb
        )
        """
        try:
            with connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        {
                            "id": str(uuid4()),
                            "event_type": event_type,
                            "user_id": user_id,
                            "request_id": request_id,
                            "route_type": route_type,
                            "tool_name": tool_name,
                            "target_type": target_type,
                            "target_id": target_id,
                            "event_payload_json": json.dumps(payload),
                        },
                    )
                conn.commit()
        except Exception:
            # Audit writes are best-effort in this scaffold.
            return

    def _map_approval_row(self, row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            status=row["status"],
            request_type=row["request_type"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            requested_at=row["requested_at"],
            decided_at=row.get("decided_at"),
            decision_notes=row.get("decision_notes"),
            next_step=self._next_step_for_status(row["status"]),
            requester=self._row_to_user(row, "requester"),
            approver=self._row_to_user(row, "approver"),
            payload=row.get("payload") or {},
        )

    def _map_audit_row(self, row) -> ApprovalAuditEvent:
        actor = None
        actor_id = row.get("actor_user_id")
        if actor_id:
            actor = UserSummary(
                user_id=actor_id,
                full_name=row.get("actor_full_name") or "Unknown User",
                role=row.get("actor_role") or "support_analyst",
                email=row.get("actor_email"),
            )

        return ApprovalAuditEvent(
            audit_event_id=row["audit_event_id"],
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            route_type=row.get("route_type"),
            tool_name=row.get("tool_name"),
            request_id=row.get("request_id"),
            actor=actor,
            target_type=row.get("target_type"),
            target_id=row.get("target_id"),
            payload=row.get("payload") or {},
        )

    def get_approval_status(self, approval_id: str) -> ApprovalRecord:
        sql = """
        select
            a.id::text as approval_id,
            a.status,
            a.request_type,
            a.target_type,
            a.target_id,
            a.requested_at,
            a.decided_at,
            a.decision_notes,
            a.payload_json as payload,
            requester.id::text as requester_user_id,
            requester.full_name as requester_full_name,
            requester.role as requester_role,
            requester.email as requester_email,
            approver.id::text as approver_user_id,
            approver.full_name as approver_full_name,
            approver.role as approver_role,
            approver.email as approver_email
        from public.approvals a
        left join public.users requester
          on requester.id = a.requested_by_user_id
        left join public.users approver
          on approver.id = a.approver_user_id
        where a.id::text = %(approval_id)s
        limit 1
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"approval_id": approval_id})
                row = cur.fetchone()

        if not row:
            raise ApprovalNotFoundError(f"Approval {approval_id} was not found.")

        return self._map_approval_row(row)

    def get_approval_audit(
        self,
        approval_id: str,
        *,
        event_type: str | None = None,
    ) -> list[ApprovalAuditEvent]:
        approval = self.get_approval_status(approval_id)
        sql = """
        select
            ae.id::text as audit_event_id,
            ae.event_type,
            ae.created_at as occurred_at,
            ae.request_id,
            ae.route_type,
            ae.tool_name,
            ae.target_type,
            ae.target_id,
            ae.event_payload_json as payload,
            actor.id::text as actor_user_id,
            actor.full_name as actor_full_name,
            actor.role as actor_role,
            actor.email as actor_email
        from public.audit_events ae
        left join public.users actor
          on actor.id = ae.user_id
        where (
                ae.event_payload_json ->> 'approval_id' = %(approval_id)s
             or (
                    ae.event_type = 'approval_requested'
                and ae.target_id = %(target_id)s
                and (ae.event_payload_json ->> 'incident_code') = %(incident_code)s
             )
        )
          and (%(event_type)s::text is null or ae.event_type = %(event_type)s::text)
        order by ae.created_at asc
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "approval_id": approval_id,
                        "target_id": approval.target_id,
                        "incident_code": approval.payload.get("incident_code"),
                        "event_type": event_type,
                    },
                )
                rows = cur.fetchall()

        return [self._map_audit_row(row) for row in rows]

    def get_latest_incident_approval(self, incident_id: str) -> ApprovalRecord | None:
        sql = """
        select
            a.id::text as approval_id,
            a.status,
            a.request_type,
            a.target_type,
            a.target_id,
            a.requested_at,
            a.decided_at,
            a.decision_notes,
            a.payload_json as payload,
            requester.id::text as requester_user_id,
            requester.full_name as requester_full_name,
            requester.role as requester_role,
            requester.email as requester_email,
            approver.id::text as approver_user_id,
            approver.full_name as approver_full_name,
            approver.role as approver_role,
            approver.email as approver_email
        from public.approvals a
        left join public.users requester
          on requester.id = a.requested_by_user_id
        left join public.users approver
          on approver.id = a.approver_user_id
        where a.target_type = 'incident'
          and a.target_id = %(incident_id)s
        order by a.requested_at desc
        limit 1
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"incident_id": incident_id})
                row = cur.fetchone()

        if not row:
            return None

        return self._map_approval_row(row)

    def list_approvals(
        self,
        *,
        status: ApprovalStatusValue | None = None,
        incident_code: str | None = None,
        requester: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "requested_at",
        sort_order: str = "desc",
    ) -> tuple[list[ApprovalRecord], int]:
        sort_column = {
            "requested_at": "a.requested_at",
            "decided_at": "a.decided_at",
            "status": "a.status",
        }.get(sort_by, "a.requested_at")
        sort_direction = "asc" if sort_order == "asc" else "desc"
        offset = max(page - 1, 0) * page_size
        where_sql = """
        where (%(status)s::text is null or a.status = %(status)s::text)
          and (
                %(incident_code)s::text is null
                or (a.payload_json ->> 'incident_code') = %(incident_code)s::text
          )
          and (
                %(requester)s::text is null
                or requester.id::text = %(requester)s::text
                or lower(requester.email) = lower(%(requester)s::text)
                or lower(requester.full_name) like lower(%(requester_like)s::text)
          )
        """
        base_select = f"""
        from public.approvals a
        left join public.users requester
          on requester.id = a.requested_by_user_id
        left join public.users approver
          on approver.id = a.approver_user_id
        {where_sql}
        """
        count_sql = f"""
        select count(*) as total_count
        {base_select}
        """
        sql = f"""
        select
            a.id::text as approval_id,
            a.status,
            a.request_type,
            a.target_type,
            a.target_id,
            a.requested_at,
            a.decided_at,
            a.decision_notes,
            a.payload_json as payload,
            requester.id::text as requester_user_id,
            requester.full_name as requester_full_name,
            requester.role as requester_role,
            requester.email as requester_email,
            approver.id::text as approver_user_id,
            approver.full_name as approver_full_name,
            approver.role as approver_role,
            approver.email as approver_email
        {base_select}
        order by {sort_column} {sort_direction}, a.requested_at desc
        limit %(limit)s
        offset %(offset)s
        """
        params = {
            "status": status,
            "incident_code": incident_code,
            "requester": requester,
            "requester_like": f"%{requester}%" if requester else None,
            "limit": page_size,
            "offset": offset,
        }
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total_count = cur.fetchone()["total_count"]
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [self._map_approval_row(row) for row in rows], total_count

    def _build_pending_metrics(
        self,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
    ) -> ApprovalDashboardMetrics:
        recent_sql = """
        select
            count(*) filter (
                where a.requested_at >= (now() at time zone 'utc') - interval '24 hours'
            ) as approvals_created_last_24h,
            count(*) filter (
                where a.decided_at is not null
                  and a.decided_at >= (now() at time zone 'utc') - interval '24 hours'
            ) as approvals_decided_last_24h,
            count(*) filter (
                where a.requested_at >= (now() at time zone 'utc') - interval '7 days'
            ) as approvals_created_last_7d,
            count(*) filter (
                where a.decided_at is not null
                  and a.decided_at >= (now() at time zone 'utc') - interval '7 days'
            ) as approvals_decided_last_7d
        from public.approvals a
        left join public.users requester
          on requester.id = a.requested_by_user_id
        where (
                %(incident_code)s::text is null
                or (a.payload_json ->> 'incident_code') = %(incident_code)s::text
        )
          and (
                %(requester)s::text is null
                or requester.id::text = %(requester)s::text
                or lower(requester.email) = lower(%(requester)s::text)
                or lower(requester.full_name) like lower(%(requester_like)s::text)
          )
        """
        trend_sql = """
        select
            day.bucket_date,
            (
                select count(*)
                from public.approvals a
                left join public.users requester
                  on requester.id = a.requested_by_user_id
                where a.requested_at >= day.bucket_date
                  and a.requested_at < day.bucket_date + interval '1 day'
                  and (
                        %(incident_code)s::text is null
                        or (a.payload_json ->> 'incident_code') = %(incident_code)s::text
                  )
                  and (
                        %(requester)s::text is null
                        or requester.id::text = %(requester)s::text
                        or lower(requester.email) = lower(%(requester)s::text)
                        or lower(requester.full_name) like lower(%(requester_like)s::text)
                  )
            ) as approvals_created,
            (
                select count(*)
                from public.approvals a
                left join public.users requester
                  on requester.id = a.requested_by_user_id
                where a.decided_at is not null
                  and a.decided_at >= day.bucket_date
                  and a.decided_at < day.bucket_date + interval '1 day'
                  and (
                        %(incident_code)s::text is null
                        or (a.payload_json ->> 'incident_code') = %(incident_code)s::text
                  )
                  and (
                        %(requester)s::text is null
                        or requester.id::text = %(requester)s::text
                        or lower(requester.email) = lower(%(requester)s::text)
                        or lower(requester.full_name) like lower(%(requester_like)s::text)
                  )
            ) as approvals_decided
        from (
            select generate_series(
                date_trunc('day', (now() at time zone 'utc')) - interval '6 days',
                date_trunc('day', (now() at time zone 'utc')),
                interval '1 day'
            ) as bucket_date
        ) day
        order by day.bucket_date
        """
        pending_approvals, pending_count = self.list_approvals(
            status="pending",
            incident_code=incident_code,
            requester=requester,
            page=1,
            page_size=200,
            sort_by="requested_at",
            sort_order="asc",
        )
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    recent_sql,
                    {
                        "incident_code": incident_code,
                        "requester": requester,
                        "requester_like": f"%{requester}%" if requester else None,
                    },
                )
                recent_row = cur.fetchone()
                cur.execute(
                    trend_sql,
                    {
                        "incident_code": incident_code,
                        "requester": requester,
                        "requester_like": f"%{requester}%" if requester else None,
                    },
                )
                trend_rows = cur.fetchall()

        oldest_pending_age_minutes: int | None = None
        oldest_pending_item: ApprovalOldestPendingItemMetric | None = None
        if pending_approvals:
            oldest_pending_approval = pending_approvals[0]
            oldest_requested_at = oldest_pending_approval.requested_at
            oldest_pending_age_minutes = int(
                max((datetime.now(UTC) - oldest_requested_at).total_seconds(), 0) // 60
            )
            oldest_pending_item = ApprovalOldestPendingItemMetric(
                approval_id=oldest_pending_approval.approval_id,
                approver_name=(
                    oldest_pending_approval.approver.full_name
                    if oldest_pending_approval.approver
                    else "Unassigned approver"
                ),
                approver_role=oldest_pending_approval.approver.role if oldest_pending_approval.approver else None,
                incident_code=oldest_pending_approval.payload.get("incident_code"),
                requested_at=oldest_pending_approval.requested_at,
                pending_age_minutes=oldest_pending_age_minutes,
            )

        priority_counts = Counter(
            (approval.payload.get("proposed_priority") or "unknown")
            for approval in pending_approvals
        )
        owner_counts: Counter[tuple[str, str | None]] = Counter(
            (
                approval.approver.full_name if approval.approver else "Unassigned approver",
                approval.approver.role if approval.approver else None,
            )
            for approval in pending_approvals
        )
        requester_counts: Counter[tuple[str, str | None]] = Counter(
            (
                approval.requester.full_name if approval.requester else "Unknown requester",
                approval.requester.role if approval.requester else None,
            )
            for approval in pending_approvals
        )
        incident_counts = Counter(
            approval.payload.get("incident_code") or "unknown_incident"
            for approval in pending_approvals
        )
        owners = [
            ApprovalPendingOwnerMetric(
                approver_name=name,
                approver_role=role,
                pending_count=count,
            )
            for (name, role), count in sorted(
                owner_counts.items(),
                key=lambda item: (-item[1], item[0][0]),
            )
        ]
        requesters = [
            ApprovalRequesterLoadMetric(
                requester_name=name,
                requester_role=role,
                pending_count=count,
            )
            for (name, role), count in sorted(
                requester_counts.items(),
                key=lambda item: (-item[1], item[0][0]),
            )
        ]
        incidents = [
            ApprovalIncidentPressureMetric(
                incident_code=incident_code,
                pending_count=count,
            )
            for incident_code, count in sorted(
                incident_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        trends = [
            ApprovalDailyTrendBucket(
                bucket_date=row["bucket_date"],
                approvals_created=row["approvals_created"] or 0,
                approvals_decided=row["approvals_decided"] or 0,
            )
            for row in trend_rows
        ]

        return ApprovalDashboardMetrics(
            pending_count=pending_count,
            approvals_created_last_24h=recent_row["approvals_created_last_24h"] or 0,
            approvals_decided_last_24h=recent_row["approvals_decided_last_24h"] or 0,
            approvals_created_last_7d=recent_row["approvals_created_last_7d"] or 0,
            approvals_decided_last_7d=recent_row["approvals_decided_last_7d"] or 0,
            oldest_pending_age_minutes=oldest_pending_age_minutes,
            oldest_pending_item=oldest_pending_item,
            pending_by_priority=dict(sorted(priority_counts.items())),
            pending_by_owner=owners,
            pending_by_requester=requesters,
            pending_by_incident=incidents,
            daily_trends_7d=trends,
        )

    def get_approval_dashboard(
        self,
        *,
        incident_code: str | None = None,
        requester: str | None = None,
        page_size_per_bucket: int = 5,
    ) -> tuple[list[ApprovalDashboardBucket], ApprovalDashboardMetrics]:
        buckets: list[ApprovalDashboardBucket] = []
        for status in ("pending", "approved", "rejected"):
            approvals, total_count = self.list_approvals(
                status=status,
                incident_code=incident_code,
                requester=requester,
                page=1,
                page_size=page_size_per_bucket,
                sort_by="requested_at",
                sort_order="desc",
            )
            buckets.append(
                ApprovalDashboardBucket(
                    status=status,
                    count=total_count,
                    approvals=approvals,
                )
            )
        metrics = self._build_pending_metrics(incident_code=incident_code, requester=requester)
        return buckets, metrics

    def create_incident_escalation_request(
        self,
        *,
        incident_id: str,
        incident_code: str,
        requested_by_user_id: str,
        requested_by_role: SupportedUserRole,
        escalation_reason: str,
        proposed_priority: str,
        draft_summary: str,
        request_id: str,
    ) -> ApprovalRecord:
        requester = self._resolve_user(requested_by_user_id, requested_by_role)
        approver = self._resolve_approver(("ops_manager", "admin"))

        sql = """
        insert into public.approvals (
            id,
            request_type,
            target_type,
            target_id,
            requested_by_user_id,
            approver_user_id,
            status,
            payload_json
        ) values (
            %(id)s::uuid,
            'incident_escalation',
            'incident',
            %(target_id)s,
            %(requested_by_user_id)s::uuid,
            %(approver_user_id)s::uuid,
            'pending',
            %(payload_json)s::jsonb
        )
        """
        approval_id = str(uuid4())
        payload = {
            "approval_id": approval_id,
            "incident_code": incident_code,
            "escalation_reason": escalation_reason,
            "proposed_priority": proposed_priority,
            "draft_summary": draft_summary,
        }

        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "id": approval_id,
                        "target_id": incident_id,
                        "requested_by_user_id": requester.user_id,
                        "approver_user_id": approver.user_id,
                        "payload_json": json.dumps(payload),
                    },
                )
            conn.commit()

        self._log_audit_event(
            event_type="approval_requested",
            user_id=requester.user_id,
            request_id=request_id,
            route_type="approval_request",
            tool_name="create_incident_escalation_request",
            target_type="incident",
            target_id=incident_id,
            payload=payload,
        )

        return self.get_approval_status(approval_id)

    def decide_approval(
        self,
        *,
        approval_id: str,
        decider_user_id: str,
        decider_role: SupportedUserRole,
        decision: str,
        decision_notes: str | None,
        request_id: str,
    ) -> ApprovalRecord:
        if decider_role not in {"ops_manager", "admin"}:
            raise ApprovalPermissionError("Only ops managers or admins may decide approvals.")

        decider = self._resolve_user(decider_user_id, decider_role)
        approval = self.get_approval_status(approval_id)
        if approval.status != "pending":
            raise ApprovalConflictError(
                f"Approval {approval_id} is already {approval.status} and cannot be decided again."
            )

        sql = """
        update public.approvals
        set
            approver_user_id = %(approver_user_id)s::uuid,
            status = %(status)s,
            decision_notes = %(decision_notes)s,
            decided_at = %(decided_at)s
        where id::text = %(approval_id)s
        """
        decided_at = datetime.now(UTC)
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "approval_id": approval_id,
                        "approver_user_id": decider.user_id,
                        "status": decision,
                        "decision_notes": decision_notes,
                        "decided_at": decided_at,
                    },
                )
            conn.commit()

        self._log_audit_event(
            event_type="approval_decided",
            user_id=decider.user_id,
            request_id=request_id,
            route_type="approval_decision",
            tool_name="decide_approval",
            target_type=approval.target_type,
            target_id=approval.target_id,
            payload={
                "approval_id": approval_id,
                "decision": decision,
                "decision_notes": decision_notes,
            },
        )

        return self.get_approval_status(approval_id)
