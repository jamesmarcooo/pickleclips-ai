from app.workers.celery_app import celery


@celery.task(bind=True, name="app.workers.ingest.ingest_video")
def ingest_video(self, video_id: str, user_id: str):
    """Full pipeline for a new video. Runs on GPU instance."""
    raise NotImplementedError("Implemented in Task 8")


@celery.task(bind=True, name="app.workers.ingest.resume_after_identify")
def resume_after_identify(self, video_id: str, user_id: str, seed_bbox: dict):
    """Resumes pipeline after user tap-to-identify."""
    raise NotImplementedError("Implemented in Task 15")
