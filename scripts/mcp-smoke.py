#!/usr/bin/env python3
"""Initialize, tools/list, and orca_status against the stdio MCP. Used for smoke + screenshots."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = [sys.executable, str(ROOT / "bin" / "grokbot-orca-mcp.py")]


def rpc(proc: subprocess.Popen, msg: dict) -> dict:
    raw = json.dumps(msg).encode("utf-8") + b"\n"
    assert proc.stdin is not None
    proc.stdin.write(raw)
    proc.stdin.flush()
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise SystemExit("MCP server closed stdout")
    return json.loads(line.decode("utf-8"))


def main() -> int:
    env = os.environ.copy()
    proc = subprocess.Popen(
        SERVER,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(ROOT),
    )
    try:
        init = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "grokbot-orca-smoke", "version": "0"},
                },
            },
        )
        print("initialize ->", json.dumps(init["result"]["serverInfo"], ensure_ascii=False))
        listed = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listed["result"]["tools"]]
        print("tools/list ->", ", ".join(names))
        status = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "orca_status", "arguments": {}},
            },
        )
        body = json.loads(status["result"]["content"][0]["text"])
        print("orca_status ->")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0 if body.get("ok") else 2
    finally:
        proc.kill()
        proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
