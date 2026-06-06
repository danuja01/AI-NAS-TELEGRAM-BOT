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
    if not (getattr(config, "SMTP_HOST", "") or "").strip():
        return False
    if not getattr(config, "EMAIL_ALERT_RECIPIENTS", None):
        return False
    return True


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
