"""
Uptime Kuma-style monitor management commands.
"""

from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from database.memory import acknowledge_alert, acknowledge_all_alerts, get_unacknowledged_alerts
from commands.alert_ack import acknowledge_all_and_reply, handle_acknowledge_all_text
from monitoring.uptime import store
from monitoring.uptime.analytics import build_weekly_report, build_monitor_stats_report
from monitoring.uptime.builtin import sync_docker_monitors
from monitoring.uptime import groups
from monitoring.uptime.docker_images import scan_image_updates
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
            "Types: http, https, tcp, ping, dns, ssl, keyword, docker, systemd, process, "
            "tailscale, cloudflared, push",
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
    lines.append(
        "\nAck one: <code>/alert_ack &lt;id&gt;</code> · "
        "all: <code>/alert_ack all</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def alert_ack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/alert_ack all</code> — dismiss all pending alerts\n"
            "<code>/alert_ack &lt;id&gt;</code> — dismiss one (see /alerts)",
            parse_mode=ParseMode.HTML,
        )
        return
    if args[0].strip().lower() in ("all", "*"):
        await acknowledge_all_and_reply(update)
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


@require_auth
@rate_limit
async def monitor_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/monitor_stats name [hours] — MTBF/MTTR and latency sparkline."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/monitor_stats &lt;name&gt; [hours]</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    hours = int(args[1]) if len(args) > 1 and args[1].isdigit() else 168
    text = await build_monitor_stats_report(args[0], hours=hours)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_group_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/monitor_group_add group_name monitor_name"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/monitor_group_add &lt;group&gt; &lt;monitor&gt;</code>\n"
            "Create group first with <code>/monitor_group_create &lt;name&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    ok = await groups.add_monitor_to_group(args[0], args[1])
    if ok:
        await update.message.reply_text(
            f"Added <code>{escape_telegram_html(args[1])}</code> → group "
            f"<code>{escape_telegram_html(args[0])}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("Group or monitor not found.")


@require_auth
@rate_limit
async def monitor_group_create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: <code>/monitor_group_create &lt;name&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        gid = await groups.create_group(args[0])
        await update.message.reply_text(
            f"✅ Group <code>{escape_telegram_html(args[0])}</code> (id {gid})",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


@require_auth
@rate_limit
async def monitor_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    grps = await groups.list_groups()
    if not grps:
        await update.message.reply_text("No groups. Use <code>/monitor_group_create</code>.", parse_mode=ParseMode.HTML)
        return
    lines = ["📁 <b>Monitor groups</b>\n"]
    for g in grps:
        lines.append(
            f"• <code>{escape_telegram_html(g['name'])}</code> "
            f"({g.get('member_count', 0)} monitors)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def monitor_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/monitor_tag monitor_name tag1,tag2"""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: <code>/monitor_tag &lt;monitor&gt; &lt;tag1,tag2&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    tags = [t.strip() for t in args[1].split(",") if t.strip()]
    ok = await groups.set_monitor_tags(args[0], tags)
    if ok:
        await update.message.reply_text(
            f"Tags set on <code>{escape_telegram_html(args[0])}</code>: "
            f"<code>{escape_telegram_html(', '.join(tags))}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("Monitor not found.")


@require_auth
@rate_limit
async def monitor_images_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force Docker image update scan."""
    await update.message.reply_text("Scanning Docker image IDs…")
    changed = await scan_image_updates(context.bot)
    if changed:
        await update.message.reply_text(
            f"Updated containers: <code>{escape_telegram_html(', '.join(changed))}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("No image changes detected.")


async def handle_monitor_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uptime alert inline buttons (delegates to monitoring.uptime.callbacks)."""
    from monitoring.uptime.callbacks import handle_uptime_callback

    await handle_uptime_callback(update, context)
