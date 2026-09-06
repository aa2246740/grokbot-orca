#!/bin/sh
# Install grokbot-orca into Grok Bot's auto-trusted plugin directory on this Mac.
set -eu

DEST="${GROK_PLUGIN_DIR:-$HOME/.grok/plugins/grokbot-orca}"
REPO="${GROKBOT_ORCA_REPO:-https://github.com/aa2246740/grokbot-orca.git}"

mkdir -p "$(dirname "$DEST")"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch --quiet origin
  git -C "$DEST" pull --ff-only --quiet origin HEAD || git -C "$DEST" pull --ff-only --quiet origin main
else
  git clone "$REPO" "$DEST"
fi

chmod +x "$DEST/bin/grokbot-orca-mcp.py"

echo "Installed $DEST"
echo "Next:"
echo "  1. orca status --json     # Orca.app must be running on this Mac"
echo "  2. python3 $DEST/bin/grokbot-orca-mcp.py --doctor"
echo "  3. Quit and reopen Grok Bot desktop so it loads ~/.grok/plugins/grokbot-orca"
echo "  4. New chat: 用 Orca 让 grok 做个天气网页"
