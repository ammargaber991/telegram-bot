from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.branding import footer, header
from bot.database import Database
from bot.permissions import COMMAND_MIN_RANK, require_rank
from bot.ranks import Rank

logger = logging.getLogger(__name__)

VISIBLE_COMMANDS = [
    BotCommand("start", "Start Design Lab bot"),
    BotCommand("help", "Show command help"),
    BotCommand("rank", "Show your rank"),
    BotCommand("whois", "Inspect user profile (moderator+)"),
    BotCommand("promote", "Promote user rank (admin+)"),
    BotCommand("demote", "Demote user to user rank (admin+)"),
    BotCommand("broadcast", "Broadcast message (admin+)"),
    BotCommand("logs", "Recent audit logs (developer+)"),
    BotCommand("dl_status", "Design Lab status"),
]


def _rank_for_user(db: Database, telegram_id: int, owner_id: int) -> Rank:
    if telegram_id == owner_id:
        return Rank.OWNER
    record = db.get_user(telegram_id)
    return record.rank if record else Rank.USER


async def rank_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    owner_id: int = context.application.bot_data["owner_id"]

    user = update.effective_user
    if user is None:
        return

    computed = _rank_for_user(db, user.id, owner_id)
    db.upsert_user(user.id, user.username, user.full_name, computed)
    context.chat_data["rank"] = computed


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rank_context(update, context)
    rank: Rank = context.chat_data["rank"]
    text = (
        f"{header('Control Center')}\n\n"
        "Welcome to the Design Lab operations bot.\n"
        f"Your current rank: *{rank.label()}*\n\n"
        "Use /help to see available commands.\n\n"
        f"{footer()}"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rank_context(update, context)
    rank: Rank = context.chat_data["rank"]

    lines = [f"{header('Command Guide')}", ""]
    for name, required in COMMAND_MIN_RANK.items():
        if name.startswith("dev_"):
            continue
        if rank >= required:
            lines.append(f"• /{name} _(min: {required.label()})_")

    lines.extend(["", footer()])
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rank_context(update, context)
    rank: Rank = context.chat_data["rank"]
    await update.effective_message.reply_text(f"🏷️ Rank: *{rank.label()}*", parse_mode=ParseMode.MARKDOWN)


@require_rank(Rank.MODERATOR)
async def whois(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text("Usage: /whois <telegram_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("telegram_id must be numeric.")
        return

    rec = db.get_user(user_id)
    if rec is None:
        await update.effective_message.reply_text("User not found.")
        return

    msg = (
        f"ID: {rec.telegram_id}\n"
        f"Username: @{rec.username or 'n/a'}\n"
        f"Name: {rec.full_name}\n"
        f"Rank: {rec.rank.label()}\n"
        f"Updated: {rec.updated_at}"
    )
    await update.effective_message.reply_text(msg)


@require_rank(Rank.ADMIN)
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    actor = update.effective_user.id
    if len(context.args) < 2:
        await update.effective_message.reply_text("Usage: /promote <telegram_id> <rank>")
        return

    try:
        target = int(context.args[0])
        new_rank = Rank.parse(context.args[1])
    except ValueError as exc:
        await update.effective_message.reply_text(str(exc))
        return

    rec = db.get_user(target)
    if rec is None:
        await update.effective_message.reply_text("Target user not found in database.")
        return

    db.set_rank(target, new_rank)
    db.write_audit(actor_id=actor, action="promote", target_id=target, details=f"rank={new_rank.label()}")
    await update.effective_message.reply_text(f"✅ User {target} promoted to {new_rank.label()}.")


@require_rank(Rank.ADMIN)
async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    actor = update.effective_user.id
    if not context.args:
        await update.effective_message.reply_text("Usage: /demote <telegram_id>")
        return

    try:
        target = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("telegram_id must be numeric.")
        return

    if db.get_user(target) is None:
        await update.effective_message.reply_text("Target user not found in database.")
        return

    db.set_rank(target, Rank.USER)
    db.write_audit(actor_id=actor, action="demote", target_id=target, details="rank=user")
    await update.effective_message.reply_text(f"✅ User {target} demoted to user.")


@require_rank(Rank.DEVELOPER)
async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            pass

    rows = db.latest_logs(limit=limit)
    if not rows:
        await update.effective_message.reply_text("No audit logs yet.")
        return

    rendered = []
    for row in rows:
        rendered.append(
            f"#{row['id']} {row['created_at']} | {row['action']} | actor={row['actor_id']} | target={row['target_id']} | {row['details'] or ''}"
        )
    await update.effective_message.reply_text("\n".join(rendered[:20]))


@require_rank(Rank.ADMIN)
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    actor = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text("Usage: /broadcast <message>")
        return

    sent = 0
    for user_id in db.list_user_ids():
        try:
            await context.bot.send_message(chat_id=user_id, text=f"📣 {text}")
            sent += 1
        except Exception:
            logger.exception("Broadcast failed for user %s", user_id)

    db.write_audit(actor_id=actor, action="broadcast", details=f"sent={sent}")
    await update.effective_message.reply_text(f"Broadcast complete. Sent to {sent} users.")


@require_rank(Rank.MODERATOR)
async def dl_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    stats = db.stats()
    text = (
        f"{header('System Status')}\n\n"
        f"Users tracked: *{stats['users']}*\n"
        f"Audit events: *{stats['logs']}*\n"
        "State: *Operational* ✅\n\n"
        f"{footer()}"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@require_rank(Rank.DEVELOPER)
async def dev_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    stats = db.stats()
    await update.effective_message.reply_text(f"internal: users={stats['users']}, logs={stats['logs']}")


@require_rank(Rank.DEVELOPER)
async def dev_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    actor = update.effective_user.id
    note = " ".join(context.args).strip()
    if not note:
        await update.effective_message.reply_text("Usage: /dev_note <text>")
        return
    db.write_audit(actor_id=actor, action="dev_note", details=note)
    await update.effective_message.reply_text("📝 note logged")


async def on_any_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rank_context(update, context)


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("rank", rank_cmd))
    app.add_handler(CommandHandler("whois", whois))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("demote", demote))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("dl_status", dl_status))

    # Hidden developer commands: registered but intentionally excluded from VISIBLE_COMMANDS and /help output.
    app.add_handler(CommandHandler("dev_stats", dev_stats))
    app.add_handler(CommandHandler("dev_note", dev_note))
