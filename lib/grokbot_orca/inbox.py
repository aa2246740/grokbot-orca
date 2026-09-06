"""Optional leftover inbox (grokbot-orca, with orca-bridge fallback)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

INBOX_DEFAULT_LIMIT = 20


def config_dir() -> Path:
    override = os.environ.get("GROKBOT_ORCA_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "grokbot-orca"


def inbox_path() -> Path:
    return config_dir() / "inbox.jsonl"


def legacy_inbox_path() -> Path:
    override = os.environ.get("ORCA_BRIDGE_CONFIG")
    root = Path(override) if override else Path.home() / ".config" / "orca-bridge"
    return root / "inbox.jsonl"


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    items: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _save(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    body = "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in items)
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "ts": item.get("ts"),
        "worktree": item.get("worktree"),
        "terminal": item.get("terminal"),
        "title": item.get("title"),
        "state": item.get("state"),
        "summary": item.get("summary"),
        "unread": item.get("unread", True),
    }


def append_done(
    *,
    worktree: str = "",
    terminal: str = "",
    title: str = "agent done",
    summary: str = "",
    state: str = "done",
) -> dict[str, Any]:
    item = {
        "id": "evt_" + uuid.uuid4().hex[:12],
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "worktree": worktree,
        "terminal": terminal,
        "title": title[:120],
        "state": state,
        "summary": summary or title,
        "unread": True,
    }
    path = inbox_path()
    items = _load(path)
    items.append(item)
    _save(path, items)
    return item


def inbox_call(args: dict[str, Any]) -> dict[str, Any]:
    path = inbox_path()
    items = _load(path)
    source = str(path)
    if not items:
        legacy = _load(legacy_inbox_path())
        if legacy:
            items = legacy
            source = str(legacy_inbox_path())
    marked = None
    mark = args.get("mark")
    if isinstance(mark, str) and mark.strip():
        for item in items:
            if str(item.get("id") or "") == mark.strip():
                item["unread"] = False
                marked = mark.strip()
                break
        if marked and source == str(path):
            _save(path, items)
    unread_only = args.get("unread_only")
    filtered = [item for item in items if item.get("unread", True)] if unread_only is not False else items
    limit = args.get("limit")
    if isinstance(limit, int) and not isinstance(limit, bool):
        cap = max(1, min(limit, 200))
    else:
        cap = INBOX_DEFAULT_LIMIT
    newest = list(reversed(filtered[-cap:]))
    return {
        "ok": True,
        "path": source,
        "unread": sum(1 for item in items if item.get("unread", True)),
        "returned": len(newest),
        "marked": marked,
        "items": [_public(item) for item in newest],
        "note": "Done/working status is orca_ps (Orca Stop-hook state), not this file.",
    }
