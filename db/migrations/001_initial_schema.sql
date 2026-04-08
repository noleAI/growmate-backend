-- ─────────────────────────────────────────────────────────────────────────────
-- 001_initial_schema.sql
-- Initial GrowMate schema for PostgreSQL / Supabase
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable the pgcrypto extension for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── user_profiles ─────────────────────────────────────────────────────────────
-- Stores display metadata for Supabase auth.users.
-- The user_id FK references Supabase's internal auth.users table.
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id      UUID PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    email        VARCHAR(255) NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── plants ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plants (
    plant_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    species       VARCHAR(150),
    location      VARCHAR(100),
    notes         TEXT,
    acquired_date DATE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plants_user_id ON plants(user_id);

-- ── growth_logs ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS growth_logs (
    log_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    plant_id   UUID        NOT NULL REFERENCES plants(plant_id) ON DELETE CASCADE,
    user_id    UUID        NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    height_cm  NUMERIC(7, 2) CHECK (height_cm > 0),
    leaf_count INTEGER       CHECK (leaf_count > 0),
    notes      TEXT,
    photo_url  VARCHAR(500),
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_growth_logs_plant_id_user_id
    ON growth_logs(plant_id, user_id);

CREATE INDEX IF NOT EXISTS idx_growth_logs_logged_at
    ON growth_logs(logged_at DESC);

-- ── Row-Level Security ────────────────────────────────────────────────────────
-- Enable RLS so that even direct Supabase client calls respect ownership rules.

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plants         ENABLE ROW LEVEL SECURITY;
ALTER TABLE growth_logs    ENABLE ROW LEVEL SECURITY;

-- user_profiles: users can read/write only their own profile
CREATE POLICY user_profiles_self ON user_profiles
    USING (user_id = auth.uid());

-- plants: users can manage only their own plants
CREATE POLICY plants_owner ON plants
    USING (user_id = auth.uid());

-- growth_logs: users can manage only their own logs
CREATE POLICY growth_logs_owner ON growth_logs
    USING (user_id = auth.uid());
