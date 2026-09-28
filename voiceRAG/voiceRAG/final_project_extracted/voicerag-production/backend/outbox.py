from __future__ import annotations

import json

from sqlalchemy import update

from .db import OutboxEvent


def add_outbox_event(session, event_type: str, aggregate_id: str, payload: dict) -> OutboxEvent:
    event = OutboxEvent(event_type=event_type, aggregate_id=aggregate_id, payload=json.dumps(payload), status="pending")
    session.add(event)
    return event


async def claim_pending_events(session, limit: int = 50) -> list[OutboxEvent]:
    """Atomically transition pending rows so multiple relays cannot dispatch twice."""
    statement = update(OutboxEvent).where(OutboxEvent.status == "pending").values(status="claimed").returning(OutboxEvent)
    return list((await session.scalars(statement)).all())[:limit]
