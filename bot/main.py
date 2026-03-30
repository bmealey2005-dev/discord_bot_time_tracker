from __future__ import annotations

from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.config import Config, load_config
from bot.cogs.time_tracking import REQUIRED_COMMAND_ROLE_IDS, TimeTrackingCog
from bot.db import Database


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
        if self.config.dev_guild_id is not None:
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        await self._sync_dev_guild_command_permissions()

    async def _sync_dev_guild_command_permissions(self) -> None:
        if self.config.dev_guild_id is None:
            print("Skipping role-lock command visibility sync: DEV_GUILD_ID is not configured.")
            return

        if self.application_id is None:
            print("Skipping role-lock command visibility sync: application_id is unavailable.")
            return

        guild_id = int(self.config.dev_guild_id)
        guild = discord.Object(id=guild_id)
        try:
            guild_commands = await self.tree.fetch_commands(guild=guild)
        except discord.HTTPException as exc:
            print(f"Failed to fetch guild commands for permission sync: {exc!r}")
            return

        if not guild_commands:
            print(f"No guild commands found for role-lock visibility sync in guild {guild_id}.")
            return

        permissions: list[dict[str, int | bool]] = [
            {
                "id": guild_id,
                "type": int(discord.AppCommandPermissionType.role.value),
                "permission": False,
            }
        ]
        seen_ids = {guild_id}
        for role_id in REQUIRED_COMMAND_ROLE_IDS:
            role_id = int(role_id)
            if role_id in seen_ids:
                continue
            seen_ids.add(role_id)
            permissions.append(
                {
                    "id": role_id,
                    "type": int(discord.AppCommandPermissionType.role.value),
                    "permission": True,
                }
            )

        payload = {"permissions": permissions}
        updated = 0
        for command in guild_commands:
            try:
                await self.http.edit_application_command_permissions(
                    application_id=self.application_id,
                    guild_id=guild_id,
                    command_id=command.id,
                    payload=payload,
                )
                updated += 1
            except discord.HTTPException as exc:
                print(f"Failed to sync command permissions for '{command.name}' ({command.id}): {exc!r}")

        print(
            f"Applied role-lock command visibility permissions to {updated}/{len(guild_commands)} "
            f"guild commands in guild {guild_id}."
        )

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

