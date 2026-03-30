# Discord Time Tracker Bot (Python + SQLite)

Small-team Discord bot for tracking hourly work sessions with weekly totals and optional report-channel posting.
 
## Features     
- `/start [note]` start a work session (one active session per user per server)
- `/stop` stop the active session and show session duration + current week total
- `/status` show whether you're clocked in + elapsed time 
- `/report [user] [week_offset]` weekly total for a specific user (defaults to you) 
- `/leaderboard [week_offset]` weekly totals for everyone with sessions (day/week boundaries are localized to the timezone of the user who runs the command)  
- `/hourly-data [week_offset]` weekly heatmap: per weekday, two rows of 12 blocks (AM hours 0–11, PM 12–23, localized to the timezone of the user who runs the command); uses the same week/report-channel behavior as `/leaderboard`. Each user after the first gets their own embed; users 10+ share the last embed (up to 10 embeds per message)
- `/add-time date minutes` add minutes to your own logged day total (last 7 invoker-local days only) with required public audit message
- `/subtract-time date minutes` subtract minutes from your own logged day total (last 7 invoker-local days only) with required public audit message
- `/set-time date minutes` set your own logged day total exactly (last 7 invoker-local days only) with required public audit message
- `/payment-data` owner-only payout breakdown for the previous week, computed per developer-local week windows with marginal pay brackets
- `/setreportchannel [channel]` (Manage Server/Admin) set the channel to post reports/leaderboards
- `/postpanel` (Manage Server/Admin) post a persistent button panel (Start/Stop/Status) in the current channel
- `/restoreday user week_offset weekday seconds` owner-role-only data restore tool
- Offline-return reminder flow for active sessions: when a clocked-in user goes offline then returns, the bot prompts them in channel `1475250429926572112` to either keep the session running or trim it back to the detected offline timestamp
- Automatic weekly leaderboard announcement (public post with `@everyone`)
- `/testweeklyannouncement` developer-only command to post immediate announcement preview in current channel (no dedupe)

Weekly totals are computed from stored sessions using timezone-aware week windows. Data is kept (no destructive weekly reset); totals naturally \"reset\" when the week window changes.
For private user-triggered outputs (`/start`, `/stop`, `/status`, `/report`, `/leaderboard`, `/hourly-data`, `/add-time`, `/subtract-time`, `/set-time`), time windows use the invoking user's configured **IANA** timezone from `USER_TIMEZONE_BY_ID` in `time_tracking.py` (fallback `UTC`).

`/start`, `/stop`, and `/status` also show **current-week earnings**. Earnings are computed from per-user payment brackets; if a user has no explicit brackets configured in `PAYMENT_BRACKETS_RATE_CENTS_BY_USER`, earnings display as `$0.00`.

## Discord app setup (one-time)
1. Go to https://discord.com/developers/applications and create an application.
2. Add a Bot user, then copy the bot token.
3. Invite the bot to your server:
   - OAuth2 -> URL Generator
   - Scopes: `bot`, `applications.commands`
   - Bot permissions (minimum): `Send Messages`, `Embed Links`, `Read Message History`
   - Privileged Gateway Intents: enable **Server Members Intent** and **Presence Intent** on the Bot page (required for offline-return prompts)
4. Paste the token into your `.env` file as `DISCORD_TOKEN=...`.
   - Do not commit or share your token. 
5. (Optional but recommended for dev) Get your server (guild) ID:
   - Discord User Settings -> Advanced -> Developer Mode (enable)
   - Right-click your server -> Copy Server ID
   - Put it into `DEV_GUILD_ID` in `.env` while developing

## Local setup (Windows PowerShell)
From this repo root:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m bot.main
```

Tip: set `DEV_GUILD_ID` in `.env` while developing so slash commands sync instantly to your server. Global command sync can take longer.

## Configuration
Environment variables (see `.env.example`):
- `DISCORD_TOKEN` (required)
- `DEFAULT_TIMEZONE` (default: `UTC`; see [Weekly totals](#weekly-totals-resets-weekly))
- `DEFAULT_WEEK_START` (default: `0` which is Monday)
- `DEV_GUILD_ID` (optional; speeds up slash command registration)
- `DATABASE_URL` (optional; preferred in production, e.g. Railway Postgres)
- `DB_PATH` (default: `./data/time_tracker.sqlite3`)

## Weekly totals ("resets weekly")

The bot stores raw sessions as UTC timestamps and derives **local days** and **week windows** with Python’s `zoneinfo.ZoneInfo` (IANA timezone database).

**Per-user local time (`USER_TIMEZONE_BY_ID` + `_resolve_user_timezone`)**  
For most behavior—`/start` / `/stop` / `/status`, `/leaderboard`, `/hourly-data`, `/weekly-earnings`, self-serve time edits, owner `/restoreday`, `/payment-data` rows, etc.—the bot picks an IANA name from `USER_TIMEZONE_BY_ID` for that Discord user id, validates it, and runs all “their” week/day math in that zone (including DST). If someone is not in the map, the cog falls back to `DEFAULT_USER_TIMEZONE` (`UTC` in code). Values can still use legacy `UTC±N` labels; those resolve to fixed-offset zones, not civil time with DST.

**Guild week start (`DEFAULT_WEEK_START`)**  
Which weekday opens the week (`0=Monday … 6=Sunday`) comes from guild settings, initially seeded from env `DEFAULT_WEEK_START`. That single setting applies to the whole server for week alignment; it is **not** per-user.

**Env `DEFAULT_TIMEZONE`**  
On first use of a guild, `DEFAULT_TIMEZONE` is stored in `guild_settings.timezone` in the database. The cog does **not** read that column for the slash-command flows above (those use `USER_TIMEZONE_BY_ID`). It remains for consistency and possible future use.

**Automatic weekly `@everyone` announcement (different clock)**  
The scheduled public leaderboard post does **not** use `USER_TIMEZONE_BY_ID` or `DEFAULT_TIMEZONE`. It uses hard-coded `WEEKLY_ANNOUNCEMENT_TIMEZONE` and `WEEKLY_ANNOUNCEMENT_WEEK_START` in `bot/cogs/time_tracking.py`—see [Automatic weekly leaderboard announcement](#automatic-weekly-leaderboard-announcement).

On Windows, the `tzdata` dependency is included so IANA timezones resolve consistently.

Current `USER_TIMEZONE_BY_ID` entries are listed with the [automatic weekly announcement](#automatic-weekly-leaderboard-announcement) section below.

## Hourly activity heatmap (`/hourly-data`)
Each weekday is **three lines** (invoker-local time): **bold** day name, then **12 emoji (0–11)** immediately below, then **12 emoji (12–23)**. A **blank line** separates one day’s PM row from the next day’s name. No Markdown list markers so Discord doesn’t reflow onto one line.

- ⬛ No work, or ≤300 seconds in that hour
- 🟧 More than 300s and less than 1800s
- 🟨 At least 1800s worked in that hour and less than 3600s (and the hour is not fully filled)
- 🟩 At least 3600s worked in that hour, or worked time spans the full length of that hour bucket (including shorter DST hours)

## Manual restore command (owner-only)
Use `/restoreday` to restore historical time after data-loss incidents.

- Allowed caller: members with the configured **owner** role (`ROLE_ID_BY_NAME` in `time_tracking.py`)
- Inputs: target `user`, `week_offset`, `weekday`, and exact `seconds`
- Behavior: replaces that local day total exactly for the target user
  - It removes overlapping portions from existing closed sessions for that day
  - It preserves non-overlapping time outside the day window
  - It inserts one synthetic closed session for the requested amount
- Safety: if an active (open) session overlaps the target day, the command fails instead of mutating data

The command resolves day boundaries using the invoking user's timezone mapping and configured week start, so DST-length days are handled correctly.

## Self-service correction commands
Use `/add-time`, `/subtract-time`, or `/set-time` to correct your own day totals.

- Scope: self-only (no user argument; you can only change your own data)
- Date input: must be one of the last 7 days in your invoker-local timezone (Today + previous 6 days)
- Amount input: `minutes` (not seconds)
- Behavior:
  - `/add-time`: adds minutes to that day
  - `/subtract-time`: subtracts minutes from that day
  - `/set-time`: replaces that day total with an exact minute value
- Safety:
  - command validates day-length limits (DST-safe local day windows)
  - command fails if there is an overlapping active session (same protection as restore)
- Audit requirement:
  - each successful use posts a **public audit embed** in the same channel
  - audit includes user, command, date/timezone, before, after, and signed delta

## Offline-return session prompt
When a user has an active session and their Discord status changes to offline, the bot stores that detection timestamp but does not auto-stop immediately.

- On return to any non-offline status, the bot posts a prompt in channel `1475250429926572112` mentioning the user.
- Prompt options:
  - **Continue session**: keeps the active session unchanged.
  - **Trim to offline timestamp**: closes the current session at the originally detected offline timestamp.
- The prompt is only actionable by the mentioned user.
- If the session is already stopped by the time they return, the offline marker is resolved automatically.

## Payment command (`/payment-data`)
- Visibility: Discord default `Manage Server` hint on the command; runtime allowlist uses `COMMAND_ACCESS_BY_NAME` (owner role only).
- Allowed caller: members with the configured **owner** role.
- Scope: computes **previous week** (`week_offset=-1`) per listed user based on their mapped timezone week window.
- Included users: every Discord user id that appears as a key in `PAYMENT_BRACKETS_RATE_CENTS_BY_USER` (add an entry there to include someone in this report).
- Output shows each person's display name and mention (`@user`) with ID for clarity.
- Rates are configured per user in `bot/cogs/time_tracking.py` via `PAYMENT_BRACKETS_RATE_CENTS_BY_USER`.
  - Default marginal tiers currently set to:
    - 0-10h at $30/hr
    - 10-20h at $33/hr
    - 20-30h at $36/hr
    - 30-40h at $40/hr
    - 40-50h at $45/hr
    - 50h+ at $50/hr

## Automatic weekly leaderboard announcement
The bot automatically posts a weekly leaderboard announcement. Timing uses **`WEEKLY_ANNOUNCEMENT_TIMEZONE`** / **`WEEKLY_ANNOUNCEMENT_WEEK_START`** in `time_tracking.py` (currently a fixed UTC-6–style week boundary), not `USER_TIMEZONE_BY_ID` or `DEFAULT_TIMEZONE`.

- Schedule: at fixed `UTC-6` week rollover (Monday 12:00 AM) for Monday→Sunday weeks
- Channel: `1469817014448029807`
- Mention: pings `@everyone`
- Content: same leaderboard format/content as `/leaderboard`
- Visibility: posted publicly in the channel (not ephemeral)

Per-user IANA timezone mapping (`USER_TIMEZONE_BY_ID`) for command-localized windows:
- `1014149760204156938` (alex) → `Europe/London`
- `434418013916233755` (yandere) → `Europe/Warsaw` (Poland)
- `629991962522681365` (wharkk) → `Europe/Paris` (France)
- `660195981404536832` (wizoo) → `Africa/Cairo` (Egypt)
- `656182155311054858` (maus) → `Asia/Manila` (Philippines)
- `753035328377454612` (BabooCN) → `America/Los_Angeles`
- `761895875361505281` (me) → `America/Chicago` (Saint Louis, Missouri)
- Any unmapped user defaults to `UTC`

The bot stores weekly post markers in the database to avoid duplicate announcements for the same week after restarts.

For testing, use `/testweeklyannouncement` (owner role only):
- Posts immediately in the channel where you run it
- Pings `@everyone`
- Uses the same leaderboard embed format as announcements
- Uses current-week preview and does not write dedupe markers (safe to run repeatedly)

## Data / backups
The bot supports two storage modes:
- PostgreSQL (`DATABASE_URL`) - recommended for hosted environments
- SQLite (`DB_PATH`) - suitable for local/dev or single-host setups with persistent disk

For production hosting, prefer PostgreSQL to avoid container-filesystem data loss on redeploy.

Important for container hosts (Railway/Render/Fly/etc.): app filesystems are typically ephemeral and can be recreated on deploy. If `DB_PATH` points to ephemeral storage, redeploys can look like a full data wipe.

## Hosting (small-team)
Any always-on machine works:
- Linux VPS: run `python -m bot.main` under `systemd` with restart-on-failure, and persist the `data/` directory.
- Windows: run with Task Scheduler (on logon) or a service wrapper like NSSM, and persist the `data/` directory.

### Railway (SQLite persistence)
To keep data across deploys, use a persistent Railway volume:

1. In Railway, open your service and add a **Volume** mounted at `/data`.
2. Set environment variable `DB_PATH=/data/time_tracker.sqlite3`.
3. Redeploy and verify rows persist after the next deploy.

The bot now defaults to `/data/time_tracker.sqlite3` when it detects Railway, but persistence still requires a mounted volume at `/data`.

### Railway (recommended: Postgres, safest)
Use Railway Postgres so data is independent of the app container filesystem:

1. In Railway, add a **Postgres** service to your project.
2. In the bot service variables, set:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
3. Redeploy the bot service.
4. Confirm data survives redeploys by creating a test session, redeploying, then checking `/leaderboard`.

When `DATABASE_URL` is set, the bot uses Postgres and ignores `DB_PATH`.

#### Optional: migrate existing SQLite data to Postgres
If you have data in `./data/time_tracker.sqlite3`, migrate it once:

```powershell
python scripts/migrate_sqlite_to_postgres.py --sqlite-path "./data/time_tracker.sqlite3" --database-url "$env:DATABASE_URL"
```

This migration script truncates destination `sessions` and `guild_settings` before importing, so run it only against the intended Postgres database.

### Example: systemd service (Linux)
Create `/etc/systemd/system/discord-time-tracker.service` (adjust paths/user):
```ini
[Unit]
Description=Discord Time Tracker Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/discord_bot_time_tracker
EnvironmentFile=/opt/discord_bot_time_tracker/.env
ExecStart=/opt/discord_bot_time_tracker/.venv/bin/python -m bot.main
Restart=on-failure
RestartSec=5
User=discordbot

[Install]
WantedBy=multi-user.target
```

### Example: Task Scheduler (Windows)
- Create a basic task that runs at startup (or at logon for a dedicated user).
- Action: start a program
  - Program: `C:\\Users\\YOUR_USER\\Desktop\\workspace\\discord_bot_time_tracker\\.venv\\Scripts\\python.exe`
  - Arguments: `-m bot.main`
  - Start in: `C:\\Users\\YOUR_USER\\Desktop\\workspace\\discord_bot_time_tracker`
- Make sure the task can access your `.env` and the `data/` directory is writable.

## Manual test checklist
- `/start`, wait 1–2 minutes, `/stop` and confirm session duration is correct.
- `/start` twice and confirm the second call refuses.
- Start a session, restart the bot process, then `/stop` and confirm it still closes the active session.
- Set report channel with `/setreportchannel` and run `/report` and `/leaderboard` from another channel; confirm it posts to the configured channel.

