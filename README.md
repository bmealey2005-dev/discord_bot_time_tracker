# Discord Time Tracker Bot (Python + SQLite)

Small-team Discord bot for tracking hourly work sessions with weekly totals and optional report-channel posting.

## Features
- `/start [note]` start a work session (one active session per user per server)
- `/stop` stop the active session and show session duration + current week total
- `/status` show whether you're clocked in + elapsed time 
- `/report [user] [week_offset]` weekly total for a specific user (defaults to you) 
- `/leaderboard [week_offset]` weekly totals for everyone with sessions
- `/hourly-data [week_offset]` weekly heatmap: 24 blocks per day (guild-local hours 0–23) per user; uses the same week and report-channel behavior as `/leaderboard`
- `/setreportchannel [channel]` (Manage Server/Admin) set the channel to post reports/leaderboards
- `/postpanel` (Manage Server/Admin) post a persistent button panel (Start/Stop/Status) in the current channel
- `/restoreday user week_offset weekday seconds` owner-only data restore tool (user id `761895875361505281`)
- Automatic weekly leaderboard announcement (public post with `@everyone`)
- `/testweeklyannouncement` developer-only command to post immediate announcement preview in current channel (no dedupe)

Weekly totals are computed from stored sessions using a timezone-aware week window. Data is kept (no destructive weekly reset); totals naturally \"reset\" when the week window changes.

## Discord app setup (one-time)
1. Go to https://discord.com/developers/applications and create an application.
2. Add a Bot user, then copy the bot token.
3. Invite the bot to your server:
   - OAuth2 -> URL Generator
   - Scopes: `bot`, `applications.commands`
   - Bot permissions (minimum): `Send Messages`, `Embed Links`, `Read Message History`
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
- `DEFAULT_TIMEZONE` (default: `America/Chicago`)
- `DEFAULT_WEEK_START` (default: `0` which is Monday)
- `DEV_GUILD_ID` (optional; speeds up slash command registration)
- `DATABASE_URL` (optional; preferred in production, e.g. Railway Postgres)
- `DB_PATH` (default: `./data/time_tracker.sqlite3`)

## Weekly totals ("resets weekly") 
The bot stores raw sessions (start/end timestamps) and computes totals based on a week window:
- `DEFAULT_TIMEZONE` uses an IANA name like `UTC` or `America/Los_Angeles`
- `DEFAULT_WEEK_START`: `0=Mon .. 6=Sun`

You can also set the timezone per server with `/settimezone` (recommended once you deploy).

On Windows, the `tzdata` dependency is included so IANA timezones work consistently.

## Hourly activity heatmap (`/hourly-data`)
Each weekday line is 24 emoji in order for local hours 0–23 (guild timezone):

- ⬛ No work, or ≤300 seconds in that hour
- 🟧 More than 300s and less than 1800s
- 🟨 At least 1800s worked in that hour and less than 3600s (and the hour is not fully filled)
- 🟩 At least 3600s worked in that hour, or worked time spans the full length of that hour bucket (including shorter DST hours)

## Manual restore command (owner-only)
Use `/restoreday` to restore historical time after data-loss incidents.

- Allowed caller: only Discord user id `761895875361505281`
- Inputs: target `user`, `week_offset`, `weekday`, and exact `seconds`
- Behavior: replaces that local day total exactly for the target user
  - It removes overlapping portions from existing closed sessions for that day
  - It preserves non-overlapping time outside the day window
  - It inserts one synthetic closed session for the requested amount
- Safety: if an active (open) session overlaps the target day, the command fails instead of mutating data

The command resolves day boundaries using the guild timezone and configured week start, so DST-length days are handled correctly.

## Automatic weekly leaderboard announcement
The bot automatically posts a weekly leaderboard announcement:

- Schedule: at CT week rollover (Monday 12:00 AM) for Monday→Sunday weeks
- Channel: `1469817014448029807`
- Mention: pings `@everyone`
- Content: same leaderboard format/content as `/leaderboard`
- Visibility: posted publicly in the channel (not ephemeral)

The bot stores weekly post markers in the database to avoid duplicate announcements for the same week after restarts.

For testing, use `/testweeklyannouncement` (developer-only for user id `761895875361505281`):
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

