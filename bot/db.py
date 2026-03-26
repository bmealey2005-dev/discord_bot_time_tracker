from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import aiosqlite
import asyncpg


class Database:
    def __init__(self, db_target: str, schema_sql_path: str) -> None:
        self._db_target = db_target
        self._schema_sql_path = schema_sql_path
        self._conn: aiosqlite.Connection | None = None
        self._pool: asyncpg.Pool | None = None
        self._is_postgres = db_target.startswith("postgres://") or db_target.startswith("postgresql://")

    @property
    def path(self) -> str:
        return self._db_target

    async def connect(self) -> None:
        if self._is_postgres:
            if self._pool is not None:
                return
            self._pool = await asyncpg.create_pool(self._db_target, min_size=1, max_size=5, command_timeout=30)
            return

        if self._conn is not None:
            return

        # Ensure parent directory exists (for ./data/... default).
        db_parent = Path(self._db_target).expanduser().resolve().parent
        db_parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self._db_target)
        self._conn.row_factory = aiosqlite.Row

        # Pragmas for reliability on small bots.
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA synchronous = NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.commit()

    async def close(self) -> None:
        if self._is_postgres:
            if self._pool is None:
                return
            await self._pool.close()
            self._pool = None
            return

        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def init_schema(self) -> None:
        if self._is_postgres:
            await self._init_schema_postgres()
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        with open(self._schema_sql_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        await self._conn.executescript(schema_sql)
        await self._migrate_sqlite()
        await self._conn.commit()

    async def _init_schema_postgres(self) -> None:
        if self._pool is None:
            raise RuntimeError("Database.connect() must be called first.")

        stmts = [
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id BIGSERIAL PRIMARY KEY,
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              started_at BIGINT NOT NULL,
              ended_at BIGINT NULL,
              note TEXT NULL,
              CHECK (started_at >= 0),
              CHECK (ended_at IS NULL OR ended_at >= started_at)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
              guild_id TEXT PRIMARY KEY,
              report_channel_id TEXT NULL,
              panel_channel_id TEXT NULL,
              panel_message_id TEXT NULL,
              clocked_in_role_id TEXT NULL,
              nickname_hours_enabled INTEGER NOT NULL DEFAULT 1,
              timezone TEXT NOT NULL,
              week_start INTEGER NOT NULL,
              CHECK (week_start >= 0 AND week_start <= 6)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_guild_user_started
              ON sessions(guild_id, user_id, started_at);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active
              ON sessions(guild_id, user_id)
              WHERE ended_at IS NULL;
            """,
            """
            CREATE TABLE IF NOT EXISTS weekly_leaderboard_posts (
              channel_id TEXT NOT NULL,
              week_start_ts BIGINT NOT NULL,
              posted_at_ts BIGINT NOT NULL,
              PRIMARY KEY(channel_id, week_start_ts)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS session_offline_flags (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              session_id BIGINT NOT NULL,
              offline_started_at BIGINT NOT NULL,
              prompt_message_id TEXT NULL,
              prompted_at BIGINT NULL,
              resolved_at BIGINT NULL,
              PRIMARY KEY(guild_id, user_id)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_session_offline_flags_unresolved
              ON session_offline_flags(guild_id, user_id, session_id)
              WHERE resolved_at IS NULL;
            """,
            "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS panel_channel_id TEXT NULL;",
            "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS panel_message_id TEXT NULL;",
            "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS clocked_in_role_id TEXT NULL;",
            "ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS nickname_hours_enabled INTEGER NOT NULL DEFAULT 1;",
        ]

        async with self._pool.acquire() as conn:
            for stmt in stmts:
                await conn.execute(stmt)

    async def _migrate_sqlite(self) -> None:
        """Lightweight migrations for existing SQLite files."""
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        # Add new columns to guild_settings if the DB was created
        # before we introduced them.
        cur = await self._conn.execute("PRAGMA table_info('guild_settings');")
        rows = await cur.fetchall()
        existing_cols = {str(r["name"]) for r in rows}

        # SQLite doesn't support "ADD COLUMN IF NOT EXISTS".
        if "panel_channel_id" not in existing_cols:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN panel_channel_id TEXT NULL;")
        if "panel_message_id" not in existing_cols:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN panel_message_id TEXT NULL;")
        if "clocked_in_role_id" not in existing_cols:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN clocked_in_role_id TEXT NULL;")
        if "nickname_hours_enabled" not in existing_cols:
            await self._conn.execute(
                "ALTER TABLE guild_settings ADD COLUMN nickname_hours_enabled INTEGER NOT NULL DEFAULT 1;"
            )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_leaderboard_posts (
              channel_id TEXT NOT NULL,
              week_start_ts INTEGER NOT NULL,
              posted_at_ts INTEGER NOT NULL,
              PRIMARY KEY(channel_id, week_start_ts)
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_offline_flags (
              guild_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              session_id INTEGER NOT NULL,
              offline_started_at INTEGER NOT NULL,
              prompt_message_id TEXT NULL,
              prompted_at INTEGER NULL,
              resolved_at INTEGER NULL,
              PRIMARY KEY(guild_id, user_id)
            );
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_offline_flags_unresolved
              ON session_offline_flags(guild_id, user_id, session_id)
              WHERE resolved_at IS NULL;
            """
        )

    @staticmethod
    def _sqlite_row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        return {k: row[k] for k in row.keys()}

    @staticmethod
    def _overlap_seconds(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
        start = max(int(a_start), int(b_start))
        end = min(int(a_end), int(b_end))
        return max(0, end - start)

    async def ensure_guild_settings(
        self,
        *,
        guild_id: int,
        default_timezone: str,
        default_week_start: int,
        default_clocked_in_role_id: int | None = None,
    ) -> None:
        role_value = str(default_clocked_in_role_id) if default_clocked_in_role_id is not None else None
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO guild_settings(guild_id, report_channel_id, clocked_in_role_id, timezone, week_start)
                    VALUES($1, NULL, $2, $3, $4)
                    ON CONFLICT(guild_id) DO NOTHING;
                    """,
                    str(guild_id),
                    role_value,
                    default_timezone,
                    int(default_week_start),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            INSERT INTO guild_settings(guild_id, report_channel_id, clocked_in_role_id, timezone, week_start)
            VALUES(?, NULL, ?, ?, ?)
            ON CONFLICT(guild_id) DO NOTHING;
            """,
            (str(guild_id), role_value, default_timezone, default_week_start),
        )
        await self._conn.commit()

    async def get_guild_settings(self, *, guild_id: int) -> dict[str, Any]:
        row: Mapping[str, Any] | None
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT guild_id, report_channel_id, panel_channel_id, panel_message_id, clocked_in_role_id,
                           nickname_hours_enabled, timezone, week_start
                    FROM guild_settings
                    WHERE guild_id = $1;
                    """,
                    str(guild_id),
                )
        else:
            if self._conn is None:
                raise RuntimeError("Database.connect() must be called first.")

            cur = await self._conn.execute(
                """
                SELECT guild_id, report_channel_id, panel_channel_id, panel_message_id, clocked_in_role_id,
                       nickname_hours_enabled, timezone, week_start
                FROM guild_settings
                WHERE guild_id = ?;
                """,
                (str(guild_id),),
            )
            sqlite_row = await cur.fetchone()
            row = self._sqlite_row_to_dict(sqlite_row) if sqlite_row is not None else None

        if row is None:
            raise KeyError(f"Missing guild_settings row for guild_id={guild_id}")

        nickname_raw = row["nickname_hours_enabled"]
        nickname_enabled = bool(int(nickname_raw)) if nickname_raw is not None else True

        return {
            "guild_id": int(row["guild_id"]),
            "report_channel_id": int(row["report_channel_id"]) if row["report_channel_id"] is not None else None,
            "panel_channel_id": int(row["panel_channel_id"]) if row["panel_channel_id"] is not None else None,
            "panel_message_id": int(row["panel_message_id"]) if row["panel_message_id"] is not None else None,
            "clocked_in_role_id": int(row["clocked_in_role_id"]) if row["clocked_in_role_id"] is not None else None,
            "nickname_hours_enabled": nickname_enabled,
            "timezone": str(row["timezone"]),
            "week_start": int(row["week_start"]),
        }

    async def set_report_channel(self, *, guild_id: int, channel_id: int | None) -> None:
        value = str(channel_id) if channel_id is not None else None
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_settings SET report_channel_id = $1 WHERE guild_id = $2;",
                    value,
                    str(guild_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            "UPDATE guild_settings SET report_channel_id = ? WHERE guild_id = ?;",
            (value, str(guild_id)),
        )
        await self._conn.commit()

    async def set_panel_message(
        self,
        *,
        guild_id: int,
        channel_id: int | None,
        message_id: int | None,
    ) -> None:
        channel_value = str(channel_id) if channel_id is not None else None
        message_value = str(message_id) if message_id is not None else None
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE guild_settings
                    SET panel_channel_id = $1, panel_message_id = $2
                    WHERE guild_id = $3;
                    """,
                    channel_value,
                    message_value,
                    str(guild_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            UPDATE guild_settings
            SET panel_channel_id = ?, panel_message_id = ?
            WHERE guild_id = ?;
            """,
            (
                channel_value,
                message_value,
                str(guild_id),
            ),
        )
        await self._conn.commit()

    async def set_clocked_in_role(self, *, guild_id: int, role_id: int | None) -> None:
        value = str(role_id) if role_id is not None else None
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_settings SET clocked_in_role_id = $1 WHERE guild_id = $2;",
                    value,
                    str(guild_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            "UPDATE guild_settings SET clocked_in_role_id = ? WHERE guild_id = ?;",
            (value, str(guild_id)),
        )
        await self._conn.commit()

    async def set_nickname_hours_enabled(self, *, guild_id: int, enabled: bool) -> None:
        value = 1 if enabled else 0
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_settings SET nickname_hours_enabled = $1 WHERE guild_id = $2;",
                    value,
                    str(guild_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            "UPDATE guild_settings SET nickname_hours_enabled = ? WHERE guild_id = ?;",
            (value, str(guild_id)),
        )
        await self._conn.commit()

    async def set_timezone(self, *, guild_id: int, timezone: str) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE guild_settings SET timezone = $1 WHERE guild_id = $2;",
                    timezone,
                    str(guild_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            "UPDATE guild_settings SET timezone = ? WHERE guild_id = ?;",
            (timezone, str(guild_id)),
        )
        await self._conn.commit()

    async def has_weekly_leaderboard_post(self, *, channel_id: int, week_start_ts: int) -> bool:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                exists = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1
                        FROM weekly_leaderboard_posts
                        WHERE channel_id = $1 AND week_start_ts = $2
                    );
                    """,
                    str(channel_id),
                    int(week_start_ts),
                )
                return bool(exists)

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            """
            SELECT 1
            FROM weekly_leaderboard_posts
            WHERE channel_id = ? AND week_start_ts = ?
            LIMIT 1;
            """,
            (str(channel_id), int(week_start_ts)),
        )
        row = await cur.fetchone()
        return row is not None

    async def mark_weekly_leaderboard_post(
        self,
        *,
        channel_id: int,
        week_start_ts: int,
        posted_at_ts: int,
    ) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO weekly_leaderboard_posts(channel_id, week_start_ts, posted_at_ts)
                    VALUES($1, $2, $3)
                    ON CONFLICT(channel_id, week_start_ts) DO NOTHING;
                    """,
                    str(channel_id),
                    int(week_start_ts),
                    int(posted_at_ts),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            INSERT OR IGNORE INTO weekly_leaderboard_posts(channel_id, week_start_ts, posted_at_ts)
            VALUES(?, ?, ?);
            """,
            (str(channel_id), int(week_start_ts), int(posted_at_ts)),
        )
        await self._conn.commit()

    async def get_session_offline_flag(self, *, guild_id: int, user_id: int) -> Mapping[str, Any] | None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                    FROM session_offline_flags
                    WHERE guild_id = $1 AND user_id = $2;
                    """,
                    str(guild_id),
                    str(user_id),
                )
                return row

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            """
            SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
            FROM session_offline_flags
            WHERE guild_id = ? AND user_id = ?;
            """,
            (str(guild_id), str(user_id)),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return self._sqlite_row_to_dict(row)

    async def upsert_session_offline_flag(
        self,
        *,
        guild_id: int,
        user_id: int,
        session_id: int,
        offline_started_at: int,
    ) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    existing = await conn.fetchrow(
                        """
                        SELECT session_id, offline_started_at, resolved_at
                        FROM session_offline_flags
                        WHERE guild_id = $1 AND user_id = $2
                        FOR UPDATE;
                        """,
                        str(guild_id),
                        str(user_id),
                    )
                    if existing is None:
                        await conn.execute(
                            """
                            INSERT INTO session_offline_flags(
                                guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                            )
                            VALUES($1, $2, $3, $4, NULL, NULL, NULL);
                            """,
                            str(guild_id),
                            str(user_id),
                            int(session_id),
                            int(offline_started_at),
                        )
                        return

                    if existing["resolved_at"] is None and int(existing["session_id"]) == int(session_id):
                        # Existing unresolved marker for the same active session: keep original detection.
                        return

                    await conn.execute(
                        """
                        UPDATE session_offline_flags
                        SET session_id = $1,
                            offline_started_at = $2,
                            prompt_message_id = NULL,
                            prompted_at = NULL,
                            resolved_at = NULL
                        WHERE guild_id = $3 AND user_id = $4;
                        """,
                        int(session_id),
                        int(offline_started_at),
                        str(guild_id),
                        str(user_id),
                    )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute("BEGIN IMMEDIATE;")
        try:
            cur = await self._conn.execute(
                """
                SELECT session_id, offline_started_at, resolved_at
                FROM session_offline_flags
                WHERE guild_id = ? AND user_id = ?;
                """,
                (str(guild_id), str(user_id)),
            )
            existing = await cur.fetchone()
            if existing is None:
                await self._conn.execute(
                    """
                    INSERT INTO session_offline_flags(
                        guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                    )
                    VALUES(?, ?, ?, ?, NULL, NULL, NULL);
                    """,
                    (str(guild_id), str(user_id), int(session_id), int(offline_started_at)),
                )
                await self._conn.commit()
                return

            if existing["resolved_at"] is None and int(existing["session_id"]) == int(session_id):
                await self._conn.commit()
                return

            await self._conn.execute(
                """
                UPDATE session_offline_flags
                SET session_id = ?,
                    offline_started_at = ?,
                    prompt_message_id = NULL,
                    prompted_at = NULL,
                    resolved_at = NULL
                WHERE guild_id = ? AND user_id = ?;
                """,
                (int(session_id), int(offline_started_at), str(guild_id), str(user_id)),
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def mark_session_offline_flag_prompted(
        self,
        *,
        guild_id: int,
        user_id: int,
        session_id: int,
        prompt_message_id: int,
        prompted_at: int,
    ) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE session_offline_flags
                    SET prompt_message_id = $1,
                        prompted_at = $2
                    WHERE guild_id = $3
                      AND user_id = $4
                      AND session_id = $5
                      AND resolved_at IS NULL;
                    """,
                    str(prompt_message_id),
                    int(prompted_at),
                    str(guild_id),
                    str(user_id),
                    int(session_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            UPDATE session_offline_flags
            SET prompt_message_id = ?,
                prompted_at = ?
            WHERE guild_id = ?
              AND user_id = ?
              AND session_id = ?
              AND resolved_at IS NULL;
            """,
            (str(prompt_message_id), int(prompted_at), str(guild_id), str(user_id), int(session_id)),
        )
        await self._conn.commit()

    async def resolve_session_offline_flag(
        self,
        *,
        guild_id: int,
        user_id: int,
        session_id: int,
        resolved_at: int,
    ) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE session_offline_flags
                    SET resolved_at = $1
                    WHERE guild_id = $2
                      AND user_id = $3
                      AND session_id = $4
                      AND resolved_at IS NULL;
                    """,
                    int(resolved_at),
                    str(guild_id),
                    str(user_id),
                    int(session_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            UPDATE session_offline_flags
            SET resolved_at = ?
            WHERE guild_id = ?
              AND user_id = ?
              AND session_id = ?
              AND resolved_at IS NULL;
            """,
            (int(resolved_at), str(guild_id), str(user_id), int(session_id)),
        )
        await self._conn.commit()

    async def list_unresolved_session_offline_flags(self, *, guild_id: int | None = None) -> list[Mapping[str, Any]]:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                if guild_id is None:
                    rows = await conn.fetch(
                        """
                        SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                        FROM session_offline_flags
                        WHERE resolved_at IS NULL;
                        """
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                        FROM session_offline_flags
                        WHERE guild_id = $1
                          AND resolved_at IS NULL;
                        """,
                        str(guild_id),
                    )
                return list(rows)

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        if guild_id is None:
            cur = await self._conn.execute(
                """
                SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                FROM session_offline_flags
                WHERE resolved_at IS NULL;
                """
            )
        else:
            cur = await self._conn.execute(
                """
                SELECT guild_id, user_id, session_id, offline_started_at, prompt_message_id, prompted_at, resolved_at
                FROM session_offline_flags
                WHERE guild_id = ?
                  AND resolved_at IS NULL;
                """,
                (str(guild_id),),
            )
        rows = await cur.fetchall()
        return [self._sqlite_row_to_dict(r) for r in rows]

    async def get_active_session(self, *, guild_id: int, user_id: int) -> Mapping[str, Any] | None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, guild_id, user_id, started_at, ended_at, note
                    FROM sessions
                    WHERE guild_id = $1 AND user_id = $2 AND ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1;
                    """,
                    str(guild_id),
                    str(user_id),
                )
                return row

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            """
            SELECT id, guild_id, user_id, started_at, ended_at, note
            FROM sessions
            WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1;
            """,
            (str(guild_id), str(user_id)),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return self._sqlite_row_to_dict(row)

    async def start_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        started_at: int,
        note: str | None,
    ) -> int:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                new_id = await conn.fetchval(
                    """
                    INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                    VALUES($1, $2, $3, NULL, $4)
                    RETURNING id;
                    """,
                    str(guild_id),
                    str(user_id),
                    int(started_at),
                    note,
                )
                return int(new_id)

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            """
            INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
            VALUES(?, ?, ?, NULL, ?);
            """,
            (str(guild_id), str(user_id), int(started_at), note),
        )
        await self._conn.commit()
        return int(cur.lastrowid)

    async def stop_session(
        self,
        *,
        session_id: int,
        ended_at: int,
    ) -> None:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE sessions
                    SET ended_at = $1
                    WHERE id = $2;
                    """,
                    int(ended_at),
                    int(session_id),
                )
            return

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute(
            """
            UPDATE sessions
            SET ended_at = ?
            WHERE id = ?;
            """,
            (int(ended_at), int(session_id)),
        )
        await self._conn.commit()

    async def replace_user_day_total_seconds(
        self,
        *,
        guild_id: int,
        user_id: int,
        day_start_ts: int,
        day_end_ts: int,
        target_seconds: int,
        note: str | None = None,
    ) -> int:
        day_start_ts = int(day_start_ts)
        day_end_ts = int(day_end_ts)
        target_seconds = int(target_seconds)

        if day_end_ts <= day_start_ts:
            raise ValueError("Invalid day window.")
        day_len = day_end_ts - day_start_ts
        if target_seconds < 0 or target_seconds > day_len:
            raise ValueError(f"target_seconds must be between 0 and {day_len}.")

        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    rows = await conn.fetch(
                        """
                        SELECT id, started_at, ended_at, note
                        FROM sessions
                        WHERE guild_id = $1 AND user_id = $2
                          AND started_at < $3
                          AND (ended_at IS NULL OR ended_at > $4)
                        ORDER BY started_at ASC
                        FOR UPDATE;
                        """,
                        str(guild_id),
                        str(user_id),
                        day_end_ts,
                        day_start_ts,
                    )

                    for row in rows:
                        if row["ended_at"] is None:
                            raise ValueError("Cannot replace a day while an overlapping active session exists.")

                    previous_total = 0
                    for row in rows:
                        s = int(row["started_at"])
                        e = int(row["ended_at"])
                        previous_total += self._overlap_seconds(s, e, day_start_ts, day_end_ts)

                    row_ids = [int(r["id"]) for r in rows]
                    if row_ids:
                        await conn.execute("DELETE FROM sessions WHERE id = ANY($1::bigint[]);", row_ids)

                    for row in rows:
                        s = int(row["started_at"])
                        e = int(row["ended_at"])
                        prev_note = row["note"]
                        if s < day_start_ts:
                            await conn.execute(
                                """
                                INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                                VALUES($1, $2, $3, $4, $5);
                                """,
                                str(guild_id),
                                str(user_id),
                                s,
                                day_start_ts,
                                prev_note,
                            )
                        if e > day_end_ts:
                            await conn.execute(
                                """
                                INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                                VALUES($1, $2, $3, $4, $5);
                                """,
                                str(guild_id),
                                str(user_id),
                                day_end_ts,
                                e,
                                prev_note,
                            )

                    if target_seconds > 0:
                        await conn.execute(
                            """
                            INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                            VALUES($1, $2, $3, $4, $5);
                            """,
                            str(guild_id),
                            str(user_id),
                            day_start_ts,
                            day_start_ts + target_seconds,
                            note,
                        )

                    return int(previous_total)

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        await self._conn.execute("BEGIN IMMEDIATE;")
        try:
            cur = await self._conn.execute(
                """
                SELECT id, started_at, ended_at, note
                FROM sessions
                WHERE guild_id = ? AND user_id = ?
                  AND started_at < ?
                  AND (ended_at IS NULL OR ended_at > ?)
                ORDER BY started_at ASC;
                """,
                (str(guild_id), str(user_id), day_end_ts, day_start_ts),
            )
            rows = await cur.fetchall()

            for row in rows:
                if row["ended_at"] is None:
                    raise ValueError("Cannot replace a day while an overlapping active session exists.")

            previous_total = 0
            for row in rows:
                s = int(row["started_at"])
                e = int(row["ended_at"])
                previous_total += self._overlap_seconds(s, e, day_start_ts, day_end_ts)

            for row in rows:
                await self._conn.execute("DELETE FROM sessions WHERE id = ?;", (int(row["id"]),))
                s = int(row["started_at"])
                e = int(row["ended_at"])
                prev_note = row["note"]
                if s < day_start_ts:
                    await self._conn.execute(
                        """
                        INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                        VALUES(?, ?, ?, ?, ?);
                        """,
                        (str(guild_id), str(user_id), s, day_start_ts, prev_note),
                    )
                if e > day_end_ts:
                    await self._conn.execute(
                        """
                        INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                        VALUES(?, ?, ?, ?, ?);
                        """,
                        (str(guild_id), str(user_id), day_end_ts, e, prev_note),
                    )

            if target_seconds > 0:
                await self._conn.execute(
                    """
                    INSERT INTO sessions(guild_id, user_id, started_at, ended_at, note)
                    VALUES(?, ?, ?, ?, ?);
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        day_start_ts,
                        day_start_ts + target_seconds,
                        note,
                    ),
                )

            await self._conn.commit()
            return int(previous_total)
        except Exception:
            await self._conn.rollback()
            raise

    async def list_sessions_overlapping_window(
        self,
        *,
        guild_id: int,
        user_id: int,
        window_start: int,
        window_end: int,
    ) -> list[Mapping[str, Any]]:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, guild_id, user_id, started_at, ended_at, note
                    FROM sessions
                    WHERE guild_id = $1 AND user_id = $2
                      AND started_at < $3
                      AND (ended_at IS NULL OR ended_at > $4)
                    ORDER BY started_at ASC;
                    """,
                    str(guild_id),
                    str(user_id),
                    int(window_end),
                    int(window_start),
                )
                return list(rows)

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        # A session overlaps [window_start, window_end) if:
        # started_at < window_end AND (ended_at is NULL OR ended_at > window_start)
        cur = await self._conn.execute(
            """
            SELECT id, guild_id, user_id, started_at, ended_at, note
            FROM sessions
            WHERE guild_id = ? AND user_id = ?
              AND started_at < ?
              AND (ended_at IS NULL OR ended_at > ?)
            ORDER BY started_at ASC;
            """,
            (str(guild_id), str(user_id), int(window_end), int(window_start)),
        )
        rows = await cur.fetchall()
        return [self._sqlite_row_to_dict(r) for r in rows]

    async def list_users_with_sessions_in_window(
        self,
        *,
        guild_id: int,
        window_start: int,
        window_end: int,
    ) -> list[int]:
        if self._is_postgres:
            if self._pool is None:
                raise RuntimeError("Database.connect() must be called first.")
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT user_id
                    FROM sessions
                    WHERE guild_id = $1
                      AND started_at < $2
                      AND (ended_at IS NULL OR ended_at > $3);
                    """,
                    str(guild_id),
                    int(window_end),
                    int(window_start),
                )
            return [int(r["user_id"]) for r in rows]

        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first.")

        cur = await self._conn.execute(
            """
            SELECT DISTINCT user_id
            FROM sessions
            WHERE guild_id = ?
              AND started_at < ?
              AND (ended_at IS NULL OR ended_at > ?);
            """,
            (str(guild_id), int(window_end), int(window_start)),
        )
        rows = await cur.fetchall()
        return [int(r["user_id"]) for r in rows]

