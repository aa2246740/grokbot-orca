"""Pure Orca-domain helpers: workers, fresh repos, pane rows, Stop-hook status."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .cli import Envelope, Runner, orca_json, record

AGENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bantigravity\b|\bagy\b", re.I), "antigravity"),
    (re.compile(r"\bclaude(?:[\s-]*code)?\b", re.I), "claude"),
    (re.compile(r"\bcodex\b", re.I), "codex"),
    (re.compile(r"\bcursor\b", re.I), "cursor"),
    (re.compile(r"\bgrok\b|\bxai\b", re.I), "grok"),
)

STAY = re.compile(
    r"就在这|当前目录|这个文件夹|不要新开|原地改|就在这儿|"
    r"\bin this (?:folder|directory)\b|\bstay (?:here|in place)\b|"
    r"\bcurrent (?:folder|directory)\b|\bin-place\b|don'?t create a new",
    re.I,
)

WORKER_IDS = ("grok", "codex", "claude", "cursor", "antigravity")


def stay_in_place(prompt: str) -> bool:
    return bool(STAY.search(prompt or ""))


def agents_in(text: str | None) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for pattern, ident in AGENT_PATTERNS:
        if pattern.search(text) and ident not in found:
            found.append(ident)
    return found


def infer_agent(agent: str | None, prompt: str) -> str | None:
    direct = (agent or "").strip()
    if direct:
        named = agents_in(direct)
        if len(named) == 1:
            return named[0]
        compact = re.sub(r"\s+", " ", direct.lower())
        if compact == "agy":
            return "antigravity"
        if compact in WORKER_IDS:
            return compact
    from_prompt = agents_in(prompt)
    if len(from_prompt) == 1:
        return from_prompt[0]
    return None


def launch_command(agent: str) -> str:
    return "agy" if agent == "antigravity" else agent


def task_name(name: str | None, prompt: str) -> str:
    given = (name or "").strip()
    if given:
        return given[:80]
    slug = re.sub(r"https?://\S+", "", prompt.lower())
    slug = re.sub(r"[^\w.-]+", "-", slug, flags=re.UNICODE)
    slug = slug.strip("-")[:40]
    return slug or f"grokbot-{int(time.time())}"


def projects_root() -> Path:
    override = os.environ.get("GROKBOT_ORCA_PROJECTS")
    if override:
        return Path(override)
    return Path.home() / "orca" / "projects"


def create_fresh_repo(name: str) -> str:
    from subprocess import run

    base = projects_root()
    base.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w.-]+", "-", name).strip("-")[:40] or f"grokbot-{int(time.time()):x}"
    directory = base / slug
    if directory.exists():
        directory = base / f"{slug}-{int(time.time()):x}"
    directory.mkdir(parents=True, exist_ok=True)
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "grokbot-orca",
        "GIT_AUTHOR_EMAIL": "grokbot-orca@local",
        "GIT_COMMITTER_NAME": "grokbot-orca",
        "GIT_COMMITTER_EMAIL": "grokbot-orca@local",
    }
    run(["git", "init"], cwd=directory, check=True, capture_output=True)
    run(
        ["git", "commit", "--allow-empty", "-m", "grokbot-orca dispatch"],
        cwd=directory,
        check=True,
        capture_output=True,
        env=git_env,
    )
    return str(directory)


def is_record(value: Any) -> bool:
    return isinstance(value, dict)


def worktrees_of(result: Any) -> list[dict[str, Any]]:
    rec = record(result)
    listing = rec.get("worktrees") if rec else None
    if not isinstance(listing, list):
        return []
    return [row for row in listing if is_record(row)]


def project_row(row: dict[str, Any]) -> dict[str, Any]:
    agents = [item for item in row.get("agents", []) if is_record(item)] if isinstance(row.get("agents"), list) else []
    primary = agents[0] if agents else {}
    return {
        "worktreeId": row.get("worktreeId"),
        "displayName": row.get("displayName"),
        "path": row.get("path"),
        "repo": row.get("repo"),
        "branch": row.get("branch"),
        "comment": row.get("comment") or "",
        "workspaceStatus": row.get("workspaceStatus"),
        "runStatus": primary.get("state") if primary else row.get("status"),
        "interrupted": bool(primary.get("interrupted")) if primary else False,
        "agentType": primary.get("agentType") if primary else None,
        "lastAssistantMessage": primary.get("lastAssistantMessage") if primary else None,
        "liveTerminalCount": row.get("liveTerminalCount") or 0,
        "lastActivityAt": row.get("lastActivityAt"),
        "unread": row.get("unread"),
        "agents": [
            {
                "paneKey": agent.get("paneKey"),
                "agentType": agent.get("agentType"),
                "state": agent.get("state"),
                "interrupted": bool(agent.get("interrupted")),
                "lastAssistantMessage": agent.get("lastAssistantMessage"),
                "prompt": agent.get("prompt"),
            }
            for agent in agents
        ],
    }


def match_worktree(row: dict[str, Any], selector: str) -> bool:
    ident = str(row.get("worktreeId") or "")
    name = str(row.get("displayName") or "")
    path = str(row.get("path") or "")
    return selector in (ident, name, path) or ident.endswith(selector)


def pick_worktree(rows: list[dict[str, Any]], selector: str) -> dict[str, Any] | None:
    return next((row for row in rows if match_worktree(row, selector)), None)


def latest_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: _activity_ts(row))


def _activity_ts(row: dict[str, Any]) -> float:
    raw = str(row.get("lastActivityAt") or "")
    if not raw:
        return 0.0
    from datetime import datetime

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def pick_row(rows: list[dict[str, Any]], worktree: str | None) -> dict[str, Any] | None:
    if worktree and worktree.strip():
        found = pick_worktree(rows, worktree.strip())
        if found:
            return found
    return latest_row(rows)


def hook_run_status(row: dict[str, Any] | None) -> str:
    if not row:
        return "unknown"
    agents = [item for item in row.get("agents", []) if is_record(item)] if isinstance(row.get("agents"), list) else []
    if any(agent.get("interrupted") is True for agent in agents):
        return "interrupted"
    if any(agent.get("state") == "done" for agent in agents):
        return "done"
    if any(agent.get("state") in ("working", "blocked", "waiting") for agent in agents):
        return "working"
    return "unknown"


def pane_row(worktree: dict[str, Any], agent: dict[str, Any] | None) -> dict[str, Any]:
    row = {
        "displayName": worktree.get("displayName"),
        "repo": worktree.get("repo"),
        "path": worktree.get("path"),
        "worktreeId": worktree.get("worktreeId"),
        "workspaceStatus": worktree.get("workspaceStatus"),
        "worktreeStatus": worktree.get("status"),
        "unread": worktree.get("unread"),
        "comment": worktree.get("comment") or "",
        "liveTerminalCount": worktree.get("liveTerminalCount"),
        "paneKey": None,
        "agentType": None,
        "state": None,
        "interrupted": False,
        "prompt": None,
        "taskTitle": None,
        "lastAssistantMessage": None,
        "stateStartedAt": None,
        "updatedAt": None,
        "toolName": None,
    }
    if agent:
        row.update(
            {
                "paneKey": agent.get("paneKey"),
                "agentType": agent.get("agentType"),
                "state": agent.get("state"),
                "interrupted": bool(agent.get("interrupted")),
                "prompt": agent.get("prompt"),
                "taskTitle": agent.get("taskTitle"),
                "lastAssistantMessage": agent.get("lastAssistantMessage"),
                "stateStartedAt": agent.get("stateStartedAt"),
                "updatedAt": agent.get("updatedAt"),
                "toolName": agent.get("toolName"),
            }
        )
    return row


def _blob(*parts: Any) -> str:
    return " ".join(str(part) for part in parts if part is not None).lower()


def ps_matches(query: str, worktree: dict[str, Any], agent: dict[str, Any] | None) -> bool:
    if not query:
        return True
    hay = _blob(
        worktree.get("displayName"),
        worktree.get("repo"),
        worktree.get("path"),
        worktree.get("worktreeId"),
        worktree.get("branch"),
        worktree.get("comment"),
    )
    if agent:
        hay = _blob(
            hay,
            agent.get("paneKey"),
            agent.get("agentType"),
            agent.get("prompt"),
            agent.get("taskTitle"),
            agent.get("lastAssistantMessage"),
        )
    return query in hay


def filter_panes(
    worktrees: list[dict[str, Any]],
    query: str = "",
    state: str = "",
) -> list[dict[str, Any]]:
    q = query.lower()
    st = state.lower()
    panes: list[dict[str, Any]] = []
    for worktree in worktrees:
        agents = [item for item in worktree.get("agents", []) if is_record(item)] if isinstance(worktree.get("agents"), list) else []
        if not agents:
            if st:
                continue
            if ps_matches(q, worktree, None):
                panes.append(pane_row(worktree, None))
            continue
        for agent in agents:
            if st and str(agent.get("state") or "").lower() != st:
                continue
            if not ps_matches(q, worktree, agent):
                continue
            panes.append(pane_row(worktree, agent))
    return panes


def pick_handle(result: Any) -> dict[str, str] | dict[str, str]:
    rec = record(result) or {}
    worktree = record(rec.get("worktree")) or {}
    agent_id = ""
    if isinstance(worktree.get("id"), str) and worktree["id"]:
        agent_id = worktree["id"]
    elif isinstance(rec.get("worktreeId"), str) and rec["worktreeId"]:
        agent_id = rec["worktreeId"]
    startup = record(rec.get("startupTerminal")) or {}
    run_id = ""
    if isinstance(rec.get("agentTerminalHandle"), str) and rec["agentTerminalHandle"]:
        run_id = rec["agentTerminalHandle"]
    elif isinstance(startup.get("handle"), str) and startup["handle"]:
        run_id = startup["handle"]
    elif isinstance(rec.get("handle"), str) and rec["handle"]:
        run_id = rec["handle"]
    if not agent_id and not run_id:
        return {"error": "orca launch returned no worktree or terminal id"}
    return {"agentId": agent_id or run_id, "runId": run_id or agent_id}


def pick_terminal_handle(result: Any) -> str | None:
    rec = record(result) or {}
    listing = rec.get("terminals")
    rows = [item for item in listing if is_record(item)] if isinstance(listing, list) else []
    live = [row for row in rows if row.get("orphaned") is not True and isinstance(row.get("handle"), str)]
    writable = next((row for row in live if row.get("writable") is not False), None)
    picked = writable or (live[0] if live else None)
    handle = picked.get("handle") if picked else None
    return handle if isinstance(handle, str) else None


def abs_path_of(repo: str | None) -> str | None:
    raw = (repo or "").strip()
    if raw.startswith("path:"):
        path = raw[5:]
        return path if path.startswith("/") else None
    if raw.startswith("/"):
        return raw
    return None


def repo_selector(repo: str | None) -> str | None:
    raw = (repo or "").strip()
    if not raw:
        return None
    if raw.startswith(("path:", "id:", "name:")):
        return raw
    if raw.startswith("/"):
        return f"path:{raw}"
    return raw


def peek_files(abs_path: Any) -> list[str]:
    if not isinstance(abs_path, str) or not abs_path.startswith("/"):
        return []
    try:
        return [name for name in os.listdir(abs_path) if not name.startswith(".")][:24]
    except OSError:
        return []


def wait_for_hook_done(
    run: Runner,
    worktree: str,
    timeout_s: float = 45.0,
    poll_s: float | None = None,
) -> dict[str, Any]:
    budget = timeout_s if timeout_s > 0 else 45.0
    poll = poll_s if poll_s is not None else float(os.environ.get("GROKBOT_ORCA_POLL_S", "2"))
    started = time.time()
    last: dict[str, Any] | None = None
    while True:
        ps = orca_json(run, ["worktree", "ps"], 30.0)
        rows = worktrees_of(ps.result) if ps.ok else []
        last = pick_worktree(rows, worktree)
        status = hook_run_status(last)
        if status in ("done", "interrupted"):
            return {
                "status": status,
                "worktree": last,
                "files": peek_files((last or {}).get("path")),
                "via": "orca-agent-hooks",
            }
        elapsed = time.time() - started
        if last is None and elapsed > 15:
            return {"status": "gone", "worktree": None, "files": [], "via": "orca-agent-hooks"}
        if elapsed > budget:
            return {
                "status": "timeout",
                "worktree": last,
                "files": peek_files((last or {}).get("path")),
                "via": "orca-agent-hooks",
            }
        time.sleep(max(poll, 0.01))


def ensure_agent_hooks(run: Runner) -> dict[str, bool]:
    status = orca_json(run, ["agent", "hooks", "status"], 15.0)
    body = record(status.result) if status.ok else None
    if body and body.get("enabled") is True:
        return {"enabled": True}
    turned = orca_json(run, ["agent", "hooks", "on"], 20.0)
    return {"enabled": turned.ok}


def import_path(run: Runner, abs_path: str) -> dict[str, Any]:
    added = orca_json(run, ["repo", "add", "--path", abs_path], 30.0)
    if not added.ok:
        return {"ok": False, "code": added.error_code, "message": added.error_message}
    repo = record(added.result) or {}
    nested = record(repo.get("repo")) or repo
    return {
        "ok": True,
        "repoId": nested.get("id"),
        "path": nested.get("path") or abs_path,
        "displayName": nested.get("displayName"),
    }


def dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


def envelope_error(env: Envelope) -> dict[str, Any]:
    return {"ok": False, "code": env.error_code, "message": env.error_message}
