"""
Uptime Kuma-style monitor management commands.
"""

from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from database.memory import acknowledge_alert, get_unacknowledged_alerts
from monitoring.uptime import store
from monitoring.uptime.analytics import build_weekly_report, send_weekly_report
from monitoring.uptime.builtin import sync_docker_monitors
from monitoring.uptime.engine import record_push_for_monitor
from utils.formatters import escape_telegram_html
from utils.security import require_auth, rate_limit, reject_unauthorized_callback, callback_data_for_user, parse_callback_user_id

logger = logging.getLogger(__name__)


@require_auth
@rate_limit
async def monitors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all uptime monitors."""
    monitors = await store.list_monitors()
    if not monitors:
        await update.message.reply_text(
            "No monitors yet. Use:\n"
            "<code>/monitor_add &lt;name&gt; &lt;type&gt; &lt;target&gt;</code>\n"
            "Types: http, https, tcp, ping, dns, ssl, keyword, docker, systemd, push",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = ["📡 <b>Uptime monitors</b>\n"]
    for m in monitors:
        icon = "🟢" if m.get("last_status") == "up" else "🔴" if m.get("last_status") == "down" else "⚪"
        maint = " 🛠" if m.get("maintenance_mode") else ""
        en = "" if m.get("enabled") else " (disabled)"
        lines.append(
            f"{icon} <code>{escape_telegram_html(m['name'])}</code>{maint}{en}\n"
            f"   {m['type']} → <code>{escape_telegram_html(m['target'][:60])}</code> "
            f"| {m.get('uptime_percentage', 0):.1f}%"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /monitor_add name type target [interval_seconds]
    """
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: <code>/monitor_add name type target [interval_sec]</code>\n"
            "Example: <code>/monitor_add jellyfin https https://127.0.0.1:8096 120</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    name, mtype, target = args[0], args[1], args[2]
    interval = int(args[3]) if len(args) > 3 else config.UPTIME_DEFAULT_INTERVAL
    try:
        mid = await store.create_monitor(name, mtype, target, interval_seconds=interval)
        await update.message.reply_text(
            f"✅ Monitor <code>{escape_telegram_html(name)}</code> created (id {mid})",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@require_auth
@rate_limit
async def monitor_rm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: <code>/monitor_rm &lt;name&gt;</code>", parse_mode=ParseMode.HTML)
        return
    m = await store.get_monitor_by_name(args[0])
    if not m:
        await update.message.reply_text("Monitor not found.")
        return
    await store.delete_monitor(m["id"])
    await update.message.reply_text(f"Deleted monitor <code>{escape_telegram_html(args[0])}</code>", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: <code>/monitor_pause &lt;name&gt;</code>", parse_mode=ParseMode.HTML)
        return
    m = await store.get_monitor_by_name(args[0])
    if not m:
        await update.message.reply_text("Monitor not found.")
        return
    await store.update_monitor(m["id"], maintenance_mode=True)
    await update.message.reply_text(f"🛠 Maintenance mode ON for <code>{escape_telegram_html(args[0])}</code>", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: <code>/monitor_resume &lt;name&gt;</code>", parse_mode=ParseMode.HTML)
        return
    m = await store.get_monitor_by_name(args[0])
    if not m:
        await update.message.reply_text("Monitor not found.")
        return
    await store.update_monitor(m["id"], maintenance_mode=False, enabled=True)
    await update.message.reply_text(f"▶️ Resumed <code>{escape_telegram_html(args[0])}</code>", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_silence_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/monitor_silence name minutes"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/monitor_silence &lt;name&gt; &lt;minutes&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    m = await store.get_monitor_by_name(args[0])
    if not m:
        await update.message.reply_text("Monitor not found.")
        return
    mins = max(1, min(1440, int(args[1])))
    await store.add_silence(mins, monitor_id=m["id"], reason="user")
    await update.message.reply_text(f"🔕 Silenced {mins}m for <code>{escape_telegram_html(args[0])}</code>", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_dep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/monitor_dep parent_name child_name — suppress child alerts when parent is down."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/monitor_dep &lt;parent&gt; &lt;child&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    parent = await store.get_monitor_by_name(args[0])
    child = await store.get_monitor_by_name(args[1])
    if not parent or not child:
        await update.message.reply_text("Parent or child monitor not found.")
        return
    await store.add_dependency(parent["id"], child["id"])
    await update.message.reply_text(
        f"Linked: <code>{args[0]}</code> → <code>{args[1]}</code>",
        parse_mode=ParseMode.HTML,
    )


@require_auth
@rate_limit
async def monitor_discover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Discovering Docker containers…")
    await sync_docker_monitors()
    await monitors_command(update, context)


@require_auth
@rate_limit
async def monitor_push_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create push monitor and return token for cron/Uptime Kuma-style heartbeat."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/monitor_push &lt;name&gt; [interval_sec]</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    name = args[0]
    interval = int(args[1]) if len(args) > 1 else 300
    if await store.get_monitor_by_name(name):
        await update.message.reply_text("Monitor name already exists.")
        return
    mid = await store.create_monitor(name, "push", "heartbeat", interval_seconds=interval)
    token = await store.register_push_token(mid)
    await update.message.reply_text(
        f"Push monitor <code>{escape_telegram_html(name)}</code>\n"
        f"POST to cron hook with token in JSON or use:\n"
        f"<code>GET /push/{token}</code> on dashboard port if enabled.\n"
        f"Token: <code>{token}</code>",
        parse_mode=ParseMode.HTML,
    )


@require_auth
@rate_limit
async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await get_unacknowledged_alerts()
    if not rows:
        await update.message.reply_text("✅ No unacknowledged alerts.")
        return
    lines = ["⚠️ <b>Unacknowledged alerts</b>\n"]
    for r in rows[:15]:
        lines.append(
            f"#{r['id']} [{r['severity']}] <code>{escape_telegram_html(r['type'])}</code>\n"
            f"{escape_telegram_html((r['message'] or '')[:200])}\n"
        )
    lines.append("\nAck: <code>/alert_ack &lt;id&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def alert_ack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: <code>/alert_ack &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        await acknowledge_alert(int(args[0]))
        await update.message.reply_text(f"✅ Alert #{args[0]} acknowledged.")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@require_auth
@rate_limit
async def monitor_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await build_weekly_report()
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_monitor_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uptime alert inline buttons."""
    query = update.callback_query
    if not query or not query.data:
        return
    if reject_unauthorized_callback(update):
        return
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    action = data.split(":", 1)[0] if data else ""

    if action == "uack":
        uid, payload = parse_callback_user_id(data, "uack")
        if uid != user_id:
            return
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✅ Monitor alert noted.")
    elif action == "usil":
        uid, payload = parse_callback_user_id(data, "usil")
        if uid != user_id:
            return
        mid_s, _, mins_s = (payload or "").partition(":")
        mins = int(mins_s or "60")
        await store.add_silence(mins, monitor_id=int(mid_s), reason="telegram")
        await query.message.reply_text(f"🔕 Silenced {mins} minutes.")
    elif action == "ulog":
        uid, payload = parse_callback_user_id(data, "ulog")
        if uid != user_id:
            return
        from services.docker_service import get_container_logs
        from utils.telegram_reply import reply_text_chunked

        try:
            logs = await __import__("asyncio").to_thread(get_container_logs, payload, 40)
            await reply_text_chunked(
                query.message,
                f"📋 Logs `{payload}`:\n<pre>{escape_telegram_html(logs[:3500])}</pre>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Logs failed: {e}")
    elif action == "urst":
        uid, payload = parse_callback_user_id(data, "urst")
        if uid != user_id:
            return
        from commands.docker_cmds import send_restart_confirmation

        await send_restart_confirmation(update, context, user_id, payload)
