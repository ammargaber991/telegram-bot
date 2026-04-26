from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from bot.ranks import Rank

HandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


COMMAND_MIN_RANK: dict[str, Rank] = {
    "start": Rank.MEMBER,
    "help": Rank.MEMBER,
    "info": Rank.MEMBER,
    "rank": Rank.MEMBER,
    "tag": Rank.MEMBER,
    "mytag": Rank.MEMBER,
    "myperms": Rank.MEMBER,
    "whois": Rank.MODERATOR,
    "panel": Rank.MODERATOR,
    "stats": Rank.MODERATOR,
    "top": Rank.MODERATOR,
    "activity": Rank.MODERATOR,
    "logs": Rank.MODERATOR,
    "ban": Rank.MODERATOR,
    "unban": Rank.MODERATOR,
    "mute": Rank.MODERATOR,
    "unmute": Rank.MODERATOR,
    "warn": Rank.MODERATOR,
    "unwarn": Rank.MODERATOR,
    "warns": Rank.MODERATOR,
    "kick": Rank.MODERATOR,
    "purge": Rank.MODERATOR,
    "clean": Rank.MODERATOR,
    "lock": Rank.MODERATOR,
    "unlock": Rank.MODERATOR,
    "tempmute": Rank.MODERATOR,
    "tempban": Rank.MODERATOR,
    "filter": Rank.MODERATOR,
    "settag": Rank.ADMIN,
    "deltag": Rank.ADMIN,
    "tags": Rank.ADMIN,
    "grant": Rank.SUPERADMIN,
    "revoke": Rank.SUPERADMIN,
    "perms": Rank.SUPERADMIN,
    "setwelcome": Rank.ADMIN,
    "setwarnmsg": Rank.ADMIN,
    "setmutemsg": Rank.ADMIN,
    "setbanmsg": Rank.ADMIN,
    "setcode": Rank.SUPERADMIN,
    "promote": Rank.SUPERADMIN,
    "demote": Rank.SUPERADMIN,
    "admin": Rank.SUPERADMIN,
    "unadmin": Rank.SUPERADMIN,
    "vip": Rank.ADMIN,
    "unvip": Rank.ADMIN,
    "reset": Rank.ADMIN,
    "replace": Rank.ADMIN,
    "say": Rank.MODERATOR,
    "reply": Rank.MODERATOR,
    "add": Rank.MODERATOR,
    "del": Rank.MODERATOR,
    "list": Rank.MODERATOR,
    "allow": Rank.MODERATOR,
    "unallow": Rank.MODERATOR,
    "broadcast": Rank.SUPERADMIN,
    "backup": Rank.OWNER,
    "restart": Rank.OWNER,
}


def _current_rank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Rank:
    user = update.effective_user
    if user is None:
        return Rank.MEMBER

    db = context.application.bot_data.get("db")
    owner_id = context.application.bot_data.get("owner_id")
    if owner_id is not None and user.id == owner_id:
        rank = Rank.OWNER
    elif db is not None:
        record = db.get_user(user.id)
        rank = record.rank if record else Rank.MEMBER
    else:
        rank = Rank.MEMBER

    context.chat_data["rank"] = rank
    return rank


def require_rank(required: Rank) -> Callable[[HandlerFn], HandlerFn]:
    def decorator(func: HandlerFn) -> HandlerFn:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user_rank = _current_rank(update, context)
            if user_rank < required:
                if update.effective_message:
                    await update.effective_message.reply_text("⛔ Permission denied | لا تملك الصلاحية")
                return
            await func(update, context)

        return wrapper

    return decorator


def has_custom_permission(context: ContextTypes.DEFAULT_TYPE, user_id: int, perm: str) -> bool:
    db = context.application.bot_data.get("db")
    return bool(db and db.has_permission(user_id, perm))
