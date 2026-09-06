#!/bin/sh
# Deterministic terminal demo for screenshots. No secrets. No fake pane lists as live Orca.
set -eu
cd /workspace
export TERM=xterm-256color
printf '\033]0;grokbot-orca smoke\007'
echo "=== grokbot-orca plugin files ==="
find . -type f \( -name 'plugin.json' -o -name 'mcp.json' -o -name 'SKILL.md' -o -name 'grokbot-orca-mcp.py' \) | sort
echo
echo "=== plugin.json ==="
cat plugin.json
echo
echo "=== mcp.json ==="
cat mcp.json
echo
echo "=== python3 bin/grokbot-orca-mcp.py --list-tools ==="
python3 bin/grokbot-orca-mcp.py --list-tools
echo
echo "=== uname / orca (this Linux host has no Orca.app) ==="
uname -s
command -v orca || echo "orca: not found"
echo
echo "=== python3 bin/grokbot-orca-mcp.py --doctor ==="
python3 bin/grokbot-orca-mcp.py --doctor || true
echo
echo "=== unittest ==="
python3 -m unittest discover -s tests -q
echo "OK"
echo
echo "=== MCP initialize + tools/list + orca_status (FAKE_ORCA_STATE) ==="
export FAKE_ORCA_STATE=/tmp/grokbot-orca-fake-orca.json
export ORCA_CLI_COMMAND=/workspace/tests/fake_orca.py
python3 -c 'import json,sys; from pathlib import Path; sys.path.insert(0,"/workspace"); from tests.fake_orca import default_state; Path("/tmp/grokbot-orca-fake-orca.json").write_text(json.dumps(default_state()))'
python3 scripts/mcp-smoke.py
echo
echo "=== done ==="
exec sleep 120
