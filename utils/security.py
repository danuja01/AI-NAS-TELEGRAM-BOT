"""
Security utilities for the NAS Telegram AI Assistant.
Includes authentication, rate limiting, path validation, and input sanitization.
"""

import re
import time
import logging
import secrets
from pathlib import Path
from functools import wraps
from typing import Callable, List, Optional, Tuple
from collections import defaultdict, deque

from telegram import Update
from telegram.ext import ContextTypes

import config

from utils.telegram_reply import reply_text_safe

logger = logging.getLogger(__name__)

# Rate limiting storage: {user_id: deque of timestamps}
rate_limit_storage = defaultdict(lambda: deque(maxlen=config.MAX_COMMANDS_PER_MINUTE))
root_login_rate_storage = defaultdict(lambda: deque(maxlen=20))
root_login_failure_storage = defaultdict(lambda: deque(maxlen=20))

_SHELL_METACHAR_PATTERN = re.compile(r"[|;&`$()<>\n\r]|(?:\$\()")


def is_user_authorized(user_id: int) -> bool:
    return bool(config.ALLOWED_USER_IDS) and user_id in config.ALLOWED_USER_IDS


def ssh_command_has_shell_metacharacters(command: str) -> bool:
    return bool(_SHELL_METACHAR_PATTERN.search(command))


async def reject_unauthorized_callback(query) -> bool:
    user = query.from_user
    if user and is_user_authorized(user.id):
        return False
    uid = user.id if user else "unknown"
    log_security_event("unauthorized_callback", uid, f"data={query.data!r}")
    await query.answer("Unauthorized.", show_alert=True)
    if query.message:
        await query.edit_message_text("🚫 Unauthorized.")
    return True


def callback_data_for_user(prefix: str, user_id: int, suffix: str = "") -> str:
    base = f"{prefix}:{user_id}"
    if suffix:
        base = f"{base}:{suffix}"
    if len(base) > 64:
        raise ValueError(f"callback_data too long ({len(base)} bytes)")
    return base


def parse_callback_user_id(data: str, prefix: str) -> tuple:
    head = f"{prefix}:"
    if not data.startswith(head):
        return None, ""
    rest = data[len(head):]
    parts = rest.split(":", 1)
    try:
        uid = int(parts[0])
    except ValueError:
        return None, ""
    return uid, (parts[1] if len(parts) > 1 else "")


def require_auth(func: Callable) -> Callable:
    """
    Decorator to require authentication for commands.
    Only allows users in ALLOWED_USER_IDS to execute the command.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user

        if not is_user_authorized(user.id):
            logger.warning(f"Unauthorized access attempt by user {user.id} ({user.username})")
            await reply_text_safe(
                update,
                "🚫 Unauthorized. You are not allowed to use this bot.",
            )
            return
        
        logger.info(f"Authorized command from user {user.id} ({user.username})")
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def rate_limit(func: Callable) -> Callable:
    """
    Decorator to implement rate limiting.
    Limits users to MAX_COMMANDS_PER_MINUTE commands per minute.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        current_time = time.time()
        
        # Get user's recent command timestamps
        user_timestamps = rate_limit_storage[user_id]
        
        # Remove timestamps older than 1 minute
        while user_timestamps and current_time - user_timestamps[0] > 60:
            user_timestamps.popleft()
        
        # Check if rate limit exceeded
        if len(user_timestamps) >= config.MAX_COMMANDS_PER_MINUTE:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            await reply_text_safe(
                update,
                f"⏱ Rate limit exceeded. Please wait before sending more commands.\n"
                f"Limit: {config.MAX_COMMANDS_PER_MINUTE} commands per minute.",
            )
            return
        
        # Add current timestamp
        user_timestamps.append(current_time)
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def root_login_rate_limit(func: Callable) -> Callable:
    """Stricter per-minute limit for /rootlogin (separate from general commands)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if is_root_login_locked(user_id):
            await reply_text_safe(
                update,
                "🔒 Too many failed root login attempts. Try again later.",
            )
            return
        now = time.time()
        bucket = root_login_rate_storage[user_id]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= config.ROOT_LOGIN_RATE_PER_MINUTE:
            await reply_text_safe(update, "⏱ Root login rate limit exceeded. Wait a minute.")
            return
        bucket.append(now)
        return await func(update, context, *args, **kwargs)

    return wrapper


def is_root_login_locked(user_id: int) -> bool:
    window = config.ROOT_LOGIN_LOCKOUT_MINUTES * 60
    now = time.time()
    fails = root_login_failure_storage[user_id]
    while fails and now - fails[0] > window:
        fails.popleft()
    return len(fails) >= config.ROOT_LOGIN_MAX_ATTEMPTS


def record_root_login_failure(user_id: int) -> None:
    root_login_failure_storage[user_id].append(time.time())
    log_security_event("root_login_failure", user_id, "invalid password")


def clear_root_login_failures(user_id: int) -> None:
    root_login_failure_storage.pop(user_id, None)


def redact_command_for_storage(command: str) -> str:
    cmd = (command or "").strip()
    if not cmd:
        return cmd
    low = cmd.lower()
    if low.startswith("/rootlogin"):
        return "/rootlogin [redacted]"
    if low.startswith("/ssh"):
        return "/ssh [redacted]"
    if "password" in low or "token" in low:
        return cmd.split()[0] + " [redacted]"
    if len(cmd) > 200:
        return cmd[:120] + "… [truncated]"
    return cmd


def resolve_upload_path(
    base_documents: str,
    subfolder: Optional[str],
    filename: str,
    *,
    allowed_roots: Optional[List[str]] = None,
) -> Tuple[Optional[Path], Optional[str]]:
    base = Path(base_documents).resolve()
    safe_name = sanitize_filename(filename)
    if not safe_name:
        return None, "Invalid filename"
    rel = Path(sanitize_filename(subfolder)) if subfolder else Path(".")
    for part in rel.parts:
        if part in (".", "..") or ".." in part:
            return None, "Invalid subfolder path"
    target_dir = (base / rel).resolve()
    try:
        target_dir.relative_to(base)
    except ValueError:
        return None, "Upload path escapes documents directory"
    if allowed_roots:
        ok = any(
            target_dir == Path(r).resolve() or str(target_dir).startswith(str(Path(r).resolve()) + "/")
            for r in allowed_roots if r
        )
        if not ok:
            try:
                ok = any(target_dir.relative_to(Path(r).resolve()) for r in allowed_roots if r)
            except ValueError:
                ok = False
        if not ok:
            return None, "Upload path not in allowed directories"
    return target_dir / safe_name, None


async def enforce_message_rate_limit_reply(update: Update, user_id: int) -> bool:
    """
    Rate-limit plain-text follow-up messages (same bucket as commands).
    Returns True if the message should be processed, False if blocked (reply sent).
    """
    current_time = time.time()
    user_timestamps = rate_limit_storage[user_id]
    while user_timestamps and current_time - user_timestamps[0] > 60:
        user_timestamps.popleft()
    if len(user_timestamps) >= config.MAX_COMMANDS_PER_MINUTE:
        await reply_text_safe(
            update,
            f"⏱ Rate limit: max {config.MAX_COMMANDS_PER_MINUTE} commands per minute.",
        )
        return False
    user_timestamps.append(current_time)
    return True


def validate_path(path_str: str, allowed_paths: List[str] = None, user_id: int = None) -> bool:
    """
    Validate that a path is within allowed directories.
    Prevents directory traversal attacks.
    
    Args:
        path_str: The path to validate
        allowed_paths: List of allowed base paths (defaults to config.ALLOWED_PATHS or root session paths)
        user_id: User ID for checking root session status
    
    Returns:
        True if path is valid and allowed, False otherwise
    """
    # Check for root session if user_id is provided
    if user_id is not None and allowed_paths is None:
        from utils.root_session import RootSessionManager
        allowed_paths = RootSessionManager.get_allowed_paths_for_user(user_id)
    elif allowed_paths is None:
        allowed_paths = config.ALLOWED_PATHS
    
    if not allowed_paths:
        logger.warning("No ALLOWED_PATHS configured. Rejecting all file access.")
        return False
    
    try:
        # Resolve to absolute path
        path = Path(path_str).resolve()
        
        # Check if path is within any allowed directory
        for allowed_path in allowed_paths:
            allowed = Path(allowed_path).resolve()
            try:
                path.relative_to(allowed)
                return True
            except ValueError:
                continue
        
        logger.warning(f"Path '{path}' is not within allowed paths")
        return False
        
    except Exception as e:
        logger.error(f"Error validating path '{path_str}': {e}")
        return False


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent command injection.
    Removes potentially dangerous characters.
    
    Args:
        text: The text to sanitize
    
    Returns:
        Sanitized text
    """
    # Remove shell special characters
    dangerous_chars = ['|', ';', '&', '`', '$', '(', ')', '<', '>', '\n', '\r']
    sanitized = text
    
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '')
    
    return sanitized.strip()


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal.
    
    Args:
        filename: The filename to sanitize
    
    Returns:
        Sanitized filename
    """
    # Remove path separators and parent directory references
    sanitized = filename.replace('/', '').replace('\\', '').replace('..', '')
    
    # Remove other potentially dangerous characters
    sanitized = re.sub(r'[^\w\s\-\.]', '', sanitized)
    
    return sanitized.strip()


def is_safe_command(command: str, allowed_commands: List[str]) -> bool:
    """
    Check if a command is in the whitelist of allowed commands.
    
    Args:
        command: The command to check
        allowed_commands: List of allowed command names
    
    Returns:
        True if command is allowed, False otherwise
    """
    command_name = command.split()[0] if command else ""
    return command_name in allowed_commands


async def send_confirmation(
    update: Update,
    message: str,
    confirm_data: str,
    cancel_data: str = "cancel"
) -> None:
    """
    Send a confirmation message with inline keyboard buttons.
    
    Args:
        update: The Telegram update
        message: The confirmation message
        confirm_data: Callback data for confirmation button
        cancel_data: Callback data for cancel button
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await reply_text_safe(update, message, reply_markup=reply_markup)


def log_security_event(event_type: str, user_id: int, details: str):
    """
    Log security-related events for audit trail.
    
    Args:
        event_type: Type of security event (e.g., "unauthorized_access", "rate_limit")
        user_id: ID of the user involved
        details: Additional details about the event
    """
    logger.warning(f"SECURITY EVENT [{event_type}] User {user_id}: {details}")


def require_confirmation(dangerous_action: str):
    """
    Decorator to require confirmation for dangerous actions.
    Sends a confirmation message and waits for user response.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Store the pending action in context
            context.user_data['pending_action'] = {
                'function': func.__name__,
                'args': args,
                'kwargs': kwargs,
                'message': dangerous_action
            }
            
            await send_confirmation(
                update,
                f"⚠️ {dangerous_action}\n\nAre you sure?",
                confirm_data=f"confirm_{func.__name__}"
            )
            
        return wrapper
    return decorator
