from celery import Celery
from app.config import settings

celery = Celery(
    "pickleclips",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.ingest",
        "app.workers.cleanup",
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # re-queue on worker crash
    worker_prefetch_multiplier=1,  # one task at a time per worker (GPU work)
    beat_schedule={
        "cleanup-stale-identify-jobs": {
            "task": "app.workers.cleanup.cleanup_stale_jobs",
            "schedule": 3600.0,  # every hour
        },
    },
)
