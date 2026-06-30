from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.config import Config, load_config
from bot.cogs.time_tracking import TimeTrackingCog
from bot.db import Database
from bot.guild_config import GUILD_CONFIGS

# Ensure all output is visible in Render logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("time-tracker")


class TimeTrackerBot(commands.Bot):
    def __init__(self, *, db: Database, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.config = config

    async def setup_hook(self) -> None:
        log.info("Step 1/5: Connecting to database...")
        await self.db.connect()
        log.info("Step 2/5: Initializing schema...")
        await self.db.init_schema()
        log.info("Step 2/5: Schema ready.")

        log.info("Step 3/5: Loading cog...")
        cog = TimeTrackingCog(
            self,
            self.db,
            default_timezone=self.config.default_timezone,
            default_week_start=self.config.default_week_start,
        )
        await self.add_cog(cog)
        self.add_view(cog.panel_persistent_view)
        log.info("Step 3/5: Cog loaded + persistent view registered.")

        log.info("Step 4/5: Syncing slash commands...")
        clear_guild_ids = set(GUILD_CONFIGS.keys())
        if self.config.dev_guild_id is not None:
            clear_guild_ids.add(int(self.config.dev_guild_id))
        if self.config.clear_guild_commands_id is not None:
            clear_guild_ids.add(int(self.config.clear_guild_commands_id))
        for guild_id in sorted(clear_guild_ids):
            guild = discord.Object(id=guild_id)
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                log.info(f"  Cleared guild commands for {guild_id}.")
            except Exception as exc:
                log.warning(f"  Failed to clear guild commands for {guild_id}: {exc!r}")

        log.info("Step 5/5: Syncing global commands...")
        await self.tree.sync()
        log.info("Setup complete! Bot is ready.")

    async def close(self) -> None:
        try:
            await self.db.close()
        finally:
            await super().close()

    async def on_ready(self) -> None:
        if self.user:
            log.info(f"Logged in as {self.user} (id={self.user.id})")

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        log.exception(f"Unhandled error in event '{event_method}'")
        # Don't call super — prevent the default traceback which might exit.


def main() -> None:
    load_dotenv()
    repo_root = Path(__file__).resolve().parents[1]
    schema_sql_path = str(repo_root / "schema.sql")

    cfg = load_config()
    db_type = "postgres" if cfg.database_url else "sqlite"
    log.info(f"Starting bot: db={db_type}, tz={cfg.default_timezone}, week_start={cfg.default_week_start}")

    db_target = cfg.database_url if cfg.database_url else cfg.db_path
    db = Database(db_target, schema_sql_path=schema_sql_path)
    bot = TimeTrackerBot(db=db, config=cfg)
    try:
        bot.run(cfg.discord_token, log_handler=None)
    except Exception:
        log.exception("Fatal error in bot.run()")
        sys.exit(1)


if __name__ == "__main__":
    main()
