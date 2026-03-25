from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, time as dt_time
import time
from typing import Any

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.db import Database
from bot.time_windows import compute_week_window, overlap_seconds

RESTORE_OWNER_USER_ID = 761895875361505281
WEEKDAY_MON_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
WEEKLY_ANNOUNCEMENT_CHANNEL_ID = 1469817014448029807
WEEKLY_ANNOUNCEMENT_TIMEZONE = "America/Chicago"
WEEKLY_ANNOUNCEMENT_WEEK_START = 0  # Monday
WEEKLY_ANNOUNCEMENT_GRACE_SECONDS = 15 * 60


def _format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _dt_from_ts(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _format_hours_minutes(total_seconds: int) -> str:
    """Human-friendly duration for day totals (no seconds)."""
    total_seconds = max(0, int(total_seconds))
    total_minutes = int(round(total_seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0 and minutes == 0:
        return "0h"
    if minutes == 0:
        return f"{hours}h"
    if hours == 0:
        return f"0h {minutes}m"
    return f"{hours}h {minutes}m"


def _format_hourglasses(total_seconds: int, *, max_hours: int = 24) -> str:
    """One hourglass per (full) hour worked, capped for message length safety."""
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds // 3600  # floor to full hours
    if hours <= 0:
        return ""

    max_hours = max(1, int(max_hours))
    shown = min(int(hours), max_hours)
    extra = int(hours) - shown
    s = "⌛" * shown
    if extra > 0:
        s += f" +{extra}h"
    return s


_NICKNAME_HOURS_SUFFIX_RE = re.compile(
    r'(?:\s*\((?: \d{1,4}h(?:\s+\d{1,2}m)? | \d{1,2}m )\))+$',
    re.VERBOSE
)


def _strip_nickname_hours_suffix(name: str) -> str:
    # Only strip our own pattern: "... (12h 30m)" at the end.
    return _NICKNAME_HOURS_SUFFIX_RE.sub("", name).strip()


def _format_week_total_for_nickname(week_total_seconds: int) -> str:
    # Keep it compact; avoid seconds.
    total_minutes = max(0, int(week_total_seconds) // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours <= 0 and minutes <= 0:
        return "0h"
    if hours <= 0:
        return f"{minutes}m"
    if minutes <= 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m" 
 
def _clamp01(x: float) -> float:   
    if x < 0.0:
        return 0.0
    if x > 1.0:  
        return 1.0
    return x


def _progress_bar(pct: float, *, width: int = 12) -> str: 
    pct = _clamp01(float(pct))
    width = max(5, int(width))
    filled = int(round(pct * width))
    filled = max(0, min(width, filled))
    # Emoji blocks render with color in Discord clients.
    # Color shifts as the week approaches its end.
    if pct < 0.50:
        fill = "🟩"
    elif pct < 0.75:
        fill = "🟩"
    elif pct < 0.90:
        fill = "🟩"
    else:
        fill = "🟩"
    empty = "⬛"
    return (fill * filled) + (empty * (width - filled))


def _progress_bar_blue(pct: float, *, width: int = 12) -> str:
    pct = _clamp01(float(pct))
    width = max(5, int(width))
    filled = int(round(pct * width))
    filled = max(0, min(width, filled))
    fill = "🟦"
    empty = "⬛"
    return (fill * filled) + (empty * (width - filled))


def _format_hours_compact(total_seconds: int) -> str:
    """Compact hours for per-day breakdown (no trailing 'h' to save space)."""
    total_seconds = max(0, int(total_seconds))
    hours = total_seconds / 3600.0
    if hours < 0.01:
        return "0"
    if hours < 10:
        s = f"{hours:.1f}"
    else:
        s = f"{hours:.0f}"
    return s.rstrip("0").rstrip(".")



@dataclass(frozen=True)
class WeeklyTotal:
    user_id: int
    total_seconds: int
    session_count: int


@dataclass(frozen=True)
class LeaderboardUserBreakdown:
    user_id: int
    week_total_seconds: int
    day_totals_seconds: list[int]  # length 7, aligned to week window start


class ClockedInActionsView(discord.ui.View):
    """Buttons shown on the 'Clocked in' response message."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(timeout=168 * 60 * 60)
        self.cog = cog

    @discord.ui.button(label="Stop session", style=discord.ButtonStyle.danger)
    async def button_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Edit this "Clocked in" message into a "Clocked out" message,
        # so relative timestamps stop updating.
        await self.cog._handle_stop(interaction, update_invoking_message=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary)
    async def button_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_leaderboard(interaction, week_offset=0)


class ClockedOutActionsView(discord.ui.View):
    """Buttons shown on the 'Clocked out' response message."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(timeout=168 * 60 * 60)
        self.cog = cog

    @discord.ui.button(label="Start session", style=discord.ButtonStyle.success)
    async def button_start(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_start(interaction, note=None)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary)
    async def button_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_leaderboard(interaction, week_offset=0)


class StatusActionsView(discord.ui.View):
    """Buttons shown on the Status response message.

    - If clocked out: Start
    - If clocked in: Stop
    """

    def __init__(self, cog: "TimeTrackingCog", *, clocked_in: bool) -> None:
        super().__init__(timeout=168 * 60 * 60)
        self.cog = cog

        if clocked_in:
            self.add_item(_StopSessionReplaceButton(cog))
        else:
            self.add_item(_StartSessionReplaceButton(cog))
        self.add_item(_LeaderboardReplaceButton(cog))


class _StartSessionReplaceButton(discord.ui.Button):
    """Replaces the Status message with the Start response."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Start session", style=discord.ButtonStyle.success)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_start(interaction, note=None, update_invoking_message=True)


class _StopSessionReplaceButton(discord.ui.Button):
    """Replaces the Status message with the Stop response."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Stop session", style=discord.ButtonStyle.danger)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_stop(interaction, update_invoking_message=True)


class _StatusReplaceButton(discord.ui.Button):
    """Replaces the current message with the Status response."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Status", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_status(interaction, update_invoking_message=True)


class _LeaderboardReplaceButton(discord.ui.Button):
    """Replaces the Status message with the Leaderboard response."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Leaderboard", style=discord.ButtonStyle.primary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_leaderboard(interaction, week_offset=0, update_invoking_message=True)


class _StartSessionButton(discord.ui.Button):
    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Start session", style=discord.ButtonStyle.success)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_start(interaction, note=None)


class _StopSessionButton(discord.ui.Button):
    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Stop session", style=discord.ButtonStyle.danger)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_stop(interaction)


class _StatusButton(discord.ui.Button):
    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Status", style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_status(interaction)


class _LeaderboardButton(discord.ui.Button):
    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(label="Leaderboard", style=discord.ButtonStyle.primary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        await self.cog._handle_leaderboard(interaction, week_offset=0)


class ReportActionsView(discord.ui.View):
    """Buttons shown on the Weekly hours report response message."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(timeout=168 * 60 * 60)
        self.add_item(_LeaderboardButton(cog))


class LeaderboardActionsView(discord.ui.View):
    """Buttons shown on the Weekly hours leaderboard response message."""

    def __init__(self, cog: "TimeTrackingCog", *, clocked_in: bool) -> None:
        super().__init__(timeout=168 * 60 * 60)
        self.cog = cog

        if clocked_in:
            self.add_item(_StopSessionReplaceButton(cog))
        else:
            self.add_item(_StartSessionReplaceButton(cog))
        self.add_item(_StatusReplaceButton(cog))


class TimeTrackerPanelView(discord.ui.View):
    """Persistent control-panel buttons for Start/Stop/Status."""

    def __init__(self, cog: "TimeTrackingCog") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Start session",
        style=discord.ButtonStyle.success,
        custom_id="timetracker:start",
    )
    async def button_start(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_start(interaction, note=None)

    @discord.ui.button(
        label="Stop session",
        style=discord.ButtonStyle.danger,
        custom_id="timetracker:stop",
    )
    async def button_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_stop(interaction)

    @discord.ui.button(
        label="Status",
        style=discord.ButtonStyle.secondary,
        custom_id="timetracker:status",
    )
    async def button_status(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_status(interaction)

    @discord.ui.button(
        label="Leaderboard",
        style=discord.ButtonStyle.primary,
        custom_id="timetracker:leaderboard",
    )
    async def button_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._handle_leaderboard(interaction, week_offset=0)


class TimeTrackingCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        *,
        default_timezone: str,
        default_week_start: int,
    ) -> None:
        self.bot = bot
        self.db = db
        self.default_timezone = default_timezone
        self.default_week_start = default_week_start
        self._panel_persistent_view = TimeTrackerPanelView(self)
        self._weekly_announcement_task: asyncio.Task[None] | None = None

    @property
    def panel_persistent_view(self) -> discord.ui.View:
        # Persistent views must be registered with bot.add_view(...)
        return self._panel_persistent_view

    def make_panel_view(self) -> discord.ui.View:
        # Views can't be reused across multiple messages.
        return TimeTrackerPanelView(self)

    async def cog_load(self) -> None:
        if self._weekly_announcement_task is None or self._weekly_announcement_task.done():
            self._weekly_announcement_task = asyncio.create_task(
                self._weekly_announcement_loop(),
                name="weekly-leaderboard-announcement",
            )

    def cog_unload(self) -> None:
        if self._weekly_announcement_task is not None:
            self._weekly_announcement_task.cancel()
            self._weekly_announcement_task = None

    async def _require_guild(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server (not in DMs).",
                ephemeral=True,
            )
            return False
        return True

    async def _require_manage_server(self, interaction: discord.Interaction) -> bool:
        assert interaction.user is not None
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.administrator):
            await interaction.response.send_message(
                "You need `Manage Server` (or Administrator) to do that.",
                ephemeral=True,
            )
            return False
        return True

    async def _require_restore_owner(self, interaction: discord.Interaction) -> bool:
        assert interaction.user is not None
        if int(interaction.user.id) != RESTORE_OWNER_USER_ID:
            await interaction.response.send_message(
                "You are not allowed to use this command.",
                ephemeral=True,
            )
            return False
        return True

    def _normalize_timezone_input(self, raw: str) -> str:
        tz = raw.strip()
        lower = tz.lower()
        if lower in {"central", "central time", "ct", "cst", "cdt", "us/central"}:
            return "America/Chicago"
        return tz

    def _is_valid_timezone(self, tz_name: str) -> bool:
        try:
            ZoneInfo(tz_name)
            return True
        except ZoneInfoNotFoundError:
            return False

    async def _update_clocked_in_role(self, interaction: discord.Interaction, *, clocked_in: bool) -> str | None:
        """Add/remove the configured clocked-in role for the interacting user.

        Returns a warning string if we attempted and failed; otherwise None.
        """
        if interaction.guild is None or interaction.user is None:
            return None

        settings = await self._get_settings(interaction.guild.id)
        role_id = settings.get("clocked_in_role_id")
        if not role_id:
            return None

        member: discord.Member | None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                except discord.HTTPException:
                    return None

        role = interaction.guild.get_role(int(role_id))
        if role is None:
            return "Configured clocked-in role no longer exists."

        should_have = bool(clocked_in)
        has_role = role in member.roles
        if should_have == has_role:
            return None

        try:
            if should_have:
                await member.add_roles(role, reason="Clocked in")
            else:
                await member.remove_roles(role, reason="Clocked out")
        except discord.Forbidden:
            return "I don't have permission to manage that role (check Manage Roles + role hierarchy)."
        except discord.HTTPException:
            return "Discord API error while updating your role."

        return None

    async def _update_nickname_week_hours(
        self,
        interaction: discord.Interaction,
        *,
        week_total_seconds: int,
    ) -> str | None:
        """Append weekly hours in parentheses to the member's nickname.

        Example: `Name (12h 30m)`. Returns a warning string on failure.
        """
        if interaction.guild is None or interaction.user is None:
            return None

        settings = await self._get_settings(interaction.guild.id)
        if not settings.get("nickname_hours_enabled", True):
            return None

        # Resolve member.
        member: discord.Member | None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            member = interaction.guild.get_member(interaction.user.id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(interaction.user.id)
                except discord.HTTPException:
                    return None

        # Resolve bot member for permission/hierarchy checks.
        me = interaction.guild.get_member(self.bot.user.id) if self.bot.user else None
        if me is None:
            return None

        base = member.nick if member.nick else member.display_name
        base = _strip_nickname_hours_suffix(base)
        suffix = f" ({_format_week_total_for_nickname(week_total_seconds)})"

        # Discord nickname max length is 32 characters.
        max_base_len = 32 - len(suffix)
        if max_base_len < 1:
            return "Nickname too long to append hours."
        if len(base) > max_base_len:
            base = base[:max_base_len].rstrip()
            if not base:
                return "Nickname too long to append hours."

        new_nick = f"{base}{suffix}"
        if member.nick == new_nick:
            return None

        # If we can't update nicknames, still show what we'd set.
        preview = f"Would set nickname to: `{new_nick}`"
        if not me.guild_permissions.manage_nicknames:
            return f"Missing permission: Manage Nicknames. {preview}"
        if interaction.guild.owner_id == member.id:
            return f"Can't change the server owner's nickname. {preview}"
        if me.top_role <= member.top_role:
            return f"Can't change nickname due to role hierarchy. {preview}"

        try:
            await member.edit(nick=new_nick, reason="Update weekly hours display")
        except discord.Forbidden:
            return f"I don't have permission to change that nickname (check role order). {preview}"
        except discord.HTTPException:
            return f"Discord API error while updating nickname. {preview}"

        return None

    async def _get_settings(self, guild_id: int) -> dict[str, Any]:
        await self.db.ensure_guild_settings(
            guild_id=guild_id,
            default_timezone=self.default_timezone,
            default_week_start=self.default_week_start,
        )
        return await self.db.get_guild_settings(guild_id=guild_id)

    async def _compute_weekly_total(
        self,
        *,
        guild_id: int,
        user_id: int,
        week_offset: int,
        now_ts: int,
        tz_name: str,
        week_start: int,
    ) -> WeeklyTotal:
        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=tz_name,
            week_start=week_start,
            week_offset=week_offset,
        )
        rows = await self.db.list_sessions_overlapping_window(
            guild_id=guild_id,
            user_id=user_id,
            window_start=window.start_ts,
            window_end=window.end_ts,
        )

        total = 0
        for r in rows:
            s = int(r["started_at"])
            e = int(r["ended_at"]) if r["ended_at"] is not None else int(now_ts)
            total += overlap_seconds(s, e, window.start_ts, window.end_ts)

        return WeeklyTotal(user_id=user_id, total_seconds=total, session_count=len(rows))

    def _compute_local_day_window(self, *, now_ts: int, tz_name: str) -> tuple[int, int]:
        """Return [start,end) for the current local day in tz_name (DST-safe)."""
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")

        local_now = datetime.fromtimestamp(int(now_ts), tz=timezone.utc).astimezone(tz)
        start_local = datetime.combine(local_now.date(), dt_time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        return int(start_local.timestamp()), int(end_local.timestamp())

    async def _compute_daily_total_seconds(
        self,
        *,
        guild_id: int,
        user_id: int,
        now_ts: int,
        tz_name: str,
    ) -> int:
        day_start_ts, day_end_ts = self._compute_local_day_window(now_ts=now_ts, tz_name=tz_name)
        rows = await self.db.list_sessions_overlapping_window(
            guild_id=guild_id,
            user_id=user_id,
            window_start=day_start_ts,
            window_end=day_end_ts,
        )

        total = 0
        for r in rows:
            s = int(r["started_at"])
            e = int(r["ended_at"]) if r["ended_at"] is not None else int(now_ts)
            total += overlap_seconds(s, e, day_start_ts, day_end_ts)
        return int(total)

    def _format_week_progress(self, *, now_ts: int, window_start: int, window_end: int) -> tuple[str, str]:
        window_len = max(1, int(window_end) - int(window_start))
        week_pct = _clamp01((int(now_ts) - int(window_start)) / window_len)
        progress = f"{_progress_bar(week_pct, width=14)} {int(round(week_pct * 100)):d}%"
        ends = f"Ends {discord.utils.format_dt(_dt_from_ts(int(window_end)), style='R')}"
        return progress, ends

    def _format_day_progress(self, *, now_ts: int, tz_name: str) -> tuple[str, str]:
        """Progress through the current local day in tz_name (DST-safe)."""
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")

        local_now = datetime.fromtimestamp(int(now_ts), tz=timezone.utc).astimezone(tz)
        start_local = datetime.combine(local_now.date(), dt_time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        start_ts = int(start_local.timestamp())
        end_ts = int(end_local.timestamp())

        day_len = max(1, end_ts - start_ts)
        day_pct = _clamp01((int(now_ts) - start_ts) / day_len)
        progress = f"{_progress_bar_blue(day_pct, width=14)} {int(round(day_pct * 100)):d}%"
        ends = f"Ends {discord.utils.format_dt(_dt_from_ts(end_ts), style='R')}"
        return progress, ends

    def _compute_day_windows_for_week(self, *, week_start_ts: int, tz_name: str) -> list[tuple[int, int]]:
        """Return 7 [(start,end)) windows for each local day in the given week.

        Uses local midnights in tz_name so DST weeks are handled correctly.
        """
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")

        start_local = datetime.fromtimestamp(int(week_start_ts), tz=timezone.utc).astimezone(tz)
        start_date = start_local.date()

        stamps: list[int] = []
        for i in range(8):
            dt = datetime.combine(start_date + timedelta(days=i), dt_time.min, tzinfo=tz)
            stamps.append(int(dt.timestamp()))

        return [(stamps[i], stamps[i + 1]) for i in range(7)]

    async def _build_leaderboard_embed(
        self,
        *,
        guild_id: int,
        now_ts: int,
        tz_name: str,
        week_start: int,
        week_offset: int,
    ) -> discord.Embed:
        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=tz_name,
            week_start=int(week_start),
            week_offset=int(week_offset),
        )
        day_windows = self._compute_day_windows_for_week(
            week_start_ts=window.start_ts,
            tz_name=tz_name,
        )

        user_ids = await self.db.list_users_with_sessions_in_window(
            guild_id=int(guild_id),
            window_start=window.start_ts,
            window_end=window.end_ts,
        )
        breakdowns: list[LeaderboardUserBreakdown] = []
        for uid in user_ids:
            rows = await self.db.list_sessions_overlapping_window(
                guild_id=int(guild_id),
                user_id=int(uid),
                window_start=window.start_ts,
                window_end=window.end_ts,
            )
            day_totals = [0] * 7
            for r in rows:
                s = int(r["started_at"])
                e = int(r["ended_at"]) if r["ended_at"] is not None else int(now_ts)
                for di, (ds, de) in enumerate(day_windows):
                    day_totals[di] += overlap_seconds(s, e, ds, de)

            week_total = sum(day_totals)
            breakdowns.append(
                LeaderboardUserBreakdown(
                    user_id=int(uid),
                    week_total_seconds=int(week_total),
                    day_totals_seconds=day_totals,
                )
            )

        breakdowns.sort(key=lambda t: t.week_total_seconds, reverse=True)

        day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        # Rotate labels to match configured week_start (0=Mon..6=Sun).
        ws = int(week_start)
        day_labels = day_labels[ws:] + day_labels[:ws]

        blocks: list[str] = []
        for i, b in enumerate(breakdowns[:25], start=1):
            header = f"{i}. <@{b.user_id}> — {_format_duration(b.week_total_seconds)}"
            day_lines = [
                (
                    f"    - {day_labels[di]}: {_format_hourglasses(b.day_totals_seconds[di])} "
                    f"{_format_hours_minutes(b.day_totals_seconds[di])}"
                ).replace(":  ", ": ")
                for di in range(7)
            ]
            blocks.append("\n".join([header, *day_lines]))

        # Stay within embed description limits.
        joined = ""
        kept = 0
        for block in blocks:
            candidate = (joined + ("\n\n" if joined else "") + block)
            if len(candidate) > 3800:
                break
            joined = candidate
            kept += 1
        if kept < len(blocks):
            joined += f"\n\n… and {len(blocks) - kept} more"

        embed = discord.Embed(title="Weekly hours leaderboard", color=discord.Color.purple())
        embed.add_field(name="Week window", value=f"<t:{window.start_ts}:D> → <t:{window.end_ts - 1}:D>", inline=False)
        week_progress, week_ends = self._format_week_progress(
            now_ts=now_ts,
            window_start=window.start_ts,
            window_end=window.end_ts,
        )
        embed.add_field(name="Week progress", value=f"{week_progress}\n{week_ends}", inline=False)
        day_progress, day_ends = self._format_day_progress(now_ts=now_ts, tz_name=tz_name)
        embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
        embed.description = joined if joined else "No sessions found for this week."
        embed.set_footer(text="Daily bullets show hours per day (week-local).")
        return embed

    async def _maybe_send_weekly_announcement(self) -> None:
        now_ts = int(time.time())
        previous_week = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=WEEKLY_ANNOUNCEMENT_TIMEZONE,
            week_start=WEEKLY_ANNOUNCEMENT_WEEK_START,
            week_offset=-1,
        )

        already_posted = await self.db.has_weekly_leaderboard_post(
            channel_id=WEEKLY_ANNOUNCEMENT_CHANNEL_ID,
            week_start_ts=previous_week.start_ts,
        )
        if already_posted:
            return

        channel = self.bot.get_channel(WEEKLY_ANNOUNCEMENT_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(WEEKLY_ANNOUNCEMENT_CHANNEL_ID)
            except discord.HTTPException:
                print("Weekly leaderboard announcement: failed to fetch target channel.")
                return

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            print("Weekly leaderboard announcement: target channel is not a text channel/thread.")
            return

        embed = await self._build_leaderboard_embed(
            guild_id=channel.guild.id,
            now_ts=now_ts,
            tz_name=WEEKLY_ANNOUNCEMENT_TIMEZONE,
            week_start=WEEKLY_ANNOUNCEMENT_WEEK_START,
            week_offset=-1,
        )
        try:
            await channel.send(
                content="@everyone",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except discord.Forbidden:
            print("Weekly leaderboard announcement: missing permission to post in target channel.")
            return
        except discord.HTTPException:
            print("Weekly leaderboard announcement: Discord API error while posting.")
            return

        await self.db.mark_weekly_leaderboard_post(
            channel_id=WEEKLY_ANNOUNCEMENT_CHANNEL_ID,
            week_start_ts=previous_week.start_ts,
            posted_at_ts=now_ts,
        )

    async def _weekly_announcement_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now_ts = int(time.time())
                current_week = compute_week_window(
                    now=_dt_from_ts(now_ts),
                    tz_name=WEEKLY_ANNOUNCEMENT_TIMEZONE,
                    week_start=WEEKLY_ANNOUNCEMENT_WEEK_START,
                    week_offset=0,
                )

                # If we started shortly after week rollover, do a catch-up post once.
                if (now_ts - int(current_week.start_ts)) <= WEEKLY_ANNOUNCEMENT_GRACE_SECONDS:
                    await self._maybe_send_weekly_announcement()

                # Sleep until the end of the current CT week.
                sleep_for = max(1, int(current_week.end_ts) - int(now_ts))
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Weekly leaderboard announcement loop error: {exc!r}")
                await asyncio.sleep(5)

    async def _maybe_post_to_report_channel(
        self,
        *,
        interaction: discord.Interaction,
        settings: dict[str, Any],
        embed: discord.Embed,
    ) -> discord.abc.MessageableChannel | None:
        channel_id = settings.get("report_channel_id")
        if not channel_id or interaction.guild is None:
            return None

        channel = interaction.guild.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(int(channel_id))
            except discord.HTTPException:
                return None

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None

        try:
            await channel.send(embed=embed)
            return channel
        except discord.Forbidden:
            return None

    async def _handle_start(
        self,
        interaction: discord.Interaction,
        *,
        note: str | None,
        update_invoking_message: bool = False,
    ) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        now_ts = int(time.time())
        active = await self.db.get_active_session(guild_id=interaction.guild.id, user_id=interaction.user.id)
        if active is not None:
            started_at = int(active["started_at"])
            msg = (
                f"You're already clocked in (started {discord.utils.format_dt(_dt_from_ts(started_at), style='R')}).\n"
                "Use `Stop session` to end your current session."
            )
            if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
                await interaction.response.edit_message(content=msg, embed=None, view=ClockedInActionsView(self))
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            await self.db.start_session(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                started_at=now_ts,
                note=note.strip() if note else None,
            )
        except aiosqlite.IntegrityError:
            # Race condition /start fired twice.
            await interaction.response.send_message(
                "You're already clocked in (detected an active session). Use `/stop`.",
                ephemeral=True,
            )
            return

        role_warning = await self._update_clocked_in_role(interaction, clocked_in=True)

        settings = await self._get_settings(interaction.guild.id)
        daily_total = await self._compute_daily_total_seconds(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            now_ts=now_ts,
            tz_name=settings["timezone"],
        )
        weekly_total = await self._compute_weekly_total(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            week_offset=0,
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
        )
        nick_warning = await self._update_nickname_week_hours(
            interaction,
            week_total_seconds=weekly_total.total_seconds,
        )

        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
            week_offset=0,
        )
        week_progress, week_ends = self._format_week_progress(
            now_ts=now_ts,
            window_start=window.start_ts,
            window_end=window.end_ts,
        )
        day_progress, day_ends = self._format_day_progress(now_ts=now_ts, tz_name=settings["timezone"])

        embed = discord.Embed(title="Clocked in", color=discord.Color.green())
        started_dt = _dt_from_ts(now_ts)
        # Relative timestamps ("R") auto-update in the Discord client.
        embed.add_field(
            name="Started",
            value=f"{discord.utils.format_dt(started_dt, style='R')}\n{discord.utils.format_dt(started_dt, style='F')}",
            inline=False,
        )
        embed.add_field(name="Today total", value=_format_duration(daily_total), inline=True)
        embed.add_field(name="This week total", value=_format_duration(weekly_total.total_seconds), inline=True)
        embed.add_field(name="Week progress", value=f"{week_progress}\n{week_ends}", inline=False)
        embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
        if role_warning:
            embed.add_field(name="Role", value=role_warning, inline=False)
        if nick_warning:
            embed.add_field(name="Nickname", value=nick_warning, inline=False)
        if note:
            embed.add_field(name="Note", value=note[:1024], inline=False)
        view = ClockedInActionsView(self)
        if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
            await interaction.response.edit_message(content=None, embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_stop(self, interaction: discord.Interaction, *, update_invoking_message: bool = False) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        now_ts = int(time.time())
        active = await self.db.get_active_session(guild_id=interaction.guild.id, user_id=interaction.user.id)
        if active is None:
            msg = "You're not clocked in. Use `Start session` to begin a session."
            if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
                await interaction.response.edit_message(content=msg, embed=None, view=ClockedOutActionsView(self))
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        started_at = int(active["started_at"])
        await self.db.stop_session(session_id=int(active["id"]), ended_at=now_ts)
        duration = max(0, now_ts - started_at)

        role_warning = await self._update_clocked_in_role(interaction, clocked_in=False)

        settings = await self._get_settings(interaction.guild.id)
        daily_total = await self._compute_daily_total_seconds(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            now_ts=now_ts,
            tz_name=settings["timezone"],
        )
        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
            week_offset=0,
        )
        weekly = await self._compute_weekly_total(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            week_offset=0,
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
        )
        nick_warning = await self._update_nickname_week_hours(
            interaction,
            week_total_seconds=weekly.total_seconds,
        )

        week_progress, week_ends = self._format_week_progress(
            now_ts=now_ts,
            window_start=window.start_ts,
            window_end=window.end_ts,
        )
        day_progress, day_ends = self._format_day_progress(now_ts=now_ts, tz_name=settings["timezone"])

        embed = discord.Embed(title="Clocked out", color=discord.Color.blurple())
        embed.add_field(name="Session duration", value=_format_duration(duration), inline=True)
        embed.add_field(name="Today total", value=_format_duration(daily_total), inline=True)
        embed.add_field(name="This week total", value=_format_duration(weekly.total_seconds), inline=True)
        embed.add_field(name="Week progress", value=f"{week_progress}\n{week_ends}", inline=False)
        embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
        embed.add_field(name="Session start", value=discord.utils.format_dt(_dt_from_ts(started_at), style="F"), inline=True)
        embed.add_field(name="Session end", value=discord.utils.format_dt(_dt_from_ts(now_ts), style="F"), inline=True)
        if role_warning:
            embed.add_field(name="Role", value=role_warning, inline=False)
        if nick_warning:
            embed.add_field(name="Nickname", value=nick_warning, inline=False)
        view = ClockedOutActionsView(self)
        if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=view)
            return

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_status(self, interaction: discord.Interaction, *, update_invoking_message: bool = False) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        now_ts = int(time.time())
        active = await self.db.get_active_session(guild_id=interaction.guild.id, user_id=interaction.user.id)
        role_warning = await self._update_clocked_in_role(interaction, clocked_in=(active is not None))

        settings = await self._get_settings(interaction.guild.id)
        daily_total = await self._compute_daily_total_seconds(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            now_ts=now_ts,
            tz_name=settings["timezone"],
        )
        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
            week_offset=0,
        )
        weekly = await self._compute_weekly_total(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            week_offset=0,
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
        )
        nick_warning = await self._update_nickname_week_hours(
            interaction,
            week_total_seconds=weekly.total_seconds,
        )

        week_progress, week_ends = self._format_week_progress(
            now_ts=now_ts,
            window_start=window.start_ts,
            window_end=window.end_ts,
        )
        day_progress, day_ends = self._format_day_progress(now_ts=now_ts, tz_name=settings["timezone"])

        if active is None:
            embed = discord.Embed(title="Status", color=discord.Color.dark_grey())
            embed.add_field(name="Clocked in", value="No", inline=True)
            embed.add_field(name="Today total", value=_format_duration(daily_total), inline=True)
            embed.add_field(name="This week total", value=_format_duration(weekly.total_seconds), inline=True)
            embed.add_field(name="Week progress", value=f"{week_progress}\n{week_ends}", inline=False)
            embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
            if role_warning:
                embed.add_field(name="Role", value=role_warning, inline=False)
            if nick_warning:
                embed.add_field(name="Nickname", value=nick_warning, inline=False)
            view = StatusActionsView(self, clocked_in=False)
            if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
                await interaction.response.edit_message(content=None, embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        started_at = int(active["started_at"])
        elapsed = max(0, now_ts - started_at)
        embed = discord.Embed(title="Status", color=discord.Color.gold())
        embed.add_field(name="Clocked in", value="Yes", inline=True)
        embed.add_field(name="Elapsed", value=_format_duration(elapsed), inline=True)
        embed.add_field(name="Today total", value=_format_duration(daily_total), inline=True)
        embed.add_field(name="Started", value=discord.utils.format_dt(_dt_from_ts(started_at), style="F"), inline=False)
        embed.add_field(name="This week total", value=_format_duration(weekly.total_seconds), inline=False)
        embed.add_field(name="Week progress", value=f"{week_progress}\n{week_ends}", inline=False)
        embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
        if role_warning:
            embed.add_field(name="Role", value=role_warning, inline=False)
        if nick_warning:
            embed.add_field(name="Nickname", value=nick_warning, inline=False)
        view = StatusActionsView(self, clocked_in=True)
        if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
            await interaction.response.edit_message(content=None, embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_leaderboard(
        self,
        interaction: discord.Interaction,
        *,
        week_offset: int,
        update_invoking_message: bool = False,
    ) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        # Give us time to query DB and (optionally) post in report channel.
        # If we're replacing an existing message (component interaction), don't defer;
        # we'll edit the message directly.
        if not update_invoking_message and not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

        now_ts = int(time.time())
        settings = await self._get_settings(interaction.guild.id)
        embed = await self._build_leaderboard_embed(
            guild_id=interaction.guild.id,
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=int(settings["week_start"]),
            week_offset=int(week_offset),
        )

        active = await self.db.get_active_session(guild_id=interaction.guild.id, user_id=interaction.user.id)
        view = LeaderboardActionsView(self, clocked_in=(active is not None))

        posted_channel = await self._maybe_post_to_report_channel(
            interaction=interaction,
            settings=settings,
            embed=embed,
        )
        content = f"Posted leaderboard in {posted_channel.mention}." if posted_channel is not None else None

        if update_invoking_message and interaction.message is not None and not interaction.response.is_done():
            await interaction.response.edit_message(content=content, embed=embed, view=view)
            return

        if posted_channel is not None:
            await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="start", description="Start a work session timer.")
    @app_commands.describe(note="Optional note about what you're working on")
    async def start(self, interaction: discord.Interaction, note: str | None = None) -> None:
        await self._handle_start(interaction, note=note)

    @app_commands.command(name="stop", description="Stop your current work session timer.")
    async def stop(self, interaction: discord.Interaction) -> None:
        await self._handle_stop(interaction)

    @app_commands.command(name="status", description="See whether you're clocked in and your current timer.")
    async def status(self, interaction: discord.Interaction) -> None:
        await self._handle_status(interaction)

    @app_commands.command(name="report", description="Show weekly hours for a scripter.")
    @app_commands.describe(user="Whose hours to report (defaults to you)", week_offset="0=current week, -1=previous week")
    async def report(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        week_offset: app_commands.Range[int, -52, 52] = 0,
    ) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        target = user or interaction.user
        now_ts = int(time.time())
        settings = await self._get_settings(interaction.guild.id)
        day_progress, day_ends = self._format_day_progress(now_ts=now_ts, tz_name=settings["timezone"])

        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
            week_offset=int(week_offset),
        )
        weekly = await self._compute_weekly_total(
            guild_id=interaction.guild.id,
            user_id=target.id,
            week_offset=int(week_offset),
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=settings["week_start"],
        )

        embed = discord.Embed(
            title="Weekly hours report",
            color=discord.Color.teal(),
        )
        embed.add_field(name="User", value=target.mention, inline=False)
        embed.add_field(name="Week window", value=f"<t:{window.start_ts}:D> → <t:{window.end_ts - 1}:D>", inline=False)
        embed.add_field(name="Day progress", value=f"{day_progress}\n{day_ends}", inline=False)
        embed.add_field(name="Total", value=_format_duration(weekly.total_seconds), inline=True)
        embed.add_field(name="Sessions", value=str(weekly.session_count), inline=True)

        posted_channel = await self._maybe_post_to_report_channel(
            interaction=interaction,
            settings=settings,
            embed=embed,
        )
        if posted_channel is not None:
            await interaction.response.send_message(
                f"Posted report in {posted_channel.mention}.",
                view=ReportActionsView(self),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed, view=ReportActionsView(self), ephemeral=True)

    @app_commands.command(name="leaderboard", description="Show weekly totals for everyone who has sessions.")
    @app_commands.describe(week_offset="0=current week, -1=previous week")
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        week_offset: app_commands.Range[int, -52, 52] = 0,
    ) -> None:
        await self._handle_leaderboard(interaction, week_offset=int(week_offset))

    @app_commands.command(
        name="restoreday",
        description="Owner-only: set a user's worked seconds for one day in a week.",
    )
    @app_commands.describe(
        user="User to restore",
        week_offset="0=current week, -1=previous week",
        weekday="Day name (Monday..Sunday)",
        seconds="Exact total worked seconds for that day",
    )
    @app_commands.choices(
        weekday=[
            app_commands.Choice(name="Monday", value="monday"),
            app_commands.Choice(name="Tuesday", value="tuesday"),
            app_commands.Choice(name="Wednesday", value="wednesday"),
            app_commands.Choice(name="Thursday", value="thursday"),
            app_commands.Choice(name="Friday", value="friday"),
            app_commands.Choice(name="Saturday", value="saturday"),
            app_commands.Choice(name="Sunday", value="sunday"),
        ]
    )
    async def restoreday(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        week_offset: app_commands.Range[int, -52, 52],
        weekday: app_commands.Choice[str],
        seconds: app_commands.Range[int, 0, 172800],
    ) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_restore_owner(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        now_ts = int(time.time())
        settings = await self._get_settings(interaction.guild.id)
        week_start = int(settings["week_start"])

        window = compute_week_window(
            now=_dt_from_ts(now_ts),
            tz_name=settings["timezone"],
            week_start=week_start,
            week_offset=int(week_offset),
        )
        day_windows = self._compute_day_windows_for_week(
            week_start_ts=window.start_ts,
            tz_name=settings["timezone"],
        )

        weekday_key = str(weekday.value).lower()
        weekday_mon_idx = WEEKDAY_MON_INDEX[weekday_key]
        day_idx = (weekday_mon_idx - week_start) % 7
        day_start_ts, day_end_ts = day_windows[day_idx]
        day_len = int(day_end_ts) - int(day_start_ts)

        if int(seconds) > day_len:
            await interaction.response.send_message(
                f"`seconds` must be between 0 and {day_len} for that local day in `{settings['timezone']}`.",
                ephemeral=True,
            )
            return

        synthetic_note = f"manual restore by {interaction.user.id}"
        try:
            previous_seconds = await self.db.replace_user_day_total_seconds(
                guild_id=interaction.guild.id,
                user_id=user.id,
                day_start_ts=day_start_ts,
                day_end_ts=day_end_ts,
                target_seconds=int(seconds),
                note=synthetic_note,
            )
        except ValueError as exc:
            await interaction.response.send_message(
                f"Restore failed: {exc}",
                ephemeral=True,
            )
            return

        weekly = await self._compute_weekly_total(
            guild_id=interaction.guild.id,
            user_id=user.id,
            week_offset=int(week_offset),
            now_ts=now_ts,
            tz_name=settings["timezone"],
            week_start=week_start,
        )

        embed = discord.Embed(
            title="Day restored",
            color=discord.Color.gold(),
        )
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Weekday", value=weekday.name, inline=True)
        embed.add_field(name="Date", value=f"<t:{day_start_ts}:D>", inline=True)
        embed.add_field(
            name="Day total",
            value=(
                f"Previous: {_format_duration(int(previous_seconds))} (`{int(previous_seconds)}s`)\n"
                f"Now: {_format_duration(int(seconds))} (`{int(seconds)}s`)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Week total after restore",
            value=f"{_format_duration(weekly.total_seconds)} (`{weekly.total_seconds}s`)",
            inline=False,
        )
        embed.set_footer(text=f"Timezone: {settings['timezone']} | Week offset: {int(week_offset)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="testweeklyannouncement",
        description="Developer-only: post weekly leaderboard announcement preview in this channel.",
    )
    async def testweeklyannouncement(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_restore_owner(interaction):
            return

        assert interaction.guild is not None
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "This command must be run in a text channel or thread.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        now_ts = int(time.time())
        embed = await self._build_leaderboard_embed(
            guild_id=interaction.guild.id,
            now_ts=now_ts,
            tz_name=WEEKLY_ANNOUNCEMENT_TIMEZONE,
            week_start=WEEKLY_ANNOUNCEMENT_WEEK_START,
            week_offset=0,  # Current-week preview for easier testing.
        )

        try:
            await channel.send(
                content="@everyone",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Failed to post preview: missing permission in this channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Failed to post preview due to a Discord API error.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Posted weekly announcement preview in {channel.mention} (no dedupe written).",
            ephemeral=True,
        )

    @app_commands.command(name="setreportchannel", description="Set (or clear) the channel where reports get posted.")
    @app_commands.describe(channel="Channel to post reports in (omit to clear)")
    async def setreportchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await self._require_guild(interaction):
            return

        assert interaction.guild is not None
        assert interaction.user is not None

        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.administrator):
            await interaction.response.send_message(
                "You need `Manage Server` (or Administrator) to change the report channel.",
                ephemeral=True,
            )
            return

        await self._get_settings(interaction.guild.id)
        await self.db.set_report_channel(guild_id=interaction.guild.id, channel_id=channel.id if channel else None)

        if channel is None:
            await interaction.response.send_message("Report channel cleared. `/report` and `/leaderboard` will respond ephemerally.", ephemeral=True)
            return

        await interaction.response.send_message(f"Report channel set to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="setclockedinrole", description="Set (or clear) the role to apply while users are clocked in.")
    @app_commands.describe(role="Role to add while clocked in (omit to clear)")
    async def setclockedinrole(self, interaction: discord.Interaction, role: discord.Role | None = None) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_manage_server(interaction):
            return

        assert interaction.guild is not None
        await self._get_settings(interaction.guild.id)
        await self.db.set_clocked_in_role(guild_id=interaction.guild.id, role_id=role.id if role else None)

        if role is None:
            await interaction.response.send_message("Clocked-in role cleared.", ephemeral=True)
            return

        await interaction.response.send_message(f"Clocked-in role set to {role.mention}.", ephemeral=True)

    @app_commands.command(name="setnicknamehours", description="Enable/disable showing weekly hours in nicknames.")
    @app_commands.describe(enabled="If enabled, nicknames become like: Name (12h 30m)")
    async def setnicknamehours(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_manage_server(interaction):
            return

        assert interaction.guild is not None
        await self._get_settings(interaction.guild.id)
        await self.db.set_nickname_hours_enabled(guild_id=interaction.guild.id, enabled=bool(enabled))

        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Nickname weekly-hours display {state}.", ephemeral=True)

    @app_commands.command(name="settimezone", description="Set the timezone used for weekly boundaries (week begin/end).")
    @app_commands.describe(timezone="IANA timezone, e.g. America/Chicago (Central Time)")
    async def settimezone(self, interaction: discord.Interaction, timezone: str) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_manage_server(interaction):
            return

        assert interaction.guild is not None

        tz_name = self._normalize_timezone_input(timezone)
        if not self._is_valid_timezone(tz_name):
            await interaction.response.send_message(
                "Invalid timezone. Use an IANA timezone like `America/Chicago`.\n"
                "Examples: `UTC`, `America/Los_Angeles`, `America/Chicago`, `Europe/London`.",
                ephemeral=True,
            )
            return

        await self._get_settings(interaction.guild.id)
        await self.db.set_timezone(guild_id=interaction.guild.id, timezone=tz_name)
        await interaction.response.send_message(f"Timezone set to `{tz_name}`.", ephemeral=True)

    @app_commands.command(name="postpanel", description="Post a persistent Start/Stop/Status button panel in this channel.")
    async def postpanel(self, interaction: discord.Interaction) -> None:
        if not await self._require_guild(interaction):
            return
        if not await self._require_manage_server(interaction):
            return

        assert interaction.guild is not None

        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("This command must be run in a text channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        embed = discord.Embed(
            title="Time Tracker",
            description="Use the buttons below to start/stop a work session, or check your status.\n"
            "Slash commands still work: `/start`, `/stop`, `/status`.",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Buttons are persistent (they keep working after bot restarts).")

        panel_message = await channel.send(embed=embed, view=self.make_panel_view())
        await self._get_settings(interaction.guild.id)
        await self.db.set_panel_message(
            guild_id=interaction.guild.id,
            channel_id=panel_message.channel.id,
            message_id=panel_message.id,
        )

        await interaction.followup.send(f"Posted the time tracker panel in {channel.mention}.", ephemeral=True)

