-- 002_reels.sql

CREATE TABLE reels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_id UUID REFERENCES videos(id) ON DELETE SET NULL,
    output_type TEXT NOT NULL CHECK (output_type IN (
        'highlight_montage', 'my_best_plays', 'game_recap',
        'points_of_improvement', 'best_shots', 'scored_point_rally',
        'full_rally_replay', 'single_shot_clip'
    )),
    r2_key TEXT,
    format TEXT NOT NULL DEFAULT 'horizontal' CHECK (format IN ('vertical', 'horizontal', 'square')),
    duration_seconds FLOAT,
    clip_ids UUID[] DEFAULT '{}',
    rally_ids UUID[] DEFAULT '{}',
    assembly_profile JSONB DEFAULT '{}',
    music_track_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'generating', 'ready', 'failed')),
    auto_generated BOOLEAN DEFAULT FALSE,
    share_token TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE clip_edits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    highlight_id UUID NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trim_start_ms INT NOT NULL DEFAULT 0,
    trim_end_ms INT,
    slow_mo_factor FLOAT NOT NULL DEFAULT 1.0,
    crop_override JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (highlight_id, user_id)
);

CREATE INDEX idx_reels_user_id ON reels(user_id);
CREATE INDEX idx_reels_video_id ON reels(video_id);
CREATE INDEX idx_reels_share_token ON reels(share_token) WHERE share_token IS NOT NULL;
CREATE INDEX idx_clip_edits_highlight_id ON clip_edits(highlight_id);
