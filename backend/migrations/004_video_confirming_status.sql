-- 004_video_confirming_status.sql
ALTER TABLE videos DROP CONSTRAINT videos_status_check;
ALTER TABLE videos ADD CONSTRAINT videos_status_check CHECK (
    status IN (
        'uploading', 'identifying', 'confirming',
        'processing', 'analyzed', 'failed', 'timed_out'
    )
);
