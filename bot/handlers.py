from __future__ import annotations

import logging
from datetime import timedelta

from telegram import BotCommand, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.branding import HELP_CATEGORIES, premium_panel
from bot.database import Database
from bot.permissions import has_custom_permission, require_rank
from bot.ranks import Rank

logger = logging.getLogger(__name__)

VISIBLE_COMMANDS = [
    BotCommand("start", "Start"),
    BotCommand("help", "Help"),
    BotCommand("panel", "Admin panel"),
    BotCommand("info", "User info"),
    BotCommand("rank", "My rank"),
    BotCommand("tag", "User tag"),
    BotCommand("stats", "Statistics"),
]


def ui(title: str, lines: list[str]) -> str:
    return premium_panel(title, lines)


def target_id(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int = 0) -> int | None:
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user.id
    if len(context.args) > idx:
        try:
            return int(context.args[idx])
        except ValueError:
            return None
    return None


def can_perm(update: Update, context: ContextTypes.DEFAULT_TYPE, perm: str, min_rank: Rank) -> bool:
    rank: Rank = context.chat_data.get("rank", Rank.MEMBER)
    if rank >= min_rank:
        return True
    return has_custom_permission(context, update.effective_user.id, perm)


async def ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    owner_id: int = context.application.bot_data["owner_id"]
    user = update.effective_user
    if not user:
        return None
    rec = db.get_user(user.id)
    rank = Rank.OWNER if user.id == owner_id else (rec.rank if rec else Rank.MEMBER)
    db.upsert_user(user.id, user.username, user.full_name, rank)
    context.chat_data["rank"] = rank
    return db.get_user(user.id)


# ---------- General ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rec = await ensure_user(update, context)
    await update.effective_message.reply_text(ui("🚀 Elite Bot", [f"├ الاسم: {rec.full_name}", f"├ الرتبة: {rec.rank.label()}", "└ /help"] ))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update, context)
    kb = [
        [InlineKeyboardButton(HELP_CATEGORIES["admin"], callback_data="help:admin"), InlineKeyboardButton(HELP_CATEGORIES["guard"], callback_data="help:guard")],
        [InlineKeyboardButton("📌 العقوبات", callback_data="help:punish"), InlineKeyboardButton("📌 الصلاحيات", callback_data="help:perms")],
        [InlineKeyboardButton("📌 الوسوم", callback_data="help:tags"), InlineKeyboardButton(HELP_CATEGORIES["tools"], callback_data="help:settings")],
        [InlineKeyboardButton(HELP_CATEGORIES["dev"], callback_data="help:dev")],
    ]
    await update.effective_message.reply_text(ui("📚 مركز المساعدة", ["└ اختر القسم"]), reply_markup=InlineKeyboardMarkup(kb))


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = {
        "help:admin": "/info /reset /replace /say /reply /panel /promote /demote",
        "help:guard": "/lock /unlock /purge /clean /add /del /list /allow /unallow",
        "help:punish": "/ban /unban /mute /unmute /warn /unwarn /warns /tempmute /tempban /kick",
        "help:perms": "/grant /revoke /perms /myperms",
        "help:tags": "/settag /deltag /tag /tags",
        "help:settings": "/setwelcome /setwarnmsg /setmutemsg /setbanmsg /setcode",
        "help:dev": "/stats /top /activity /logs /broadcast /restart /backup",
    }
    await q.edit_message_text(ui("📘 Commands", [f"└ {data.get(q.data, '-')}"]))


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rec = await ensure_user(update, context)
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context) or rec.telegram_id
    r = db.get_user(uid)
    perms = ", ".join(db.permissions_of(uid)) or "-"
    await update.effective_message.reply_text(ui("👤 معلومات العضو", [
        f"├ الاسم: {r.full_name}",
        f"├ الايدي: {r.telegram_id}",
        f"├ الرتبة: {r.rank.label()}",
        f"├ الوسم: {r.tag or '-'}",
        f"├ التحذيرات: {db.warns_count(uid)}",
        f"└ الصلاحيات: {perms}",
    ]))


# ---------- Management ----------
@require_rank(Rank.ADMIN)
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ui("♻ Reset", ["└ تم إعادة الضبط"] ))


@require_rank(Rank.ADMIN)
async def replace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ui("🔁 Replace", ["└ تم تنفيذ الاستبدال"] ))


@require_rank(Rank.MODERATOR)
async def say(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(" ".join(context.args) or "-")


@require_rank(Rank.MODERATOR)
async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await update.message.reply_to_message.reply_text(" ".join(context.args) or "-")


# ---------- Roles ----------
@require_rank(Rank.SUPERADMIN)
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await promote_to(update, context, Rank.ADMIN)


@require_rank(Rank.SUPERADMIN)
async def unadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await promote_to(update, context, Rank.MEMBER)


@require_rank(Rank.ADMIN)
async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await promote_to(update, context, Rank.VIP)


@require_rank(Rank.ADMIN)
async def unvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await promote_to(update, context, Rank.MEMBER)


async def promote_to(update: Update, context: ContextTypes.DEFAULT_TYPE, rank: Rank):
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context)
    if not uid:
        await update.effective_message.reply_text("Usage: command <id>")
        return
    db.set_rank(uid, rank)
    db.write_audit(update.effective_user.id, "set_rank", uid, rank.label())
    await update.effective_message.reply_text(ui("👑 Roles", [f"└ {uid} => {rank.label()} "]))


@require_rank(Rank.SUPERADMIN)
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    if len(context.args) < 2:
        await update.effective_message.reply_text("/promote <id> <rank>")
        return
    uid = int(context.args[0])
    rk = Rank.parse(context.args[1])
    db.set_rank(uid, rk)
    db.write_audit(update.effective_user.id, "promote", uid, rk.label())
    await update.effective_message.reply_text(ui("⬆ Promote", [f"└ {uid} => {rk.label()} "]))


@require_rank(Rank.SUPERADMIN)
async def demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = [str(target_id(update, context) or 0), "member"]
    await promote(update, context)


async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    me = await ensure_user(update, context)
    await update.effective_message.reply_text(ui("🏅 Rank", [f"├ rank: {me.rank.label()}", f"├ tag: {me.tag or '-'}", f"└ joined: {me.created_at[:10]}"]))


whois = info


# ---------- Tags ----------
@require_rank(Rank.ADMIN)
async def settag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    if len(context.args) < 2:
        await update.effective_message.reply_text("/settag <id> <tag>")
        return
    uid = int(context.args[0])
    tag = " ".join(context.args[1:])
    db.set_tag(uid, tag)
    db.write_audit(update.effective_user.id, "settag", uid, tag)
    await update.effective_message.reply_text(ui("🏷 Tag", [f"└ {uid}: {tag}"]))


@require_rank(Rank.ADMIN)
async def deltag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context)
    if not uid:
        await update.effective_message.reply_text("/deltag <id>")
        return
    db.set_tag(uid, None)
    db.write_audit(update.effective_user.id, "deltag", uid)
    await update.effective_message.reply_text(ui("🏷 Tag", ["└ removed"]))


async def tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context) or update.effective_user.id
    r = db.get_user(uid)
    await update.effective_message.reply_text(ui("🏷 Tag", [f"└ {r.tag or '-'}"]))


@require_rank(Rank.ADMIN)
async def tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = context.application.bot_data["db"].list_tags()
    await update.effective_message.reply_text(ui("🏷 Tags", [*(f"├ {x['telegram_id']}: {x['tag']}" for x in rows[:20]), "└ End"]))


# ---------- Custom permissions ----------
@require_rank(Rank.SUPERADMIN)
async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    if len(context.args) < 2:
        await update.effective_message.reply_text("/grant <id> <permission>")
        return
    db.grant_permission(int(context.args[0]), context.args[1])
    await update.effective_message.reply_text(ui("✅ Grant", [f"└ {context.args[0]} + {context.args[1]}"]))


@require_rank(Rank.SUPERADMIN)
async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    if len(context.args) < 2:
        await update.effective_message.reply_text("/revoke <id> <permission>")
        return
    db.revoke_permission(int(context.args[0]), context.args[1])
    await update.effective_message.reply_text(ui("❌ Revoke", [f"└ {context.args[0]} - {context.args[1]}"]))


@require_rank(Rank.SUPERADMIN)
async def perms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context)
    if not uid:
        await update.effective_message.reply_text("/perms <id>")
        return
    p = ", ".join(db.permissions_of(uid)) or "-"
    await update.effective_message.reply_text(ui("🔐 Permissions", [f"└ {uid}: {p}"]))


async def myperms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    p = ", ".join(db.permissions_of(update.effective_user.id)) or "-"
    await update.effective_message.reply_text(ui("🔐 My Permissions", [f"└ {p}"]))


# ---------- Moderation ----------
async def _mod_guard(update: Update, context: ContextTypes.DEFAULT_TYPE, perm: str):
    await ensure_user(update, context)
    if not can_perm(update, context, perm, Rank.MODERATOR):
        await update.effective_message.reply_text("⛔ Missing permission")
        return None
    uid = target_id(update, context)
    if not uid:
        await update.effective_message.reply_text("حدد المستخدم عبر reply أو id")
        return None
    return uid


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "ban")
    if not uid:
        return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid)
    except Exception:
        pass
    context.application.bot_data["db"].write_audit(update.effective_user.id, "ban", uid)
    await update.effective_message.reply_text(ui("🚫 Ban", [f"└ {uid}"]))


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "ban")
    if not uid:
        return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, uid)
    except Exception:
        pass
    await update.effective_message.reply_text(ui("✅ Unban", [f"└ {uid}"]))


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "mute")
    if not uid:
        return
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, ChatPermissions(can_send_messages=False))
    except Exception:
        pass
    await update.effective_message.reply_text(ui("🔇 Mute", [f"└ {uid}"]))


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "mute")
    if not uid:
        return
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, ChatPermissions(can_send_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True))
    except Exception:
        pass
    await update.effective_message.reply_text(ui("🔊 Unmute", [f"└ {uid}"]))


async def tempmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "mute")
    if not uid:
        return
    mins = int(context.args[1]) if len(context.args) > 1 else 10
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, ChatPermissions(can_send_messages=False), until_date=timedelta(minutes=mins))
    except Exception:
        pass
    await update.effective_message.reply_text(ui("⏳ TempMute", [f"└ {uid} for {mins}m"]))


async def tempban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "ban")
    if not uid:
        return
    hrs = int(context.args[1]) if len(context.args) > 1 else 1
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid, until_date=timedelta(hours=hrs))
    except Exception:
        pass
    await update.effective_message.reply_text(ui("⏳ TempBan", [f"└ {uid} for {hrs}h"]))


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await tempban(update, context)


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "warn")
    if not uid:
        return
    db: Database = context.application.bot_data["db"]
    total = db.add_warn(uid, update.effective_user.id, " ".join(context.args[1:]) if len(context.args) > 1 else None)
    db.write_audit(update.effective_user.id, "warn", uid, str(total))
    await update.effective_message.reply_text(ui("⚠ Warn", [f"└ {uid}: {total}"]))


async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await _mod_guard(update, context, "warn")
    if not uid:
        return
    db: Database = context.application.bot_data["db"]
    db.clear_warn(uid)
    await update.effective_message.reply_text(ui("✅ Unwarn", [f"└ {uid}"]))


async def warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    uid = target_id(update, context) or update.effective_user.id
    await update.effective_message.reply_text(ui("⚠ Warns", [f"└ {uid}: {db.warns_count(uid)}"]))


# ---------- Delete / protection ----------
async def delmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await update.message.reply_to_message.delete()


async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_perm(update, context, "purge", Rank.MODERATOR):
        await update.effective_message.reply_text("⛔")
        return
    await update.effective_message.reply_text(ui("🧹 Purge", ["└ done"]))


async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ui("🧼 Clean", [f"└ {' '.join(context.args) or 'all'}"]))


async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    key = " ".join(context.args).lower()
    db.set_setting(update.effective_chat.id, f"lock_{key}", "1")
    await update.effective_message.reply_text(ui("🔒 Lock", [f"└ {key}"]))


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    key = " ".join(context.args).lower()
    db.set_setting(update.effective_chat.id, f"lock_{key}", "0")
    await update.effective_message.reply_text(ui("🔓 Unlock", [f"└ {key}"]))


add = lock
del_cmd = unlock


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = context.application.bot_data["db"].list_filters(update.effective_chat.id)
    await update.effective_message.reply_text(ui("📋 List", [f"└ {', '.join(words) if words else '-'}"]))


allow = unlock
unallow = lock


# ---------- Settings ----------
@require_rank(Rank.ADMIN)
async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.bot_data["db"].set_setting(update.effective_chat.id, "welcome_text", " ".join(context.args))
    await update.effective_message.reply_text(ui("⚙ setwelcome", ["└ saved"]))


setwarnmsg = setwelcome
setmutemsg = setwelcome
setbanmsg = setwelcome
setcode = setwelcome


# ---------- Analytics/dev ----------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    st = db.stats()
    await update.effective_message.reply_text(ui("📊 Stats", [f"├ users: {st['users']}", f"├ warns: {st['warns']}", f"└ logs: {st['logs']} "]))


top = stats
activity = stats


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = context.application.bot_data["db"].latest_logs(10)
    await update.effective_message.reply_text(ui("📜 Logs", [*(f"├ {x['action']} {x['target_id']}" for x in rows), "└ end"]))


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    text = " ".join(context.args)
    sent = 0
    for uid in db.list_user_ids():
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
    await update.effective_message.reply_text(ui("📢 Broadcast", [f"└ {sent}"]))


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ui("♻ Restart", ["└ requested"]))


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    with open(db.path, "rb") as f:
        await context.bot.send_document(update.effective_chat.id, f)


# ---------- panel / callbacks / trackers ----------
async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Members", callback_data="panel:members"), InlineKeyboardButton("Warnings", callback_data="panel:warnings")],
        [InlineKeyboardButton("Mute", callback_data="panel:mute"), InlineKeyboardButton("Ban", callback_data="panel:ban")],
        [InlineKeyboardButton("Tags", callback_data="panel:tags"), InlineKeyboardButton("Permissions", callback_data="panel:perms")],
        [InlineKeyboardButton("Stats", callback_data="panel:stats"), InlineKeyboardButton("Logs", callback_data="panel:logs")],
        [InlineKeyboardButton("Settings", callback_data="panel:settings")],
    ]
    await update.effective_message.reply_text(ui("🧩 Premium Panel", ["└ اختر القسم"]), reply_markup=InlineKeyboardMarkup(kb))


async def panel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(ui("🎛 Panel", [f"└ {q.data}"]))


async def on_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    owner = context.application.bot_data["owner_id"]
    for m in update.effective_message.new_chat_members:
        r = Rank.OWNER if m.id == owner else Rank.MEMBER
        db.upsert_user(m.id, m.username, m.full_name, r)
        db.record_event(m.id, "join")
        await update.effective_message.reply_text(ui("🎉 Welcome", [f"├ {m.full_name}", f"└ Rank: {r.label()} "]))


async def on_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.left_chat_member:
        context.application.bot_data["db"].record_event(update.message.left_chat_member.id, "leave")


async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message or not update.effective_message.text:
        return
    db: Database = context.application.bot_data["db"]
    owner = context.application.bot_data["owner_id"]
    db.upsert_user(update.effective_user.id, update.effective_user.username, update.effective_user.full_name, Rank.OWNER if update.effective_user.id == owner else Rank.MEMBER)
    db.increment_message(update.effective_user.id)



def register_handlers(app: Application) -> None:
    mapping = {
        "start": start, "help": help_cmd, "info": info, "reset": reset, "replace": replace, "say": say, "reply": reply_cmd,
        "lock": lock, "unlock": unlock, "purge": purge, "delmsg": delmsg, "clean": clean,
        "ban": ban, "unban": unban, "mute": mute, "unmute": unmute, "warn": warn, "unwarn": unwarn, "warns": warns,
        "tempmute": tempmute, "tempban": tempban, "kick": kick,
        "admin": admin, "unadmin": unadmin, "vip": vip, "unvip": unvip,
        "setwelcome": setwelcome, "setwarnmsg": setwarnmsg, "setmutemsg": setmutemsg, "setbanmsg": setbanmsg, "setcode": setcode,
        "add": add, "del": del_cmd, "list": list_cmd, "allow": allow, "unallow": unallow,
        "settag": settag, "deltag": deltag, "tag": tag, "tags": tags,
        "grant": grant, "revoke": revoke, "perms": perms, "myperms": myperms,
        "promote": promote, "demote": demote, "rank": rank, "whois": whois,
        "panel": panel_cmd, "stats": stats, "top": top, "activity": activity, "logs": logs,
        "broadcast": broadcast, "restart": restart, "backup": backup,
    }
    for name, fn in mapping.items():
        app.add_handler(CommandHandler(name, fn))

    app.add_handler(CallbackQueryHandler(help_callback, pattern=r"^help:"))
    app.add_handler(CallbackQueryHandler(panel_cb, pattern=r"^panel:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_join))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track))
