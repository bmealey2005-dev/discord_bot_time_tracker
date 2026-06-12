from __future__ import annotations

from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.config import Config, load_config
from bot.cogs.time_tracking import TimeTrackingCog
from bot.db import Database
from bot.guild_config import GUILD_CONFIGS


class TimeTrackerBot(commands.Bot):
    def __init__(self, *, db: Database, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.config = config

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init_schema()

        cog = TimeTrackingCog(
            self,
            self.db,
            default_timezone=self.config.default_timezone,
            default_week_start=self.config.default_week_start,
        )
        await self.add_cog(cog)
        # Register persistent button handlers (works for already-posted panel messages).
        self.add_view(cog.panel_persistent_view)

        # Sync slash commands.
        if self.config.clear_guild_commands_id is not None:
            # One-time cleanup: remove guild-specific commands (fixes duplicates).
            guild = discord.Object(id=self.config.clear_guild_commands_id)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)

        # Copy global commands into every configured guild for instant availability.
        # NOTE: Discord does not allow bot tokens to edit per-command role
        # permissions (error 20001), so command *visibility* is managed in each
        # server via Server Settings -> Integrations -> this app -> Commands.
        # Actual access is enforced at runtime by _require_command_access.
        sync_guild_ids = set(GUILD_CONFIGS.keys())
        if self.config.dev_guild_id is not None:
            sync_guild_ids.add(int(self.config.dev_guild_id))
        if sync_guild_ids:
            for guild_id in sorted(sync_guild_ids):
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

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
    db_target = cfg.database_url if cfg.database_url else cfg.db_path
    db = Database(db_target, schema_sql_path=schema_sql_path)
    bot = TimeTrackerBot(db=db, config=cfg)
    bot.run(cfg.discord_token)


if __name__ == "__main__":
    main()

