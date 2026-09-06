#!/bin/bash
set -eu
cd /workspace
export DISPLAY=:1
pkill -f xfce4-terminal 2>/dev/null || true
sleep 0.5

shot() {
  local title="$1" cmd="$2" out="$3"
  xfce4-terminal --title="$title" --geometry=110x38 --working-directory=/workspace \
    -e "bash -lc '$cmd; sleep 80'" &
  sleep 3
  ffmpeg -y -f x11grab -video_size 1920x1080 -i :1 -frames:v 1 "$out" >/tmp/ff.log 2>&1
  echo "wrote $out $(stat -c%s "$out") bytes"
  pkill -f xfce4-terminal 2>/dev/null || true
  sleep 0.8
}

shot "grokbot-orca plugin files" \
  'echo === plugin files ===; find . -type f \( -name plugin.json -o -name mcp.json -o -name SKILL.md -o -name grokbot-orca-mcp.py \) | sort; echo; echo === plugin.json ===; cat plugin.json; echo; echo === mcp.json ===; cat mcp.json' \
  /workspace/docs/screenshots/plugin-tree.png

unset ORCA_CLI_COMMAND FAKE_ORCA_STATE || true
shot "grokbot-orca doctor (no orca)" \
  'echo === uname ===; uname -srm; echo; echo === command -v orca ===; command -v orca || echo orca: not found; echo; echo === python3 bin/grokbot-orca-mcp.py --doctor ===; python3 bin/grokbot-orca-mcp.py --doctor || true' \
  /workspace/docs/screenshots/doctor-no-orca.png

python3 -c 'import json,sys; from pathlib import Path; sys.path.insert(0,"/workspace"); from tests.fake_orca import default_state; Path("/tmp/grokbot-orca-fake-orca.json").write_text(json.dumps(default_state()))'
export FAKE_ORCA_STATE=/tmp/grokbot-orca-fake-orca.json
export ORCA_CLI_COMMAND=/workspace/tests/fake_orca.py
shot "grokbot-orca MCP smoke (fake orca)" \
  'export FAKE_ORCA_STATE=/tmp/grokbot-orca-fake-orca.json ORCA_CLI_COMMAND=/workspace/tests/fake_orca.py; echo === --list-tools ===; python3 bin/grokbot-orca-mcp.py --list-tools; echo; echo === --doctor ===; python3 bin/grokbot-orca-mcp.py --doctor; echo; echo === mcp-smoke.py ===; python3 scripts/mcp-smoke.py' \
  /workspace/docs/screenshots/mcp-tools-list.png

cp /workspace/docs/screenshots/mcp-tools-list.png /workspace/docs/screenshots/doctor-fake-orca.png
ls -la /workspace/docs/screenshots/*.png
