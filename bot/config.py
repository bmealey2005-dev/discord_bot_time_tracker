from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    discord_token: str
    default_timezone: str
    default_week_start: int
    dev_guild_id: int | None
    clear_guild_commands_id: int | None
    database_url: str | None
    db_path: str


def _parse_int(name: str, raw: str | None, *, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid int for {name}: {raw!r}") from exc


def _parse_optional_int(name: str, raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid int for {name}: {raw!r}") from exc


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required (set it in your .env).")

    default_timezone = os.getenv("DEFAULT_TIMEZONE", "UTC").strip() or "UTC"
    default_week_start = _parse_int(
        "DEFAULT_WEEK_START",
        os.getenv("DEFAULT_WEEK_START"),
        default=0,
    )
    if default_week_start < 0 or default_week_start > 6:
        raise ValueError("DEFAULT_WEEK_START must be between 0 (Mon) and 6 (Sun).")

    dev_guild_id = _parse_optional_int("DEV_GUILD_ID", os.getenv("DEV_GUILD_ID"))
    clear_guild_commands_id = _parse_optional_int(
        "CLEAR_GUILD_COMMANDS_ID", os.getenv("CLEAR_GUILD_COMMANDS_ID")
    )
    database_url = os.getenv("DATABASE_URL", "").strip() or None
    default_db_path = "./data/time_tracker.sqlite3"
    db_path = os.getenv("DB_PATH", default_db_path).strip() or default_db_path

    return Config(
        discord_token=token,
        default_timezone=default_timezone,
        default_week_start=default_week_start,
        dev_guild_id=dev_guild_id,
        clear_guild_commands_id=clear_guild_commands_id,
        database_url=database_url,
        db_path=db_path,
    )

