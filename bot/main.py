from __future__ import annotations

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
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    stream=sys.stdout,
)


class TimeTrackerBot(commands.Bot):
    def __init__(self, *, db: Database, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.config = config

    async def setup_hook(self) -> None:
        logging.getLogger(__name__).info("setup_hook: connecting to database...")
        await self.db.connect()
        logging.getLogger(__name__).info("setup_hook: initializing schema...")
        await self.db.init_schema()
        logging.getLogger(__name__).info("setup_hook: schema ready.")

        cog = TimeTrackingCog(
            self,
            self.db,
            default_timezone=self.config.default_timezone,
            default_week_start=self.config.default_week_start,
        )
        await self.add_cog(cog)
        logging.getLogger(__name__).info("setup_hook: cog loaded.")
        # Register persistent button handlers (works for already-posted panel messages).
        self.add_view(cog.panel_persistent_view)
        logging.getLogger(__name__).info("setup_hook: persistent view registered.")

        # Sync slash commands.
        clear_guild_ids = set(GUILD_CONFIGS.keys())
        if self.config.dev_guild_id is not None:
            clear_guild_ids.add(int(self.config.dev_guild_id))
        if self.config.clear_guild_commands_id is not None:
            clear_guild_ids.add(int(self.config.clear_guild_commands_id))
        for guild_id in sorted(clear_guild_ids):
            guild = discord.Object(id=guild_id)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            logging.getLogger(__name__).info(f"setup_hook: cleared guild commands for {guild_id}.")

        await self.tree.sync()
        logging.getLogger(__name__).info("setup_hook: global commands synced. Setup complete.")

    async def close(self) -> None:
        try:
            await self.db.close()
        finally:
            await super().close()

    async def on_ready(self) -> None:
        # on_ready can fire more than once; keep it simple.
        if self.user:
            print(f"Logged in as {self.user} (id={self.user.id})")


def main() -> None:
    # Load .env from repo root.
    load_dotenv()

    # schema.sql is at the repository root.
    repo_root = Path(__file__).resolve().parents[1]
    schema_sql_path = str(repo_root / "schema.sql")

    cfg = load_config()
    logging.getLogger(__name__).info(
        f"Config loaded: db_type={'postgres' if cfg.database_url else 'sqlite'}, "
        f"tz={cfg.default_timezone}, week_start={cfg.default_week_start}"
    )
    db_target = cfg.database_url if cfg.database_url else cfg.db_path
    db = Database(db_target, schema_sql_path=schema_sql_path)
    bot = TimeTrackerBot(db=db, config=cfg)
    try:
        bot.run(cfg.discord_token)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
