# Multi-Server Support Plan

Goal: run this time-tracking bot in **two Discord servers** (the existing server plus a new one with a separate dev team), each with its own employees, roles, channels, permissions, timezones, pay brackets, and time-tracking data — without breaking the current server.

---

## 1. Where the codebase stands today

### Already multi-server safe (no changes needed)

The database layer is **already keyed by `guild_id`**:

- `sessions`, `guild_settings`, offline-flag tables, and weekly-post markers in `bot/db.py` all take `guild_id` parameters (`get_active_session`, `start_session`, `list_sessions_overlapping_window`, `ensure_guild_settings`, etc.).
- `weekly_leaderboard_posts` is keyed by `(channel_id, week_start_ts)`, which is naturally per-server since channels belong to one guild.

This means **time-tracking data is already isolated per server**. A user clocking in on Server A writes rows with Server A's guild id; Server B queries will never see them.

### Single-server assumptions (the actual problem)

All of these are **module-level constants** in `bot/cogs/time_tracking.py` that bake in Server A's IDs:

| Constant | What it hardcodes | Used by |
|---|---|---|
| `USER_ID_BY_USERNAME` | Server A employee user IDs | payment brackets, timezones |
| `CHANNEL_ID_BY_NAME` | `general`, `time-logging`, `announcements`, `private` channel IDs | audit posts, offline prompts, weekly announcement |
| `ROLE_ID_BY_NAME` | `owner`, `admin`, `ui-artists`, `ugc-creators` role IDs | every permission check, command visibility sync |
| `COMMAND_ACCESS_BY_NAME` | role *names* per command (names resolve through `ROLE_ID_BY_NAME`) | `_require_command_access`, `bot/main.py` sync |
| `USER_TIMEZONE_BY_ID` | per-employee IANA timezones | all week/day window math, announcement scheduling |
| `PAYMENT_BRACKETS_RATE_CENTS_BY_USER` | per-employee pay rates | `/payment-data`, `/weekly-earnings`, status embeds |
| `DEFAULT_CLOCKED_IN_ROLE_ID` | Server A clocked-in role | seeded into `guild_settings` |

And two flows that iterate a single server:

- **Weekly announcement loop** (`_weekly_announcement_loop` / `_maybe_send_weekly_announcement`): posts to the one `CHANNEL_ID_BY_NAME["announcements"]` channel and computes rollover from the one global `USER_TIMEZONE_BY_ID`.
- **Command visibility sync** (`bot/main.py::_sync_dev_guild_command_permissions`): syncs role-locked command permissions only for `DEV_GUILD_ID`, using the one global `ROLE_ID_BY_NAME`.

---

## 2. Highest-ROI design: a per-guild config registry

The cheapest change that solves everything: **wrap every hardcoded constant in one `GuildConfig` object, stored in a dict keyed by guild id.** No database migration is needed for configuration — these values are developer-maintained today and can stay in code; they just need to be looked up per guild instead of globally.

### New module: `bot/guild_config.py`

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class GuildConfig:
    guild_id: int
    role_id_by_name: dict[str, int]                 # owner/admin/teams -> role id
    channel_id_by_name: dict[str, int]              # general / time-logging / announcements
    command_access_by_name: dict[str, frozenset[str]]
    user_timezone_by_id: dict[int, str]             # employee id -> IANA tz
    payment_brackets_by_user: dict[int, tuple[tuple[int, int], ...]]
    clocked_in_role_id: int | None = None
    week_start: int = 0                             # 0=Monday
    announcement_grace_seconds: int = 15 * 60

SERVER_A_GUILD_ID = 0  # existing server's guild id
SERVER_B_GUILD_ID = 0  # new server's guild id

GUILD_CONFIGS: dict[int, GuildConfig] = {
    # Server A (existing): move current constants here verbatim
    SERVER_A_GUILD_ID: GuildConfig(...),
    # Server B (new team): new IDs, new roster
    SERVER_B_GUILD_ID: GuildConfig(...),
}

def get_guild_config(guild_id: int) -> GuildConfig | None:
    return GUILD_CONFIGS.get(int(guild_id))
```

Key properties of this design:

- **Unknown guilds are rejected.** If the bot is added to a third server, `get_guild_config` returns `None` and every command/loop politely refuses. No accidental data or pings.
- **Role *names* stay shared, role *IDs* differ.** `COMMAND_ACCESS_BY_NAME` can remain a shared default (both servers use owner/admin/team-role semantics) with an optional per-guild override; each guild maps those names to its own role IDs.
- **Per-guild validation at startup** replaces the current module-level asserts: every role name referenced by `command_access_by_name` must exist in that guild's `role_id_by_name`.

### Why not move config to the database?

Could be done later (slash commands to edit rosters), but it is *not* the highest-ROI first step: the data changes rarely, is owner-maintained, and code-as-config keeps the diff small and reviewable. The DB already handles the data that actually grows (sessions). Revisit if a third+ server or non-developer admins appear.

---

## 3. Code changes (file by file)

### `bot/cogs/time_tracking.py` (the bulk of the work)

1. **Delete the global constants** (`USER_ID_BY_USERNAME` references in brackets/timezones, `CHANNEL_ID_BY_NAME`, `ROLE_ID_BY_NAME`, `COMMAND_ACCESS_BY_NAME` as a global, `USER_TIMEZONE_BY_ID`, `PAYMENT_BRACKETS_RATE_CENTS_BY_USER`, `DEFAULT_CLOCKED_IN_ROLE_ID`) and import from `bot/guild_config.py` instead.
2. **Add a guard helper** used at the top of every handler (alongside `_require_guild`):
   - `_get_config_or_reject(interaction) -> GuildConfig | None` — resolves config for `interaction.guild.id`, sends "This bot is not configured for this server." if missing.
3. **Thread the config through permission checks:**
   - `_role_ids_for_allowed_names(cfg, names)`, `_member_has_roles_for_command(cfg, member, guild, command_name)`, `_require_command_access(interaction, command_name)` look up `cfg = get_guild_config(...)` instead of module globals.
4. **Thread the config through channel lookups:**
   - Audit posts (`_handle_self_time_adjustment`) → `cfg.channel_id_by_name["general"]`.
   - Offline prompts (`_get_offline_return_prompt_channel`) → `cfg.channel_id_by_name["time-logging"]`.
   - Announcements → `cfg.channel_id_by_name["announcements"]`.
5. **Timezones and pay become per-guild:**
   - `_resolve_user_timezone(guild_id, user_id)` reads `cfg.user_timezone_by_id`.
   - `_payment_brackets_for_user(guild_id, user_id)` reads `cfg.payment_brackets_by_user`; `/payment-data` iterates that guild's dict only.
6. **Weekly announcement loop becomes a per-guild loop:**
   - `_weekly_announcement_loop` iterates `GUILD_CONFIGS`; for each guild, compute `AnnouncementCycleState` from **that guild's** `user_timezone_by_id`, post to **that guild's** announcements channel, and dedupe per channel (already supported by the `(channel_id, week_start_ts)` key — no schema change).
   - Sleep until the **soonest** next-check timestamp across all guilds.
7. **Presence/offline handlers:** `on_presence_update` already receives a `Member` with a guild; just guard with `get_guild_config(member.guild.id)` so unconfigured servers are ignored.

### `bot/main.py`

- Replace the single `DEV_GUILD_ID` permission sync with a loop over `GUILD_CONFIGS`: for each configured guild, copy global commands to the guild and apply role-locked visibility using that guild's `role_id_by_name` + `command_access_by_name`.
- Keep `DEV_GUILD_ID` env var as an optional *additional* fast-sync target during development, or retire it in favor of the registry.

### `bot/config.py` / `.env`

- No new required env vars. Guild registry lives in code. Optionally add `ENABLED_GUILD_IDS` as a safety allowlist if you want env-level control over which configured guilds are active per deployment.

### `bot/db.py` / `schema.sql`

- **No schema changes required.** Verify only:
  - `guild_settings` rows seed correctly for the new guild on first use (`ensure_guild_settings` already handles this; pass `cfg.clocked_in_role_id` instead of the global default).
  - `weekly_leaderboard_posts` dedupe works unchanged because Server B posts to a different channel id.

---

## 4. Migration steps (zero downtime for Server A)

1. **Refactor, no behavior change:** create `bot/guild_config.py` containing exactly one entry — Server A with today's constants. Replace all global lookups with `get_guild_config(...)`. Deploy. Server A behaves identically (same IDs, same checks); this is verifiable with `python -m py_compile` plus a live smoke test of `/start`, `/stop`, `/leaderboard`, an audit post, and `/testweeklyannouncement`.
2. **Gather Server B IDs:** guild id, role ids (owner/admin/teams as appropriate for that team), channel ids (general/time-logging/announcements), employee user ids, timezones, pay brackets, clocked-in role.
3. **Add the Server B `GuildConfig` entry** and invite the bot (scopes: `bot`, `applications.commands`; same intents: members + presences).
4. **First-run checks on Server B:**
   - `guild_settings` row auto-seeds with Server B's week start / clocked-in role.
   - Command visibility sync applies Server B role locks.
   - Run `/postpanel` in Server B's panel channel; verify offline prompt and audit channels with a test session.
5. **Watch the announcement cycle** for one week: each guild should post once in its own announcements channel at its own roster's rollover, with dedupe rows keyed to different channel ids.

Rollback at any step = redeploy previous commit; no data migration to undo.

---

## 5. Risks and edge cases

- **A user in both servers** (e.g. you as owner): sessions are separate per guild by design; timezones/pay can intentionally differ per guild since they live in each `GuildConfig`.
- **Panel buttons / persistent views:** callbacks resolve guild from the interaction, so they inherit per-guild config automatically once handlers are threaded.
- **Unconfigured guild safety:** every entry point (commands, buttons, presence events, loops) must hit the `get_guild_config` guard — this is the main review checklist item for the refactor PR.
- **Announcement loop fan-out:** failures in one guild's post must not break the other's (wrap each guild's attempt in its own try/except, as the loop already does for the whole body).

## 6. Suggested implementation order (each step shippable)

1. `bot/guild_config.py` + Server A entry + mechanical lookup refactor (largest diff, zero behavior change).
2. Per-guild permission sync in `bot/main.py`.
3. Per-guild announcement loop.
4. Add Server B entry + invite + smoke test.
