PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  started_at INTEGER NOT NULL, -- unix seconds
  ended_at INTEGER NULL,       -- unix seconds; NULL means active
  note TEXT NULL,
  CHECK (started_at >= 0),
  CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id TEXT PRIMARY KEY,
  report_channel_id TEXT NULL,
  panel_channel_id TEXT NULL,
  panel_message_id TEXT NULL,
  clocked_in_role_id TEXT NULL,
  nickname_hours_enabled INTEGER NOT NULL DEFAULT 1,
  timezone TEXT NOT NULL,
  week_start INTEGER NOT NULL, -- 0=Mon .. 6=Sun
  CHECK (week_start >= 0 AND week_start <= 6)
);

-- Reporting lookups.
CREATE INDEX IF NOT EXISTS idx_sessions_guild_user_started
  ON sessions(guild_id, user_id, started_at);

-- Ensure only one active session exists per (guild_id, user_id).
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active
  ON sessions(guild_id, user_id)
  WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS weekly_leaderboard_posts (
  channel_id TEXT NOT NULL,
  week_start_ts INTEGER NOT NULL,
  posted_at_ts INTEGER NOT NULL,
  PRIMARY KEY(channel_id, week_start_ts)
);
