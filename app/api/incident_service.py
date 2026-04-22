from __future__ import annotations

from dataclasses import dataclass

from app.api.db import connect, require_dsn
from app.api.schemas import IncidentEvent, IncidentRecord


@dataclass(slots=True)
class IncidentService:
    dsn: str

    @classmethod
    def from_env(cls) -> "IncidentService":
        return cls(dsn=require_dsn())

    def get_incident(self, incident_code: str) -> IncidentRecord | None:
        sql = """
        select
            id::text as incident_id,
            incident_code,
            title,
            status,
            severity,
            service_area,
            summary,
            customer_impact,
            start_time,
            resolved_time
        from app_private.incidents
        where upper(incident_code) = upper(%(incident_code)s)
        limit 1
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"incident_code": incident_code.strip()})
                row = cur.fetchone()

        if not row:
            return None

        return IncidentRecord(**row)

    def get_incident_timeline(self, incident_id: str) -> list[IncidentEvent]:
        sql = """
        select
            event_time,
            event_type,
            actor,
            event_summary
        from app_private.incident_events
        where incident_id::text = %(incident_id)s
        order by event_time asc
        """
        with connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"incident_id": incident_id})
                rows = cur.fetchall()

        return [IncidentEvent(**row) for row in rows]
