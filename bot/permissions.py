from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from bot.ranks import Rank

HandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


COMMAND_MIN_RANK: dict[str, Rank] = {
    "start": Rank.USER,
    "help": Rank.USER,
    "rank": Rank.USER,
    "whois": Rank.MODERATOR,
    "dl_status": Rank.MODERATOR,
    "promote": Rank.ADMIN,
    "demote": Rank.ADMIN,
    "broadcast": Rank.ADMIN,
    "logs": Rank.DEVELOPER,
    "dev_stats": Rank.DEVELOPER,
    "dev_note": Rank.DEVELOPER,
}


def _current_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Rank:
    user = update.effective_user
    if user is None:
        return Rank.USER

    db = context.application.bot_data.get("db")
    owner_id = context.application.bot_data.get("owner_id")
    if owner_id is not None and user.id == owner_id:
        rank = Rank.OWNER
    elif db is not None:
        record = db.get_user(user.id)
        rank = record.rank if record else Rank.USER
    else:
        rank = Rank.USER

    context.chat_data["rank"] = rank
    return rank


def require_rank(required: Rank) -> Callable[[HandlerFn], HandlerFn]:
    def decorator(func: HandlerFn) -> HandlerFn:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user_rank = _current_rank(update, context)
            if user_rank < required:
                if update.effective_message:
                    await update.effective_message.reply_text("⛔ Permission denied.")
                return
            await func(update, context)

        return wrapper

    return decorator
