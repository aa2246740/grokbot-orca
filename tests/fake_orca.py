#!/usr/bin/env python3
"""Test double for the Orca CLI. Driven by FAKE_ORCA_STATE JSON."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CORE = [
    "open",
    "status",
    "repo add",
    "worktree create",
    "worktree ps",
    "worktree show",
    "terminal create",
    "terminal send",
    "terminal wait",
    "terminal list",
    "terminal read",
    "agent-context",
    "agent hooks status",
    "agent hooks on",
    "orchestration run-create",
    "orchestration task-create",
    "orchestration worker-start",
    "orchestration check",
    "orchestration worker-stop",
    "orchestration worker-read",
    "orchestration gate-list",
    "orchestration gate-resolve",
    "skills get",
]


def state_path() -> Path:
    return Path(os.environ.get("FAKE_ORCA_STATE") or "/tmp/grokbot-orca-fake-orca.json")


def load() -> dict:
    path = state_path()
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default_state()


def save(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def default_state() -> dict:
    return {
        "reachable": True,
        "appVersion": "1.4.193",
        "capabilities": ["orchestration.contract.v1"],
        "commands": CORE,
        "hooksEnabled": False,
        "worktrees": [],
        "terminals": [],
        "reads": {},
        "sends": [],
        "creates": [],
        "argvLog": [],
        "gateError": None,
        "composerDraft": "",
    }


def flag(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def ok(result) -> int:
    print(json.dumps({"ok": True, "result": result}))
    return 0


def err(code: str, message: str) -> int:
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
    return 1


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--json"]
    state = load()
    state.setdefault("argvLog", []).append(args)
    save(state)

    if args[:1] == ["agent-context"]:
        print(json.dumps({"schemaVersion": 1, "commands": [{"command": c} for c in state.get("commands", CORE)]}))
        return 0
    if args[:1] == ["status"]:
        return ok(
            {
                "runtime": {
                    "appVersion": state.get("appVersion"),
                    "reachable": state.get("reachable", True),
                    "capabilities": state.get("capabilities", []),
                },
                "app": {"running": state.get("reachable", True)},
            }
        )
    if args[:1] == ["open"]:
        state["reachable"] = True
        save(state)
        return ok({"opened": True})
    if args[:2] == ["agent", "hooks"]:
        if args[2:3] == ["on"]:
            state["hooksEnabled"] = True
            save(state)
            return ok({"enabled": True})
        return ok({"enabled": bool(state.get("hooksEnabled"))})
    if args[:2] == ["repo", "add"]:
        path = flag(args, "--path") or ""
        repo = {"id": "repo_" + path.replace("/", "_")[-12:], "path": path, "displayName": Path(path).name}
        return ok({"repo": repo})
    if args[:2] == ["worktree", "ps"]:
        trees = state.get("worktrees") or []
        return ok({"worktrees": trees, "totalCount": len(trees)})
    if args[:2] == ["worktree", "show"]:
        return ok({"worktree": (state.get("worktrees") or [None])[0]})
    if args[:2] == ["worktree", "create"]:
        name = flag(args, "--name") or "task"
        agent = flag(args, "--agent") or "grok"
        prompt = flag(args, "--prompt") or ""
        repo = flag(args, "--repo") or ""
        wt_id = f"wt_{len(state.get('worktrees') or []) + 1}"
        handle = f"term_{wt_id}"
        row = {
            "worktreeId": wt_id,
            "displayName": name,
            "path": f"/tmp/fake-orca/{name}",
            "repo": repo,
            "lastActivityAt": "2026-09-06T08:00:00+00:00",
            "liveTerminalCount": 1,
            "agents": [
                {
                    "paneKey": handle,
                    "agentType": agent,
                    "state": "working",
                    "interrupted": False,
                    "prompt": prompt,
                    "lastAssistantMessage": None,
                }
            ],
        }
        state.setdefault("worktrees", []).append(row)
        state.setdefault("terminals", []).append(
            {"handle": handle, "worktreeId": wt_id, "writable": True, "orphaned": False, "title": name}
        )
        state.setdefault("creates", []).append({"name": name, "agent": agent, "prompt": prompt, "repo": repo})
        save(state)
        return ok(
            {
                "worktree": {"id": wt_id},
                "worktreeId": wt_id,
                "startupTerminal": {"handle": handle},
                "agentTerminalHandle": handle,
            }
        )
    if args[:2] == ["terminal", "list"]:
        return ok({"terminals": state.get("terminals") or []})
    if args[:2] == ["terminal", "create"]:
        handle = "term_active"
        state.setdefault("terminals", []).append(
            {"handle": handle, "worktreeId": "active", "writable": True, "orphaned": False}
        )
        save(state)
        return ok({"handle": handle, "worktreeId": "active"})
    if args[:2] == ["terminal", "wait"]:
        return ok({"waited": True})
    if args[:2] == ["terminal", "read"]:
        terminal = flag(args, "--terminal") or ""
        draft = state.get("composerDraft") or ""
        payload = state.get("reads", {}).get(terminal) or {
            "truncated": False,
            "limited": False,
            "oldestCursor": "0",
            "nextCursor": "1",
            "latestCursor": "1",
            "returnedLineCount": 1,
            "text": "ready",
            "terminal": {"tail": [f"❯ {draft}"] if draft else ["(idle)"]},
        }
        return ok(payload)
    if args[:2] == ["terminal", "send"]:
        terminal = flag(args, "--terminal") or ""
        text = flag(args, "--text")
        interrupt = "--interrupt" in args
        enter = "--enter" in args
        event = {"terminal": terminal, "text": text, "interrupt": interrupt, "enter": enter}
        state.setdefault("sends", []).append(event)
        if text is not None:
            state["composerDraft"] = text.splitlines()[0][:80]
        if enter:
            state["composerDraft"] = ""
        if interrupt:
            for wt in state.get("worktrees") or []:
                for agent in wt.get("agents") or []:
                    agent["interrupted"] = True
                    agent["state"] = "interrupted"
        save(state)
        return ok(event)
    if args[:2] == ["orchestration", "run-create"]:
        return ok({"id": "run_1"})
    if args[:2] == ["orchestration", "task-create"]:
        return ok({"id": "task_1"})
    if args[:2] == ["orchestration", "worker-start"]:
        return ok({"dispatchId": "ctx_1", "worktreeId": "wt_orch", "handle": "term_orch"})
    if args[:2] == ["orchestration", "check"]:
        return ok({"events": []})
    if args[:2] == ["orchestration", "worker-stop"]:
        return ok({"stopped": True})
    if args[:2] == ["orchestration", "worker-read"]:
        return ok({"text": "worker log", "source": flag(args, "--source") or "auto"})
    if args[:2] == ["orchestration", "gate-list"]:
        if state.get("gateError") == "run_required":
            return err("run_required", "no run bound")
        return ok({"gates": []})
    if args[:2] == ["orchestration", "gate-resolve"]:
        return ok({"resolved": True, "id": flag(args, "--id")})
    return err("unknown", " ".join(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
