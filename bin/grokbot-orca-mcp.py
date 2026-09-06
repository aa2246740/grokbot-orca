#!/usr/bin/env python3
"""stdio MCP for local Orca. Must run on the same Mac as Orca.app and Grok Bot desktop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from grokbot_orca import TOOLS, doctor, stdio_main  # noqa: E402
from grokbot_orca.cli import default_runner, resolve_cli  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grokbot-orca-mcp", description="Local Orca MCP for Grok Bot desktop")
    parser.add_argument("--doctor", action="store_true", help="Print orca status JSON and exit")
    parser.add_argument("--list-tools", action="store_true", help="Print MCP tool names and exit")
    args = parser.parse_args(argv)
    if args.list_tools:
        for spec in TOOLS:
            print(spec["name"])
        return 0
    if args.doctor:
        payload = doctor(default_runner(resolve_cli()))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 1
    return stdio_main()


if __name__ == "__main__":
    raise SystemExit(main())
