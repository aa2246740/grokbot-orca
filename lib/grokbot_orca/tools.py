"""MCP tool table. Product behavior from dsh-orca-agents + orca-bridge, over the local orca CLI."""

from __future__ import annotations

import os
import time
from typing import Any

from .cli import Binder, Runner, bind, default_runner, ensure_runtime, fail_payload, orca_json, record, resolve_cli
from .domain import (
    abs_path_of,
    create_fresh_repo,
    dumps,
    ensure_agent_hooks,
    envelope_error,
    filter_panes,
    hook_run_status,
    import_path,
    infer_agent,
    launch_command,
    peek_files,
    pick_handle,
    pick_row,
    pick_terminal_handle,
    project_row,
    repo_selector,
    stay_in_place,
    task_name,
    wait_for_hook_done,
    worktrees_of,
)
from .inbox import append_done, inbox_call

READ_DEFAULT_LIMIT = 200
READ_MAX_LIMIT = 2000
SUBMIT_DELAY_SEC = float(os.environ.get("GROKBOT_ORCA_SUBMIT_DELAY", "0.5"))
SUBMIT_RETRY_SEC = float(os.environ.get("GROKBOT_ORCA_SUBMIT_RETRY", "0.35"))


def _need(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing required argument: {key}")
    return value.strip()


def _optional_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _limit(args: dict[str, Any]) -> int:
    value = args.get("limit")
    if isinstance(value, bool) or not isinstance(value, int):
        return READ_DEFAULT_LIMIT
    return max(1, min(value, READ_MAX_LIMIT))


def _text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else dumps(payload)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _runner(runner: Runner | None) -> Runner:
    return runner or default_runner(resolve_cli())


def _ready(runner: Runner) -> Binder | dict[str, Any]:
    bound = bind(runner)
    if not bound.ok:
        return fail_payload(bound)
    live = ensure_runtime(runner, bound)
    if not live.ok:
        return fail_payload(live)
    return live


def _ps_rows(runner: Runner) -> list[dict[str, Any]]:
    ps = orca_json(runner, ["worktree", "ps"], 30.0)
    if not ps.ok:
        return []
    return [project_row(row) for row in worktrees_of(ps.result)]


def doctor(runner: Runner | None = None) -> dict[str, Any]:
    run = _runner(runner)
    bound = bind(run)
    payload: dict[str, Any] = {
        "ok": bound.ok,
        "cli": bound.cli,
        "appVersion": bound.app_version,
        "reachable": bound.reachable,
        "missing": list(bound.missing),
        "optionalMissing": list(bound.optional_missing),
        "capabilities": list(bound.capabilities),
        "code": bound.code or None,
        "message": bound.message or None,
        "topology": "mac-colocated",
        "note": (
            "This MCP must run on Cola's Mac next to Grok Bot desktop and Orca.app. "
            "Linux cloud cannot reach that orca CLI."
        ),
    }
    if bound.ok and not bound.reachable:
        live = ensure_runtime(run, bound)
        payload["ok"] = live.ok
        payload["reachable"] = live.reachable
        payload["appVersion"] = live.app_version
        if not live.ok:
            payload["code"] = live.code
            payload["message"] = live.message
    return payload


def _status(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    return doctor(runner)


def _ps(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    ps = orca_json(runner, ["worktree", "ps"], 30.0)
    if not ps.ok:
        return envelope_error(ps)
    worktrees = worktrees_of(ps.result)
    query = (_optional_str(args, "query") or "").lower()
    state = (_optional_str(args, "state") or "").lower()
    panes = filter_panes(worktrees, query, state)
    by_state: dict[str, int] = {}
    for pane in panes:
        key = str(pane.get("state") or "none")
        by_state[key] = by_state.get(key, 0) + 1
    rec = record(ps.result) or {}
    return {
        "ok": True,
        "source": "orca worktree ps",
        "note": (
            "state/interrupted/lastAssistantMessage come from Orca agent Stop hooks "
            "for every worker type. Call again for a fresh snapshot."
        ),
        "totalWorktrees": rec.get("totalCount", len(worktrees)),
        "matchedPanes": len(panes),
        "byState": by_state,
        "query": query or None,
        "stateFilter": state or None,
        "panes": panes,
    }


def _dispatch(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    prompt = _need(args, "prompt")
    agent = infer_agent(_optional_str(args, "agent"), prompt)
    if not agent:
        return {
            "ok": False,
            "code": "need_agent",
            "message": "Which worker should Orca start: grok, codex, claude, cursor, or antigravity?",
        }
    name = task_name(_optional_str(args, "name"), prompt)
    supervise = args.get("supervise") is True
    stay = stay_in_place(prompt) or _optional_str(args, "worktree") == "current"
    repo_flag: str | None = None
    if stay:
        repo = abs_path_of(_optional_str(args, "repo")) or os.environ.get("ORCA_SESSION_CWD") or os.getcwd()
        if not str(repo).startswith("/"):
            return {"ok": False, "code": "invalid_argument", "message": "stay-in-place needs an absolute folder"}
        imported = import_path(runner, str(repo))
        if imported.get("ok") is False:
            return imported
        repo_flag = f"path:{repo}"
    elif _optional_str(args, "repo"):
        raw = _optional_str(args, "repo") or ""
        abs_path = abs_path_of(raw)
        if abs_path:
            imported = import_path(runner, abs_path)
            if imported.get("ok") is False:
                return imported
            repo_flag = f"path:{abs_path}"
        else:
            repo_flag = repo_selector(raw)
    else:
        fresh = create_fresh_repo(name)
        imported = import_path(runner, fresh)
        if imported.get("ok") is False:
            return imported
        repo_flag = f"path:{fresh}"

    hooks = ensure_agent_hooks(runner)
    if supervise and "orchestration.contract.v1" not in ready.capabilities:
        return {
            "ok": False,
            "code": "orchestration_unavailable",
            "message": "Orca orchestration is not enabled. Turn on Settings → Experimental, then retry with supervise.",
        }

    if supervise:
        return _dispatch_supervised(runner, agent, prompt, name, repo_flag, hooks)

    if stay:
        created = orca_json(
            runner,
            [
                "terminal",
                "create",
                "--worktree",
                "active",
                "--title",
                name,
                "--command",
                launch_command(agent),
            ],
            60.0,
        )
        if created.ok:
            rec = record(created.result) or {}
            handle = rec.get("handle") if isinstance(rec.get("handle"), str) else ""
            if handle:
                orca_json(
                    runner,
                    ["terminal", "wait", "--terminal", handle, "--for", "tui-idle", "--timeout-ms", "60000"],
                    70.0,
                )
                paste = orca_json(runner, ["terminal", "send", "--terminal", handle, "--text", prompt], 20.0)
                if paste.ok:
                    time.sleep(SUBMIT_DELAY_SEC)
                    orca_json(runner, ["terminal", "send", "--terminal", handle, "--enter"], 20.0)
            worktree_id = rec.get("worktreeId") if isinstance(rec.get("worktreeId"), str) else "active"
            return {
                "ok": True,
                "inspect": "orca",
                "agent": agent,
                "name": name,
                "supervise": False,
                "hooksEnabled": hooks.get("enabled"),
                "repo": repo_flag,
                "stay": True,
                "agentId": worktree_id,
                "runId": handle or worktree_id,
                "watch": "call orca_watch or orca_ps; Stop-hook state is agents[].state",
            }

    argv = ["worktree", "create", "--name", name, "--no-parent", "--agent", agent, "--prompt", prompt]
    if repo_flag:
        argv.extend(["--repo", repo_flag])
    created = orca_json(runner, argv, 90.0)
    if not created.ok:
        return envelope_error(created)
    ids = pick_handle(created.result)
    if "error" in ids:
        return {"ok": False, "code": "orca_error", "message": ids["error"]}
    return {
        "ok": True,
        "inspect": "orca",
        "agent": agent,
        "name": name,
        "supervise": False,
        "hooksEnabled": hooks.get("enabled"),
        "repo": repo_flag,
        "stay": stay,
        **ids,
        "watch": "call orca_watch or orca_ps; Stop-hook state is agents[].state",
    }


def _dispatch_supervised(
    runner: Runner,
    agent: str,
    prompt: str,
    name: str,
    repo_flag: str | None,
    hooks: dict[str, bool],
) -> dict[str, Any]:
    run = orca_json(runner, ["orchestration", "run-create", "--objective", prompt], 30.0)
    if not run.ok:
        return envelope_error(run)
    run_rec = record(run.result) or {}
    run_id = run_rec.get("id") if isinstance(run_rec.get("id"), str) else run_rec.get("runId")
    task = orca_json(runner, ["orchestration", "task-create", "--spec", prompt], 30.0)
    if not task.ok:
        return envelope_error(task)
    task_rec = record(task.result) or {}
    task_id = task_rec.get("id") if isinstance(task_rec.get("id"), str) else task_rec.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        return {"ok": False, "code": "orca_error", "message": "task-create returned no id"}
    worker_args = [
        "orchestration",
        "worker-start",
        "--task",
        task_id,
        "--worktree",
        "new-top-level",
        "--agent",
        agent,
        "--name",
        name,
    ]
    if repo_flag:
        worker_args.extend(["--repo", repo_flag])
    worker = orca_json(runner, worker_args, 90.0)
    if not worker.ok:
        return envelope_error(worker)
    worker_rec = record(worker.result) or {}
    dispatch_id = worker_rec.get("dispatchId") if isinstance(worker_rec.get("dispatchId"), str) else ""
    nested = record(worker_rec.get("dispatch")) or {}
    if not dispatch_id and isinstance(nested.get("id"), str):
        dispatch_id = nested["id"]
    ids = pick_handle(worker.result)
    if "error" in ids:
        ids = {
            "agentId": worker_rec.get("worktreeId") if isinstance(worker_rec.get("worktreeId"), str) else str(run_id or ""),
            "runId": dispatch_id,
        }
    return {
        "ok": True,
        "inspect": "orca",
        "agent": agent,
        "name": name,
        "supervise": True,
        "hooksEnabled": hooks.get("enabled"),
        "repo": repo_flag,
        "dispatchId": dispatch_id,
        "orchestrationRunId": run_id,
        "taskId": task_id,
        **ids,
    }


def _watch(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    budget = args.get("timeoutMs")
    timeout_s = (budget / 1000.0) if isinstance(budget, (int, float)) and budget > 0 else 45.0
    if args.get("supervise") is True:
        if "orchestration.contract.v1" not in ready.capabilities:
            return {
                "ok": False,
                "code": "orchestration_unavailable",
                "message": "Orca orchestration is not enabled. Turn on Settings → Experimental.",
            }
        checked = orca_json(
            runner,
            [
                "orchestration",
                "check",
                "--wait",
                "--types",
                "worker_done,escalation,question",
                "--timeout-ms",
                str(int(timeout_s * 1000)),
            ],
            timeout_s + 10.0,
        )
        if not checked.ok:
            return envelope_error(checked)
        return {"ok": True, "status": "mailbox", "result": checked.result}

    rows = _ps_rows(runner)
    row = pick_row(rows, _optional_str(args, "worktree"))
    selector = row.get("worktreeId") if row and isinstance(row.get("worktreeId"), str) else _optional_str(args, "worktree")
    if not selector:
        return {
            "ok": False,
            "code": "not_found",
            "message": "no Orca worktrees" if not _optional_str(args, "worktree") else f"no worktree matching {_optional_str(args, 'worktree')}",
        }
    waited = wait_for_hook_done(runner, str(selector), timeout_s=timeout_s)
    if waited["status"] in ("done", "interrupted"):
        wt = waited.get("worktree") or {}
        append_done(
            worktree=str(wt.get("worktreeId") or selector),
            title=str(wt.get("displayName") or "agent done"),
            summary=str((wt.get("lastAssistantMessage") if isinstance(wt, dict) else "") or waited["status"]),
            state=waited["status"],
        )
        return {"ok": True, **waited}
    return {"ok": False, "code": waited["status"], "message": f"wait ended: {waited['status']}", **waited}


def _terminals(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    listed = orca_json(runner, ["terminal", "list", "--worktree", _need(args, "worktree")], 20.0)
    if not listed.ok:
        return envelope_error(listed)
    return {"ok": True, "result": listed.result}


def _read(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    cmd = ["terminal", "read", "--terminal", _need(args, "terminal"), "--limit", str(_limit(args))]
    cursor = _optional_str(args, "cursor")
    if cursor:
        cmd.extend(["--cursor", cursor])
    got = orca_json(runner, cmd, 20.0)
    if not got.ok:
        return envelope_error(got)
    return {"ok": True, "result": got.result}


def _composer_draft(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    terminal = result.get("terminal")
    tail = terminal.get("tail") if isinstance(terminal, dict) else None
    if not isinstance(tail, list):
        return ""
    for line in reversed(tail[-30:]):
        if not isinstance(line, str) or "❯" not in line:
            continue
        after = line.split("❯", 1)[1]
        if "│" in after:
            after = after.split("│", 1)[0]
        return after.strip()
    return ""


def _draft_still_ours(draft: str, text: str) -> bool:
    if not draft:
        return False
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        return False
    return draft.startswith(first[:80]) or first[:80] in draft


def _send(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    terminal = _need(args, "terminal")
    text = _need(args, "text").rstrip("\r\n")
    interrupt = args.get("interrupt") is True
    steps: list[dict[str, Any]] = []
    if interrupt:
        code_env = orca_json(runner, ["terminal", "send", "--terminal", terminal, "--interrupt"], 20.0)
        steps.append({"step": "interrupt", "ok": code_env.ok, "raw": code_env.result if code_env.ok else code_env.error_message})
        if not code_env.ok:
            return {"ok": False, "submitted": False, "steps": steps, **envelope_error(code_env)}
        time.sleep(SUBMIT_RETRY_SEC)
    pasted = orca_json(runner, ["terminal", "send", "--terminal", terminal, "--text", text], 20.0)
    steps.append({"step": "paste", "ok": pasted.ok, "raw": pasted.result if pasted.ok else pasted.error_message})
    if not pasted.ok:
        return {"ok": False, "submitted": False, "steps": steps, **envelope_error(pasted)}
    submitted = False
    composer_empty = False
    for attempt in ("enter", "enter-retry"):
        time.sleep(SUBMIT_DELAY_SEC if attempt == "enter" else SUBMIT_RETRY_SEC)
        entered = orca_json(runner, ["terminal", "send", "--terminal", terminal, "--enter"], 20.0)
        steps.append({"step": attempt, "ok": entered.ok, "raw": entered.result if entered.ok else entered.error_message})
        if not entered.ok:
            return {"ok": False, "submitted": False, "steps": steps, **envelope_error(entered)}
        time.sleep(SUBMIT_RETRY_SEC)
        read = orca_json(runner, ["terminal", "read", "--terminal", terminal, "--limit", "80"], 20.0)
        draft = _composer_draft(record(read.result) if read.ok else None)
        composer_empty = not _draft_still_ours(draft, text)
        if composer_empty:
            submitted = True
            break
    return {
        "ok": submitted,
        "submitted": submitted,
        "composerEmpty": composer_empty,
        "user_prompt_submit": submitted,
        "steps": steps,
        "terminal": terminal,
    }


def _stop(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    handle = _optional_str(args, "terminal")
    if not handle:
        rows = _ps_rows(runner)
        row = pick_row(rows, _optional_str(args, "worktree"))
        if not row:
            return {
                "ok": False,
                "code": "not_found",
                "message": "no Orca worktrees" if not _optional_str(args, "worktree") else f"no worktree matching {_optional_str(args, 'worktree')}",
            }
        selector = f"id:{row['worktreeId']}" if isinstance(row.get("worktreeId"), str) else str(row.get("displayName") or "")
        listed = orca_json(runner, ["terminal", "list", "--worktree", selector], 20.0)
        handle = pick_terminal_handle(listed.result) if listed.ok else None
    if not handle:
        return {"ok": False, "code": "not_found", "message": "no live terminal for that worker"}
    sent = orca_json(runner, ["terminal", "send", "--terminal", handle, "--interrupt"], 20.0)
    if not sent.ok:
        return envelope_error(sent)
    worker_stop = None
    dispatch = _optional_str(args, "dispatch")
    if dispatch:
        stopped = orca_json(runner, ["orchestration", "worker-stop", "--dispatch", dispatch], 20.0)
        worker_stop = {"ok": stopped.ok, "message": None if stopped.ok else stopped.error_message}
    return {"ok": True, "interrupted": True, "terminal": handle, "workerStop": worker_stop}


def _import(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    path = _need(args, "path")
    if not path.startswith("/"):
        return {"ok": False, "code": "invalid_argument", "message": "path must be absolute"}
    return import_path(runner, path)


def _inbox(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    return inbox_call(args)


def _gate_list(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    cmd = ["orchestration", "gate-list"]
    run = _optional_str(args, "run")
    if run:
        cmd.extend(["--run", run])
    status = _optional_str(args, "status")
    if status:
        cmd.extend(["--status", status])
    listed = orca_json(runner, cmd, 20.0)
    rec = record(listed.result)
    err_code = listed.error_code
    if err_code == "run_required" or (
        not listed.ok and "run_required" in (listed.error_message or "")
    ):
        return {
            "ok": True,
            "gates": [],
            "note": (
                "No Run is bound. Pass run=<run_id> to inspect a named Run without binding. "
                "This is an empty list, not a hard error."
            ),
        }
    if not listed.ok:
        body = rec or {}
        nested = body.get("error") if isinstance(body.get("error"), dict) else None
        if nested and nested.get("code") == "run_required":
            return {
                "ok": True,
                "gates": [],
                "note": "No Run is bound. Pass run=<run_id>. Empty list, not a hard error.",
            }
        return envelope_error(listed)
    return {"ok": True, "result": listed.result}


def _gate_resolve(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    resolved = orca_json(
        runner,
        [
            "orchestration",
            "gate-resolve",
            "--id",
            _need(args, "id"),
            "--resolution",
            _need(args, "resolution"),
        ],
        20.0,
    )
    if not resolved.ok:
        return envelope_error(resolved)
    return {"ok": True, "result": resolved.result}


def _worker_read(args: dict[str, Any], runner: Runner) -> dict[str, Any]:
    ready = _ready(runner)
    if isinstance(ready, dict):
        return ready
    cmd = [
        "orchestration",
        "worker-read",
        "--dispatch",
        _need(args, "dispatch"),
        "--source",
        _optional_str(args, "source") or "auto",
        "--limit",
        str(_limit(args)),
    ]
    cursor = _optional_str(args, "cursor")
    if cursor:
        cmd.extend(["--cursor", cursor])
    got = orca_json(runner, cmd, 20.0)
    if not got.ok:
        return envelope_error(got)
    return {"ok": True, "result": got.result}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "orca_status",
        "description": (
            "See if the local Orca.app is reachable from this Mac (`orca status --json`). "
            "Call when install, doctor, or a later tool says orca_unavailable. "
            "This plugin cannot reach Orca from Linux cloud."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _status,
    },
    {
        "name": "orca_ps",
        "description": (
            "Orca pane status from `orca worktree ps`. This is the done/working/interrupted "
            "signal for every worker (grok, codex, claude, cursor, agy). Optional query/state. "
            "You decide when to call again."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional. Case-insensitive match on displayName, repo, path, worktreeId, prompt, lastAssistantMessage.",
                },
                "state": {
                    "type": "string",
                    "description": "Optional. Only panes in this Orca state, e.g. working or done.",
                },
            },
            "additionalProperties": False,
        },
        "handler": _ps,
    },
    {
        "name": "orca_dispatch",
        "description": (
            "Start grok, Codex, Claude, Cursor, or Antigravity in a new empty Orca project "
            "under ~/orca/projects/<name>. Use when the user says 用 Orca / 在 Orca 里 / "
            "let grok do / 开一栏. Do not write the files yourself. Omit repo unless they "
            "named a folder or said to stay in this folder. Returns immediately."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "grok, codex, claude, cursor, or antigravity. Infer from the sentence.",
                },
                "prompt": {"type": "string", "description": "The user task, in their words."},
                "name": {"type": "string", "description": "Short label. Invented from the task if omitted."},
                "repo": {"type": "string", "description": "Absolute folder they named. Omit for a new empty project."},
                "supervise": {
                    "type": "boolean",
                    "description": "True only if they asked Orca orchestration to watch the worker.",
                },
                "worktree": {
                    "type": "string",
                    "enum": ["new", "current"],
                    "description": "current only if they asked to stay in this folder.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        "handler": _dispatch,
    },
    {
        "name": "orca_watch",
        "description": (
            "Poll `orca worktree ps` until that worker's Stop-hook state is done or interrupted. "
            "tui-idle is not success. Default timeout 45s so the MCP call can return; call again "
            "if status is timeout and they still want you to wait."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "worktree": {"type": "string", "description": "Name, id, or path. Omit for the latest worker."},
                "timeoutMs": {"type": "number", "description": "Max wait in milliseconds. Default 45000."},
                "supervise": {"type": "boolean", "description": "True when dispatch used supervise: true."},
            },
            "additionalProperties": False,
        },
        "handler": _watch,
    },
    {
        "name": "orca_inbox",
        "description": (
            "Optional leftover pull file (~/.config/grokbot-orca/inbox.jsonl, then orca-bridge). "
            "Done/working status is orca_ps, not this file. Pass mark=<id> to mark one read."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "description": "Default true."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "mark": {"type": "string", "description": "Item id to mark read."},
            },
            "additionalProperties": False,
        },
        "handler": _inbox,
    },
    {
        "name": "orca_terminals",
        "description": "List live terminals for a worktree. Re-list before send; handles go stale.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "worktree": {
                    "type": "string",
                    "description": "Worktree selector, e.g. id:<repoId>::<path> or name:<displayName>",
                }
            },
            "required": ["worktree"],
            "additionalProperties": False,
        },
        "handler": _terminals,
    },
    {
        "name": "orca_read",
        "description": (
            "Read a worker TUI pane via orca terminal read (screen buffer, not a full transcript). "
            "Pass cursor=nextCursor to page."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "terminal": {"type": "string", "description": "Runtime terminal handle"},
                "cursor": {"type": "string", "description": "nextCursor from a previous orca_read."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": READ_MAX_LIMIT,
                    "description": f"Rows to return. Default {READ_DEFAULT_LIMIT}.",
                },
            },
            "required": ["terminal"],
            "additionalProperties": False,
        },
        "handler": _read,
    },
    {
        "name": "orca_send",
        "description": (
            "Paste text into a live Orca pane, then submit it. Paste and Enter are separate so "
            "Grok does not treat CR as a newline inside bracketed paste. Confirm with the user first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "terminal": {"type": "string"},
                "text": {"type": "string"},
                "interrupt": {"type": "boolean"},
            },
            "required": ["terminal", "text"],
            "additionalProperties": False,
        },
        "handler": _send,
    },
    {
        "name": "orca_stop",
        "description": (
            "Interrupt a live Orca worker (`orca terminal send --interrupt`). Use when they say "
            "停 / 取消 / stop / interrupt. Confirm first. Omit handles and the tool finds the latest pane."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "terminal": {"type": "string"},
                "worktree": {"type": "string"},
                "dispatch": {"type": "string", "description": "Optional orchestration dispatch id."},
            },
            "additionalProperties": False,
        },
        "handler": _stop,
    },
    {
        "name": "orca_import",
        "description": "Register a local folder with Orca (`orca repo add`). Path must be absolute.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute folder path."}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "handler": _import,
    },
    {
        "name": "orca_worker_read",
        "description": (
            "Read one supervised orchestration Dispatch. Manual grok/codex windows have no "
            "dispatch id — use orca_read."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dispatch": {"type": "string"},
                "source": {"type": "string", "enum": ["auto", "transcript", "terminal"]},
                "cursor": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": READ_MAX_LIMIT},
            },
            "required": ["dispatch"],
            "additionalProperties": False,
        },
        "handler": _worker_read,
    },
    {
        "name": "orca_gate_list",
        "description": (
            "List Orca decision gates. If no Run is bound, returns an empty list plus a note."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "run": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "handler": _gate_list,
    },
    {
        "name": "orca_gate_resolve",
        "description": "Resolve a pending decision gate. Confirm with the user first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "resolution": {"type": "string"},
            },
            "required": ["id", "resolution"],
            "additionalProperties": False,
        },
        "handler": _gate_resolve,
    },
]


def call_tool(name: str, arguments: dict[str, Any] | None, runner: Runner | None = None) -> dict[str, Any]:
    args = arguments or {}
    run = _runner(runner)
    for spec in TOOLS:
        if spec["name"] == name:
            try:
                payload = spec["handler"](args, run)
            except ValueError as exc:
                return _text_result(str(exc), is_error=True)
            is_error = isinstance(payload, dict) and payload.get("ok") is False
            return _text_result(payload, is_error=is_error)
    return _text_result(f"unknown tool: {name}", is_error=True)
