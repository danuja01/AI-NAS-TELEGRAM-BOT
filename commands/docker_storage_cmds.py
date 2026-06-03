"""
Docker + storage management (/d* commands).
"""

from __future__ import annotations

import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from database.memory import save_command, save_storage_snapshot
from services import docker_storage_service as dss
from services import storage_scanner as ss
from services.host_runner import run_profile
from services.system_monitor import (
    get_cpu_stats,
    get_disk_stats,
    get_memory_stats,
    get_temperatures,
    get_uptime,
)
from utils.formatters import format_error_html
from utils.formatters import docker_storage as fmt
from utils.security import (
    require_auth,
    rate_limit,
    reject_unauthorized_callback,
    callback_data_for_user,
    parse_callback_user_id,
)
from utils.telegram_reply import reply_text_chunked, reply_text_safe

logger = logging.getLogger(__name__)

CB_DCLEAN_CONFIRM = "cln"
CB_DCLEAN_CANCEL = "clc"
CB_DAGG_STEP1 = "ag1"
CB_DAGG_CANCEL = "agc"
CB_DAGG_CONFIRM = "agf"

_kw = {"parse_mode": ParseMode.HTML}


def _volume_count() -> int:
    try:
        import docker

        return len(docker.from_env().volumes.list())
    except Exception:
        return 0


async def docker_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Docker HTML dashboard (/docker). Authorized + rate-limited by the caller."""
    user_id = update.effective_user.id
    await reply_text_safe(update, "🐳 Loading Docker dashboard…", **_kw)
    try:
        df = dss.docker_system_df()
        running, stopped = dss.count_containers()
        images = dss.list_images_with_usage()
        vols = _volume_count()
        active = run_profile("systemctl_is_active", extra_args=["docker"])
        docker_state = active.stdout.strip() if active.ok else (active.error or "unknown")
        raw = dss.docker_ps_json_lines()
        msg = fmt.format_docker_dashboard(
            df.stdout, running, stopped, len(images), vols, docker_state, raw
        )
        await reply_text_chunked(update, msg, **_kw)
        await save_command(user_id, "/docker", "dashboard")
    except Exception as e:
        logger.exception("docker_dashboard")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


@require_auth
@rate_limit
async def dimages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await reply_text_safe(update, "📦 Listing images…", **_kw)
    try:
        images = dss.list_images_with_usage()
        await reply_text_chunked(update, fmt.format_images_report(images), **_kw)
        await save_command(user_id, "/dimages", f"{len(images)} images")
    except Exception as e:
        logger.exception("dimages_command")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


@require_auth
@rate_limit
async def dbigfiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await reply_text_safe(update, "📁 Scanning large files (allowlisted paths)…", **_kw)
    try:
        files = await asyncio.to_thread(ss.find_large_files)
        await reply_text_chunked(update, fmt.format_bigfiles(files), **_kw)
        await save_command(user_id, "/dbigfiles", f"{len(files)} files")
    except Exception as e:
        logger.exception("dbigfiles_command")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


@require_auth
@rate_limit
async def dlogs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Huge log file scan (not container tail — use /dtail)."""
    user_id = update.effective_user.id
    await reply_text_safe(update, "📜 Scanning for large log files…", **_kw)
    try:
        files = await asyncio.to_thread(ss.find_huge_logs)
        await reply_text_chunked(update, fmt.format_huge_logs(files), **_kw)
        await save_command(user_id, "/dlogs", f"{len(files)} logs")
    except Exception as e:
        logger.exception("dlogs_command")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


@require_auth
@rate_limit
async def dhealth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await reply_text_safe(update, "🏥 Building health report…", **_kw)
    try:
        cpu = get_cpu_stats()
        mem = get_memory_stats()
        swap = mem.get("swap", {})
        disks = get_disk_stats()
        df = dss.docker_system_df()
        uptime = get_uptime()
        temps = get_temperatures()
        temp_vals = [float(t) for t in temps.values() if t is not None]
        temp_max = max(temp_vals) if temp_vals else None
        failed = run_profile("systemctl_failed")
        running, stopped = dss.count_containers()
        msg = fmt.format_dhealth(
            float(cpu.get("percent", 0)),
            float(mem.get("percent", 0)),
            float(swap.get("percent", 0)),
            disks,
            df.stdout,
            int(uptime.get("uptime_seconds", 0)),
            temp_max,
            failed.stdout if not failed.error else failed.error or "",
            running,
            stopped,
        )
        await reply_text_chunked(update, msg, **_kw)
        await save_command(user_id, "/dhealth", "report")
    except Exception as e:
        logger.exception("dhealth_command")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


async def _build_scan_message():
    df = dss.docker_system_df()
    dfv = dss.docker_system_df(verbose=True)
    running, stopped = dss.count_containers()
    images = dss.list_images_with_usage()
    bundle = await asyncio.to_thread(ss.run_full_scan_bundle)
    est = await asyncio.to_thread(dss.estimate_safe_prune, False)
    bdu = dss.docker_builder_du()
    return fmt.format_scan_report(
        df.stdout,
        dfv.stdout,
        running,
        stopped,
        images,
        bundle,
        est,
        bdu.stdout,
    )


async def _dscan_job(bot, chat_id: int, user_id: int):
    t0 = time.time()
    try:
        msg = await _build_scan_message()
        await bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
        await save_command(user_id, "/dscan", "completed")
        try:
            df = dss.docker_system_df()
            disks = get_disk_stats()
            free_pcts = [100.0 - float(d.get("percent", 0)) for d in disks]
            disk_min_free = min(free_pcts) if free_pcts else None
            est = dss.estimate_safe_prune(False)
            await save_storage_snapshot(
                reclaimable_hint=f"{est.container_reclaim}+{est.image_reclaim}",
                disk_min_free_percent=disk_min_free,
                docker_df_excerpt=(df.stdout or "")[:500],
            )
        except Exception:
            logger.debug("storage snapshot save skipped", exc_info=True)
        logger.info("dscan completed in %.1fs user=%s", time.time() - t0, user_id)
    except Exception as e:
        logger.exception("dscan_job")
        await bot.send_message(chat_id, format_error_html(str(e)), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def dscan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await reply_text_safe(
        update,
        "🔍 <b>Storage scan started</b>\n\nThis may take a few minutes…",
        **_kw,
    )
    asyncio.create_task(_dscan_job(context.bot, chat_id, user_id))


@require_auth
@rate_limit
async def dprune_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await reply_text_safe(update, "🧹 Quick prune (dangling images + build cache)…", **_kw)
    try:
        result = await asyncio.to_thread(dss.run_quick_prune)
        logger.info("dprune user=%s steps=%s", user_id, len(result.steps))
        await reply_text_chunked(
            update, fmt.format_prune_result("Quick prune (/dprune)", result), **_kw
        )
        await save_command(user_id, "/dprune", "done")
    except Exception as e:
        logger.exception("dprune_command")
        await reply_text_safe(update, format_error_html(str(e)), **_kw)


@require_auth
@rate_limit
async def dclean_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dry_only = (
        config.DOCKER_CLEAN_DRY_RUN_DEFAULT
        or (context.args and context.args[0].lower() in ("dry", "dry-run", "estimate"))
    )
    est = await asyncio.to_thread(dss.estimate_safe_prune, False)
    text = (
        "🧹 <b>Safe Docker cleanup</b>\n\n"
        f"Estimated reclaimable: containers <code>{est.container_reclaim}</code>, "
        f"images <code>{est.image_reclaim}</code>, "
        f"build cache <code>{est.builder_reclaim}</code>\n\n"
        "Removes: stopped containers, unused images, build cache.\n"
        "<b>Never</b> removes volumes, bind mounts, or active containers.\n"
    )
    if dry_only:
        text += "\n<i>Dry-run only (no changes made).</i>"
        await reply_text_safe(update, text, **_kw)
        return
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Run cleanup",
                callback_data=callback_data_for_user(CB_DCLEAN_CONFIRM, user_id),
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=callback_data_for_user(CB_DCLEAN_CANCEL, user_id),
            ),
        ]
    ]
    await reply_text_safe(update, text, reply_markup=InlineKeyboardMarkup(keyboard), **_kw)


@require_auth
@rate_limit
async def daggressive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [
            InlineKeyboardButton(
                "⚠️ Continue",
                callback_data=callback_data_for_user(CB_DAGG_STEP1, user_id),
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=callback_data_for_user(CB_DAGG_CANCEL, user_id),
            ),
        ]
    ]
    await reply_text_safe(
        update,
        "⚠️ <b>Aggressive cleanup</b>\n\n"
        "Step 1 of 2: This can remove unused Docker networks and run "
        "<code>apt-get clean</code> on the host.\n\n"
        "<b>Volumes are still never removed automatically.</b>\n"
        "Log truncation is manual only.\n\n"
        "Continue only during a maintenance window.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        **_kw,
    )


async def handle_storage_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    if await reject_unauthorized_callback(query):
        return
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = query.message.chat_id if query.message else update.effective_chat.id

    for cancel_prefix in (CB_DCLEAN_CANCEL, CB_DAGG_CANCEL):
        uid, _ = parse_callback_user_id(data, cancel_prefix)
        if uid is not None:
            if uid != user_id:
                await query.edit_message_text(
                    "🚫 This confirmation is for another user.", parse_mode=ParseMode.HTML
                )
                return
            await query.edit_message_text("❌ Cancelled.", parse_mode=ParseMode.HTML)
            return

    uid, _ = parse_callback_user_id(data, CB_DCLEAN_CONFIRM)
    if uid is not None:
        if uid != user_id:
            await query.edit_message_text(
                "🚫 This confirmation is for another user.", parse_mode=ParseMode.HTML
            )
            return
        await query.edit_message_text("🧹 Running safe cleanup…", parse_mode=ParseMode.HTML)
        try:
            result = await asyncio.to_thread(dss.run_safe_prune, False)
            logger.info("dclean confirmed user=%s", user_id)
            text = fmt.format_prune_result("Safe cleanup complete", result)
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            await save_command(user_id, "/dclean", "confirmed")
        except Exception as e:
            logger.exception("dclean_confirm")
            await context.bot.send_message(
                chat_id, format_error_html(str(e)), parse_mode=ParseMode.HTML
            )
        return

    uid, _ = parse_callback_user_id(data, CB_DAGG_STEP1)
    if uid is not None:
        if uid != user_id:
            await query.edit_message_text(
                "🚫 This confirmation is for another user.", parse_mode=ParseMode.HTML
            )
            return
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ CONFIRM aggressive cleanup",
                    callback_data=callback_data_for_user(CB_DAGG_CONFIRM, user_id),
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data=callback_data_for_user(CB_DAGG_CANCEL, user_id),
                ),
            ]
        ]
        await query.edit_message_text(
            "⚠️ <b>Step 2 of 2</b>\n\n"
            "Confirm aggressive cleanup: safe prune + unused networks + apt cache.\n"
            "Volumes will NOT be pruned.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
        return

    uid, _ = parse_callback_user_id(data, CB_DAGG_CONFIRM)
    if uid is not None:
        if uid != user_id:
            await query.edit_message_text(
                "🚫 This confirmation is for another user.", parse_mode=ParseMode.HTML
            )
            return
        await query.edit_message_text("🧹 Running aggressive cleanup…", parse_mode=ParseMode.HTML)
        try:
            result = await asyncio.to_thread(dss.run_safe_prune, True)
            extra = await asyncio.to_thread(dss.run_aggressive_extras)
            apt = await asyncio.to_thread(run_profile, "apt_clean")
            result.steps.extend(extra)
            result.steps.append(("apt-get clean", apt))
            logger.info("daggressive confirmed user=%s", user_id)
            text = fmt.format_prune_result("Aggressive cleanup complete", result)
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            await save_command(user_id, "/daggressive", "confirmed")
        except Exception as e:
            logger.exception("daggressive_confirm")
            await context.bot.send_message(
                chat_id, format_error_html(str(e)), parse_mode=ParseMode.HTML
            )
        return


async def run_weekly_scan_report(bot) -> None:
    """Scheduled: DM allowed users a storage scan summary."""
    if not config.ALLOWED_USER_IDS:
        return
    try:
        from utils.telegram_reply import split_text_for_telegram

        msg = await _build_scan_message()
        body = "📋 <b>Weekly Docker storage scan</b>\n\n" + msg
        for uid in config.ALLOWED_USER_IDS:
            for part in split_text_for_telegram(body):
                await bot.send_message(uid, part, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error("weekly scan report failed: %s", e, exc_info=True)
