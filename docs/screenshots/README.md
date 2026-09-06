# Screenshots

These are real terminal captures from the grokbot-orca checkout.

This Linux image has no `orca` binary and no Orca.app. `orca_ps` against live panes is not captured here on purpose. Do not substitute a mocked pane list for that slot.

| File | What it shows |
| --- | --- |
| `plugin-tree.png` | Agent Plugins files: `plugin.json`, `mcp.json`, skill, MCP entry. |
| `mcp-tools-list.png` | stdio MCP `initialize` then `tools/list` (live tool names). |
| `doctor-no-orca.png` | `--doctor` on this Linux host: `orca_unavailable`, mac-colocated note. |
| `doctor-fake-orca.png` | `--doctor` / `orca_status` with the test double CLI (`FAKE_ORCA_STATE`). |

Mac prove (Orca.app open, `orca status --json` green) is [mac-prove.md](../mac-prove.md). EDITH captures `orca-ps.png` there.
