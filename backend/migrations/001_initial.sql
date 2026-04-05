-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Users (mirrors Supabase auth.users, stores app-specific fields)
CREATE TABLE users (
    id UUID PRIMARY KEY,  -- same as Supabase auth user id
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    avatar_url TEXT,
    highlight_preferences JSONB DEFAULT '{}',
    subscription_tier TEXT NOT NULL DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'team')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Player profiles (persistent Re-ID embeddings per user)
CREATE TABLE player_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    appearance_embedding VECTOR(512),  -- OSNet osnet_x1_0 outputs 512-dim
    embedding_confidence FLOAT DEFAULT 0.0,
    uploads_contributing INT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Videos
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    r2_key_original TEXT,
    r2_key_processed TEXT,
    duration_seconds FLOAT,
    resolution TEXT,
    status TEXT NOT NULL DEFAULT 'uploading' CHECK (
        status IN ('uploading', 'identifying', 'processing', 'analyzed', 'failed', 'timed_out')
    ),
    identify_started_at TIMESTAMPTZ,
    cleanup_after TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Video players (per-video player roles)
CREATE TABLE video_players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'partner', 'opponent_1', 'opponent_2')),
    player_profile_id UUID REFERENCES player_profiles(id),
    seed_frame_bbox JSONB,   -- {x, y, w, h} in pixels
    appearance_embedding VECTOR(512),
    tracking_confidence FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Rallies
CREATE TABLE rallies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    start_time_ms INT NOT NULL,
    end_time_ms INT NOT NULL,
    shot_count INT DEFAULT 0,
    intensity_score FLOAT DEFAULT 0.0,
    point_won_by TEXT CHECK (point_won_by IN ('user_team', 'opponent_team')),
    score_before JSONB DEFAULT '{}',
    score_after JSONB DEFAULT '{}',
    is_comeback_point BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Highlights (and lowlights)
CREATE TABLE highlights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    rally_id UUID REFERENCES rallies(id) ON DELETE SET NULL,
    attributed_player_role TEXT CHECK (attributed_player_role IN ('user', 'partner', 'opponent_1', 'opponent_2')),
    sub_highlight_type TEXT NOT NULL CHECK (
        sub_highlight_type IN ('shot_form', 'point_scored', 'lowlight', 'both')
    ),
    lowlight_type TEXT CHECK (
        lowlight_type IN ('unforced_error', 'positioning', 'weak_shot', 'lost_point')
    ),
    point_lost_by_error BOOLEAN DEFAULT FALSE,
    start_time_ms INT NOT NULL,
    end_time_ms INT NOT NULL,
    highlight_score FLOAT DEFAULT 0.0,
    highlight_score_raw FLOAT DEFAULT 0.0,
    shot_type TEXT CHECK (
        shot_type IN ('drive', 'dink', 'lob', 'erne', 'atp', 'drop', 'smash', 'overhead', 'speed_up')
    ),
    shot_quality FLOAT DEFAULT 0.5,
    point_scored BOOLEAN DEFAULT FALSE,
    point_won_by TEXT CHECK (point_won_by IN ('user_team', 'opponent_team')),
    rally_length INT DEFAULT 0,
    rally_intensity FLOAT DEFAULT 0.0,
    score_source TEXT NOT NULL DEFAULT 'rule_based' CHECK (score_source IN ('ocr', 'rule_based', 'manual')),
    r2_key_clip TEXT,  -- set after clip extraction
    model_outputs JSONB DEFAULT '{}',
    user_feedback TEXT CHECK (user_feedback IN ('liked', 'disliked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_videos_user_id ON videos(user_id);
CREATE INDEX idx_videos_status ON videos(status);
CREATE INDEX idx_highlights_video_id ON highlights(video_id);
CREATE INDEX idx_highlights_score ON highlights(highlight_score DESC);
CREATE INDEX idx_rallies_video_id ON rallies(video_id);
