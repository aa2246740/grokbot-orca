"""MCP JSON-RPC over stdio. Newline JSON by default, Content-Length if the client speaks LSP."""

from __future__ import annotations

import json
import sys
from typing import Any

from .meta import SERVER_NAME, __version__
from .tools import TOOLS, call_tool

PROTOCOL_VERSION = "2024-11-05"

_framing = "newline"


def _read_message() -> dict[str, Any] | None:
    global _framing
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    stripped = line.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        _framing = "newline"
        return json.loads(line.decode("utf-8"))
    header_size = None
    while True:
        if line in (b"\r\n", b"\n"):
            break
        if line.lower().startswith(b"content-length:"):
            header_size = int(line.split(b":", 1)[1].strip())
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    if header_size is None:
        return None
    body = sys.stdin.buffer.read(header_size)
    if not body:
        return None
    _framing = "lsp"
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if _framing == "lsp":
        sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(raw)
    else:
        sys.stdout.buffer.write(raw + b"\n")
    sys.stdout.buffer.flush()


def ok(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def err(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle_rpc(msg: dict[str, Any], runner=None) -> dict[str, Any] | None:
    method = msg.get("method")
    id_ = msg.get("id")
    if method is None:
        return None
    if id_ is None:
        return None
    if method == "initialize":
        params = msg.get("params") or {}
        requested = params.get("protocolVersion")
        proto = requested if isinstance(requested, str) and requested.strip() else PROTOCOL_VERSION
        return ok(
            id_,
            {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
            },
        )
    if method == "ping":
        return ok(id_, {})
    if method == "tools/list":
        tools = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in TOOLS]
        return ok(id_, {"tools": tools})
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            return ok(id_, call_tool(str(params.get("name") or ""), params.get("arguments") or {}, runner=runner))
        except ValueError as exc:
            return ok(
                id_,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
    return err(id_, -32601, f"method not found: {method}")


def main(runner=None) -> int:
    while True:
        try:
            msg = _read_message()
        except Exception as exc:  # noqa: BLE001 — keep the MCP loop alive
            _write_message(err(None, -32700, f"parse error: {exc}"))
            continue
        if msg is None:
            return 0
        reply = handle_rpc(msg, runner=runner)
        if reply is not None:
            _write_message(reply)
