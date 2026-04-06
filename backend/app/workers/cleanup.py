from app.workers.celery_app import celery


@celery.task(name="app.workers.cleanup.cleanup_stale_jobs")
def cleanup_stale_jobs():
    """Cancel jobs stuck in 'identifying' for > 24 hours. Implemented in Task 17."""
    pass
