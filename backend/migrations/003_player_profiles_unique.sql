-- 003_player_profiles_unique.sql
-- One profile per user (rolling average embedding)
ALTER TABLE player_profiles
    ADD CONSTRAINT player_profiles_user_id_unique UNIQUE (user_id);

-- ivfflat index for cosine similarity search at scale
-- lists=10 suitable for < 10k users; tune upward as user base grows
CREATE INDEX IF NOT EXISTS idx_player_profiles_embedding
    ON player_profiles USING ivfflat (appearance_embedding vector_cosine_ops)
    WITH (lists = 10);
