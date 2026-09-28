from .config import settings
from celery import Celery

celery_app = Celery("voicerag", broker=settings.redis_url, backend=settings.redis_url.replace("/0", "/1"))
celery_app.conf.task_routes = {"backend.tasks.*": {"queue": "transcription"}, "backend.tasks.relay_outbox": {"queue": "maintenance"}}
celery_app.conf.beat_schedule = {"relay-outbox-every-5-seconds": {"task": "backend.tasks.relay_outbox", "schedule": 5.0}}
celery_app.autodiscover_tasks(["backend"])
