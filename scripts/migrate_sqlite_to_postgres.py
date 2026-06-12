from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sqlite3

import asyncpg

from bot.db import Database


def _read_sqlite_rows(
    sqlite_path: Path,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row]]:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        guild_settings = conn.execute(
            """
            SELECT guild_id, report_channel_id, panel_channel_id, panel_message_id, clocked_in_role_id,
                   nickname_hours_enabled, timezone, week_start
            FROM guild_settings;
            """
        ).fetchall()
        sessions = conn.execute(
            """
            SELECT id, guild_id, user_id, started_at, ended_at, note
            FROM sessions
            ORDER BY id ASC;
            """
        ).fetchall()
        weekly_leaderboard_posts = conn.execute(
            """
            SELECT channel_id, week_start_ts, posted_at_ts
            FROM weekly_leaderboard_posts;
            """
        ).fetchall()
        session_offline_flags = conn.execute(
            """
            SELECT guild_id, user_id, session_id, offline_started_at,
                   prompt_message_id, prompted_at, resolved_at
            FROM session_offline_flags;
            """
        ).fetchall()
        return guild_settings, sessions, weekly_leaderboard_posts, session_offline_flags
    finally:
        conn.close()


async def _ensure_postgres_schema(database_url: str, schema_sql_path: Path) -> None:
    db = Database(database_url, schema_sql_path=str(schema_sql_path))
    await db.connect()
    try:
        await db.init_schema()
    finally:
        await db.close()


async def _migrate(sqlite_path: Path, database_url: str, schema_sql_path: Path) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    guild_settings, sessions, weekly_leaderboard_posts, session_offline_flags = _read_sqlite_rows(sqlite_path)
    await _ensure_postgres_schema(database_url, schema_sql_path)

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3, command_timeout=60)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("TRUNCATE TABLE sessions, guild_settings, weekly_leaderboard_posts, session_offline_flags RESTART IDENTITY;")

                for row in guild_settings:
                    await conn.execute(
                        """
                        INSERT INTO guild_settings(
                            guild_id, report_channel_id, panel_channel_id, panel_message_id, clocked_in_role_id,
                            nickname_hours_enabled, timezone, week_start
                        )
                        VALUES($1, $2, $3, $4, $5, $6, $7, $8);
                        """,
                        row["guild_id"],
                        row["report_channel_id"],
                        row["panel_channel_id"],
                        row["panel_message_id"],
                        row["clocked_in_role_id"],
                        int(row["nickname_hours_enabled"]) if row["nickname_hours_enabled"] is not None else 1,
                        row["timezone"],
                        int(row["week_start"]),
                    )

                for row in sessions:
                    await conn.execute(
                        """
                        INSERT INTO sessions(id, guild_id, user_id, started_at, ended_at, note)
                        VALUES($1, $2, $3, $4, $5, $6);
                        """,
                        int(row["id"]),
                        row["guild_id"],
                        row["user_id"],
                        int(row["started_at"]),
                        int(row["ended_at"]) if row["ended_at"] is not None else None,
                        row["note"],
                    )

                await conn.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('sessions', 'id'),
                        COALESCE((SELECT MAX(id) FROM sessions), 1),
                        true
                    );
                    """
                )

                for row in weekly_leaderboard_posts:
                    await conn.execute(
                        """
                        INSERT INTO weekly_leaderboard_posts(channel_id, week_start_ts, posted_at_ts)
                        VALUES($1, $2, $3);
                        """,
                        row["channel_id"],
                        int(row["week_start_ts"]),
                        int(row["posted_at_ts"]),
                    )

                for row in session_offline_flags:
                    await conn.execute(
                        """
                        INSERT INTO session_offline_flags(
                            guild_id, user_id, session_id, offline_started_at,
                            offline_accumulated_seconds, offline_open_started_at,
                            prompt_message_id, prompted_at, resolved_at
                        )
                        VALUES($1, $2, $3, $4, 0, NULL, $5, $6, $7);
                        """,
                        row["guild_id"],
                        row["user_id"],
                        int(row["session_id"]),
                        int(row["offline_started_at"]),
                        row["prompt_message_id"],
                        int(row["prompted_at"]) if row["prompted_at"] is not None else None,
                        int(row["resolved_at"]) if row["resolved_at"] is not None else None,
                    )
    finally:
        await pool.close()

    print(f"Migrated {len(guild_settings)} guild_settings, {len(sessions)} sessions, {len(weekly_leaderboard_posts)} weekly_leaderboard_posts, {len(session_offline_flags)} session_offline_flags.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLite data into PostgreSQL.")
    parser.add_argument(
        "--sqlite-path",
        default="./data/time_tracker.sqlite3",
        help="Path to the source SQLite DB (default: ./data/time_tracker.sqlite3)",
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="Destination PostgreSQL URL (e.g. Railway Postgres DATABASE_URL)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[1]
    schema_sql_path = repo_root / "schema.sql"
    asyncio.run(_migrate(sqlite_path, args.database_url, schema_sql_path))


if __name__ == "__main__":
    main()
