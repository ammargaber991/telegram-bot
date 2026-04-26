# Design Lab Telegram Bot

A production-style Telegram bot scaffold with:

- Rank-based access control
- Command permissions and moderation tools
- Hidden developer-only commands
- Persistent audit logging to SQLite
- Consistent **Design Lab** branding

## Features

### Rank system
Users are assigned one of these ranks:

1. `owner`
2. `developer`
3. `admin`
4. `moderator`
5. `user`

Higher ranks inherit all lower-rank command access.

### Permissions
Every command has a required minimum rank. The bot enforces this centrally through a permission gate.

### Hidden developer commands
Developer commands are intentionally omitted from normal help output and command menus.

### Logging
Two logging layers:

- Structured application logs (stdout/file)
- Persistent audit trail in SQLite (`audit_logs` table)

### Branding
Messages and help output are branded with **Design Lab** language and style.

## Quick start

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy token.
2. Create environment file:

```bash
cp .env.example .env
```

3. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Run bot:

> *Use either `OWNER_TELEGRAM_ID` or `OWNER_ID` for owner configuration.*


```bash
python -m bot.main
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes | Telegram bot token |
| `OWNER_TELEGRAM_ID` | Yes* | Telegram numeric ID treated as `owner` |
| `OWNER_ID` | Yes* | Backward-compatible alias for owner ID |
| `DATABASE_PATH` | No | SQLite file path (default: `./design_lab_bot.db`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

## Core commands

Visible commands:

- `/start` – onboarding and branding intro
- `/help` – command help by rank
- `/rank` – show your rank
- `/whois <user_id>` – inspect user profile and rank (`moderator+`)
- `/promote <user_id> <rank>` – set user rank (`admin+`)
- `/demote <user_id>` – demote to `user` (`admin+`)
- `/logs [limit]` – show latest audit actions (`developer+`)
- `/broadcast <message>` – broadcast to all known users (`admin+`)
- `/dl_status` – Design Lab operational status (`moderator+`)

Hidden commands:

- `/dev_stats` – internal user/log statistics (`developer+`)
- `/dev_note <text>` – write internal developer note to audit log (`developer+`)

## Security notes

- Avoid adding arbitrary eval/shell commands.
- Keep hidden commands developer-only.
- Audit all privilege-changing actions (`promote`, `demote`).

## License

MIT (or your preferred internal license).

## Troubleshooting

- If startup fails with network errors:
  - this bot disables env proxy usage by default for Telegram API stability
  - verify outbound access to `https://api.telegram.org` from your host

## Deploy on Render (24/7)

This project is ready for Render worker deployment.

### Included deployment files

- `requirements.txt` (Python dependencies)
- `Procfile` with `worker: python -m bot.main`
- `runtime.txt` pinned to `python-3.10.19`
- `render.yaml` with worker service, start command, and persistent disk mount

### Render setup

1. Create a new **Blueprint** service from this repository (uses `render.yaml`), or create a Worker manually.
2. Set required env vars:
   - `BOT_TOKEN`
   - `OWNER_TELEGRAM_ID` (or `OWNER_ID`)
3. Keep `DATABASE_PATH=/var/data/design_lab_bot.db` to persist SQLite on Render disk.
4. Start command should be:

```bash
python -m bot.main
```

### 24/7 reliability

- Bot process uses retry/backoff for Telegram connectivity checks.
- On transient network interruptions, runtime automatically reconnects.
- Persistent disk prevents SQLite data loss across deploy restarts.
