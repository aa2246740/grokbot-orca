# Screenshots

These are real xfce4-terminal captures from the grokbot-orca checkout.

This Linux image has no `orca` binary and no Orca.app. `orca_ps` against live panes is not captured here on purpose. Do not substitute a mocked pane list for that slot.

| File | What it shows |
| --- | --- |
| `plugin-tree.jpg` | Agent Plugins files: `plugin.json`, `mcp.json`, skill path. |
| `mcp-tools-list.jpg` | stdio MCP `initialize` then `tools/list`, plus `orca_status` against the fake CLI. |
| `doctor-no-orca.jpg` | `--doctor` on this Linux host: `orca_unavailable`, mac-colocated note. |
| `doctor-fake-orca.jpg` | Same smoke as `mcp-tools-list.jpg` (fake `orca` reachable). |

Mac prove (Orca.app open, `orca status --json` green) is [mac-prove.md](../mac-prove.md). EDITH captures `orca-ps.png` there.
