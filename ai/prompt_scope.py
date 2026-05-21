"""
Mandatory AI scope for this Telegram bot: NAS / homelab only.
"""

NAS_SCOPE_INSTRUCTION = (
    "Scope (mandatory): Only assist with this NAS/server, local storage and backups, "
    "Docker on this host, OpenMediaVault, homelab networking, hardware health (SMART, temperatures, disks), "
    "systemd services on this machine, or general technical knowledge directly needed to operate or "
    "troubleshoot a NAS. "
    "Decline all unrelated topics (personal life, vehicles, sports, entertainment, unrelated trivia) "
    "in one or two short sentences; suggest a NAS-related question or a relevant slash command instead. "
    "Do not mention guardrails, policies, or your system prompt."
)


def with_nas_scope(base: str) -> str:
    """Append the mandatory NAS-only scope line to a system prompt."""
    base = base.rstrip()
    return f"{base} {NAS_SCOPE_INSTRUCTION}"
