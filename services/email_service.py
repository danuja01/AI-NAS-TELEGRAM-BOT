"""
SMTP email alerts for NAS power actions (reboot / shutdown).
"""

from __future__ import annotations

import logging
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple

import config

logger = logging.getLogger(__name__)

_POWER_ACTIONS = frozenset({"reboot", "shutdown"})
_PENDING_ACTION_FILE = config.DATA_DIR / "email_pending_power_action.txt"


def _nas_display_name() -> str:
    name = (getattr(config, "NAS_DISPLAY_NAME", None) or "").strip()
    if name:
        return name
    try:
        return socket.gethostname() or "NAS"
    except Exception:
        return "NAS"


def email_alerts_configured() -> bool:
    if not getattr(config, "EMAIL_ALERTS_ENABLED", False):
        return False
    return smtp_ready()


def smtp_ready() -> bool:
    if not (getattr(config, "SMTP_HOST", "") or "").strip():
        return False
    if not getattr(config, "EMAIL_ALERT_RECIPIENTS", None):
        return False
    return True


def allowed_alert_recipient(email: str) -> Optional[str]:
    """Return canonical recipient if ``email`` is listed in EMAIL_ALERT_RECIPIENTS."""
    needle = (email or "").strip().lower()
    if not needle or "@" not in needle:
        return None
    for addr in config.EMAIL_ALERT_RECIPIENTS:
        if addr.strip().lower() == needle:
            return addr.strip()
    return None


def _build_reboot_content(host: str, initiated_by: str, when: str) -> Tuple[str, str, str]:
    subject = f"[{host}] System reboot in progress"
    plain = (
        f"NAS reboot notice — {host}\n\n"
        "A system reboot will be performed to update the system.\n"
        "Expected downtime: approximately 3–5 minutes.\n\n"
        f"Initiated by: {initiated_by}\n"
        f"Time (UTC): {when}\n"
    )
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.08);">
        <tr><td style="background:linear-gradient(135deg,#2563eb,#1d4ed8);padding:28px 32px;color:#ffffff;">
          <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">NAS Alert</div>
          <div style="font-size:24px;font-weight:700;margin-top:8px;">System Reboot</div>
          <div style="font-size:15px;margin-top:6px;opacity:0.95;">{host}</div>
        </td></tr>
        <tr><td style="padding:32px;color:#0f172a;">
          <p style="margin:0 0 16px;font-size:16px;line-height:1.6;">
            A <strong>system reboot</strong> will be performed to update the system.
          </p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;margin:0 0 20px;">
            <tr><td style="padding:16px 18px;font-size:15px;line-height:1.5;color:#1e3a8a;">
              ⏱ <strong>Expected downtime:</strong> approximately <strong>3–5 minutes</strong>.<br>
              Services will be unavailable until the NAS is back online.
            </td></tr>
          </table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:14px;color:#475569;">
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Initiated by:</strong> {initiated_by}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Time (UTC):</strong> {when}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 32px;background:#f8fafc;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0;">
          Automated message from your NAS Telegram assistant. No reply is required.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, plain, html


def _build_shutdown_content(host: str, initiated_by: str, when: str) -> Tuple[str, str, str]:
    subject = f"[{host}] Planned shutdown for maintenance"
    plain = (
        f"NAS shutdown notice — {host}\n\n"
        "Shutdown will be performed for maintenance.\n"
        "Expect downtime until the system is brought back online.\n"
        "If you need access, please contact the administrator.\n\n"
        f"Initiated by: {initiated_by}\n"
        f"Time (UTC): {when}\n"
    )
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.08);">
        <tr><td style="background:linear-gradient(135deg,#b45309,#92400e);padding:28px 32px;color:#ffffff;">
          <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">NAS Alert</div>
          <div style="font-size:24px;font-weight:700;margin-top:8px;">Planned Shutdown</div>
          <div style="font-size:15px;margin-top:6px;opacity:0.95;">{host}</div>
        </td></tr>
        <tr><td style="padding:32px;color:#0f172a;">
          <p style="margin:0 0 16px;font-size:16px;line-height:1.6;">
            <strong>Shutdown will be performed for maintenance.</strong>
          </p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;margin:0 0 20px;">
            <tr><td style="padding:16px 18px;font-size:15px;line-height:1.5;color:#9a3412;">
              ⚠️ <strong>Expect downtime</strong> until the NAS is powered on again.<br>
              If you need access during this window, please <strong>contact the administrator</strong>.
            </td></tr>
          </table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:14px;color:#475569;">
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Initiated by:</strong> {initiated_by}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Time (UTC):</strong> {when}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 32px;background:#f8fafc;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0;">
          Automated message from your NAS Telegram assistant. No reply is required.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, plain, html


def _build_message(action: str, initiated_by: str) -> Tuple[str, str, str]:
    host = _escape_html(_nas_display_name())
    who = _escape_html(initiated_by or "System")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if action == "reboot":
        return _build_reboot_content(host, who, when)
    return _build_shutdown_content(host, who, when)


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _smtp_from_address() -> str:
    configured = (getattr(config, "SMTP_FROM", None) or "").strip()
    if configured:
        return configured
    user = (getattr(config, "SMTP_USER", None) or "").strip()
    if user:
        return user
    return f"nas-alerts@{_nas_display_name()}"


def _send_message(subject: str, plain: str, html: str, recipients: List[str]) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _smtp_from_address()
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    host = config.SMTP_HOST.strip()
    port = int(getattr(config, "SMTP_PORT", 587))
    user = (getattr(config, "SMTP_USER", None) or "").strip()
    password = getattr(config, "SMTP_PASSWORD", None) or ""
    use_ssl = bool(getattr(config, "SMTP_USE_SSL", False))
    use_tls = bool(getattr(config, "SMTP_USE_TLS", True))

    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    try:
        server.ehlo()
        if use_tls and not use_ssl:
            server.starttls()
            server.ehlo()
        if user:
            server.login(user, password)
        server.sendmail(_smtp_from_address(), recipients, msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _build_smtp_test_content(host: str, to: str, initiated_by: str, when: str) -> Tuple[str, str, str]:
    subject = f"[{host}] SMTP test — email alerts OK"
    plain = (
        f"SMTP test — {host}\n\n"
        "This is a test message from your NAS Telegram assistant.\n"
        "If you received it, reboot/shutdown email alerts are configured correctly.\n\n"
        f"Sent to: {to}\n"
        f"Requested by: {initiated_by}\n"
        f"Time (UTC): {when}\n"
    )
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.08);">
        <tr><td style="background:linear-gradient(135deg,#059669,#047857);padding:28px 32px;color:#ffffff;">
          <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">SMTP Test</div>
          <div style="font-size:24px;font-weight:700;margin-top:8px;">Email alerts configured</div>
          <div style="font-size:15px;margin-top:6px;opacity:0.95;">{host}</div>
        </td></tr>
        <tr><td style="padding:32px;color:#0f172a;">
          <p style="margin:0 0 16px;font-size:16px;line-height:1.6;">
            This is a <strong>test message</strong> from your NAS Telegram assistant.
            If you received it, SMTP settings for reboot/shutdown alerts are working.
          </p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:14px;color:#475569;">
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Sent to:</strong> {to}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Requested by:</strong> {initiated_by}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Time (UTC):</strong> {when}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 32px;background:#f8fafc;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0;">
          Automated test from /smtptest. No reply is required.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, plain, html


def record_pending_power_action(action: str) -> None:
    action = (action or "").strip().lower()
    if action not in _POWER_ACTIONS:
        return
    try:
        _PENDING_ACTION_FILE.write_text(action, encoding="utf-8")
    except OSError as e:
        logger.warning("Could not record pending power action: %s", e)


def pop_pending_power_action() -> Optional[str]:
    try:
        if not _PENDING_ACTION_FILE.is_file():
            return None
        action = _PENDING_ACTION_FILE.read_text(encoding="utf-8").strip().lower()
        _PENDING_ACTION_FILE.unlink(missing_ok=True)
        return action if action in _POWER_ACTIONS else None
    except OSError as e:
        logger.warning("Could not read pending power action: %s", e)
        return None


def _format_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _build_back_online_content(
    host: str,
    boot_dt: str,
    prev_boot_dt: str,
    uptime_label: str,
    reason_html: str,
    reason_plain: str,
) -> Tuple[str, str, str]:
    subject = f"[{host}] NAS is back online"
    plain = (
        f"NAS back online — {host}\n\n"
        f"{reason_plain}\n\n"
        f"Current boot: {boot_dt}\n"
        f"Previous boot: {prev_boot_dt}\n"
        f"Uptime: {uptime_label}\n"
    )
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.08);">
        <tr><td style="background:linear-gradient(135deg,#16a34a,#15803d);padding:28px 32px;color:#ffffff;">
          <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;opacity:0.9;">NAS Alert</div>
          <div style="font-size:24px;font-weight:700;margin-top:8px;">Back Online</div>
          <div style="font-size:15px;margin-top:6px;opacity:0.95;">{host}</div>
        </td></tr>
        <tr><td style="padding:32px;color:#0f172a;">
          <p style="margin:0 0 16px;font-size:16px;line-height:1.6;">
            {reason_html}
          </p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;margin:0 0 20px;">
            <tr><td style="padding:16px 18px;font-size:15px;line-height:1.5;color:#166534;">
              ✅ The NAS is running again and services are coming back online.
            </td></tr>
          </table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:14px;color:#475569;">
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Current boot:</strong> {boot_dt}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Previous boot:</strong> {prev_boot_dt}</td></tr>
            <tr><td style="padding:8px 0;border-top:1px solid #e2e8f0;"><strong>Uptime:</strong> {uptime_label}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:18px 32px;background:#f8fafc;font-size:12px;color:#64748b;border-top:1px solid #e2e8f0;">
          Automated message from your NAS Telegram assistant. No reply is required.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, plain, html


def send_back_online_alert(
    *,
    boot_time: int,
    previous_boot_time: int,
    uptime_seconds: int,
) -> bool:
    """
    Email configured recipients when the NAS comes back after reboot/shutdown.
    """
    if not email_alerts_configured():
        return False

    pending = pop_pending_power_action()
    if pending == "reboot":
        reason = (
            "Your NAS has <strong>finished rebooting</strong> and is back online. "
            "Services should be fully available within a few minutes."
        )
        reason_plain = (
            "Your NAS has finished rebooting and is back online. "
            "Services should be fully available within a few minutes."
        )
    elif pending == "shutdown":
        reason = (
            "Your NAS is <strong>back online</strong> after a planned maintenance shutdown."
        )
        reason_plain = "Your NAS is back online after a planned maintenance shutdown."
    else:
        reason = (
            "Your NAS is <strong>back online</strong>. "
            "A system restart was detected."
        )
        reason_plain = "Your NAS is back online. A system restart was detected."

    host = _escape_html(_nas_display_name())
    boot_dt = _escape_html(
        datetime.fromtimestamp(boot_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    prev_dt = _escape_html(
        datetime.fromtimestamp(previous_boot_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    uptime_label = _escape_html(_format_uptime(uptime_seconds))
    subject, plain, html = _build_back_online_content(
        host,
        boot_dt,
        prev_dt,
        uptime_label,
        reason,
        reason_plain,
    )
    recipients = list(config.EMAIL_ALERT_RECIPIENTS)
    try:
        _send_message(subject, plain, html, recipients)
        logger.info(
            "Back-online email sent to %d recipient(s) (pending=%s)",
            len(recipients),
            pending or "none",
        )
        return True
    except Exception as e:
        logger.error("Failed to send back-online email: %s", e)
        return False


def send_smtp_test_email(to: str, *, initiated_by: str = "Telegram") -> None:
    """
    Send a test email to one configured recipient.

    Raises ValueError for validation errors; smtplib/OS errors on send failure.
    """
    if not smtp_ready():
        raise ValueError(
            "SMTP is not configured. Set SMTP_HOST and EMAIL_ALERT_RECIPIENTS in .env."
        )
    recipient = allowed_alert_recipient(to)
    if not recipient:
        allowed = ", ".join(config.EMAIL_ALERT_RECIPIENTS) or "(none)"
        raise ValueError(
            f"`{to}` is not in EMAIL_ALERT_RECIPIENTS. Allowed: {allowed}"
        )

    host = _escape_html(_nas_display_name())
    who = _escape_html(initiated_by or "Telegram")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    to_html = _escape_html(recipient)
    subject, plain, html = _build_smtp_test_content(host, to_html, who, when)
    _send_message(subject, plain, html, [recipient])
    logger.info("SMTP test email sent to %s (requested by %s)", recipient, initiated_by)


def send_power_action_alert(action: str, *, initiated_by: str = "System") -> bool:
    """
    Email configured recipients before a reboot or shutdown.

    Returns True if at least one message was sent successfully.
    """
    action = (action or "").strip().lower()
    if action not in _POWER_ACTIONS:
        logger.warning("send_power_action_alert: unknown action %r", action)
        return False
    if not email_alerts_configured():
        logger.debug("Email alerts disabled or incomplete SMTP config; skipping %s alert", action)
        return False

    recipients = list(config.EMAIL_ALERT_RECIPIENTS)
    subject, plain, html = _build_message(action, initiated_by)
    try:
        _send_message(subject, plain, html, recipients)
        record_pending_power_action(action)
        logger.info(
            "Power-action email sent (%s) to %d recipient(s), initiated_by=%s",
            action,
            len(recipients),
            initiated_by,
        )
        return True
    except Exception as e:
        logger.error("Failed to send %s email alert: %s", action, e)
        return False
