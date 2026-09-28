from __future__ import annotations

import asyncio
import json

from .celery_app import celery_app
from .config import settings
from .db import create_database
from .outbox import claim_pending_events
from .tasks import process_document


async def _relay(limit: int) -> int:
    engine, session_factory = create_database(settings.database_url)
    dispatched = 0
    try:
        async with session_factory() as session:
            async with session.begin():
                events = await claim_pending_events(session, limit)
                payloads = [(event, json.loads(event.payload)) for event in events]
            for event, payload in payloads:
                if event.event_type == "document.processing_requested":
                    process_document.delay(payload["document_id"], payload["object_key"])
                    async with session.begin():
                        event.status = "dispatched"
                    dispatched += 1
        return dispatched
    finally:
        await engine.dispose()


@celery_app.task(name="backend.tasks.relay_outbox")
def relay_outbox(limit: int = 50) -> int:
    return asyncio.run(_relay(limit))
