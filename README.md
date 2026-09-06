# grokbot-orca

Grok Bot desktop on Cola's Mac talks to the local [Orca](https://orca.computer) app. This plugin replaced the Cloudflare Worker + Mac relay path in [orca-bridge](https://github.com/aa2246740/orca-bridge).

EDITH (the Grok Bot agent) schedules. Orca executes in isolated worktrees. Workers are grok, Codex, Claude, Cursor, and Antigravity (`agy`). Default project is a new empty git repo under `~/orca/projects/<name>`. Done is Orca's Stop-hook `agents[].state`, not `tui-idle`.

```text
you ──chat──► Grok Bot desktop (this Mac)
                 │  grokbot-orca stdio MCP
                 ▼
            orca CLI  ──►  Orca.app
                              └── isolated worktree (grok / codex / …)
```

Same machine as `orca`. A Linux cloud agent cannot call this Mac's Orca. Do not assume otherwise.

Product behavior is ported from [dsh-orca-agents](https://github.com/aa2246740/dsh-orca-agents) (dispatch, empty project, Stop-hook watch, NL skill). Packaging is an [Agent Plugins 1.0.0](https://agent-plugins.org/specification) directory, not a DSH Cordis plugin. This repo does not patch DSH or Orca.app.

## You need (MacBook)

1. [Orca desktop](https://orca.computer), with `orca status --json` succeeding (tested against the 1.4.x CLI surface).
2. [Grok Bot desktop](https://grok.com) on the same Mac.
3. `python3` (macOS ships it as `/usr/bin/python3`).
4. At least one worker Orca can launch: `grok` / `codex` / `claude` / `cursor` / `agy`.
5. Local `git` (dispatch runs `git init` for empty projects). No GitHub account required.

Turn on Orca Settings → Experimental only if you want supervised orchestration (`supervise: true`). Ordinary dispatch does not need it. The plugin will try `orca agent hooks on` so Stop-hook `state` is populated.

## Install on this MacBook (Cola / EDITH)

One-liner:

```sh
curl -fsSL https://raw.githubusercontent.com/aa2246740/grokbot-orca/main/scripts/install-mac.sh | sh
```

That clones into `~/.grok/plugins/grokbot-orca` (Grok Bot auto-trusts this directory).

Equivalent:

```sh
git clone https://github.com/aa2246740/grokbot-orca.git ~/.grok/plugins/grokbot-orca
chmod +x ~/.grok/plugins/grokbot-orca/bin/grokbot-orca-mcp.py
```

Then, in Terminal:

```sh
command -v orca
orca status --json
python3 ~/.grok/plugins/grokbot-orca/bin/grokbot-orca-mcp.py --doctor
```

You want `ok: true` and `reachable: true`. If Orca.app is closed:

```sh
orca open
orca status --json
```

Quit Grok Bot desktop completely and reopen it so it loads the plugin (`plugin.json` + `mcp.json` stdio + `skills/grokbot-orca`). If the MCP does not appear, EDITH can AddMcpServer on this Mac as stdio:

- name: `grokbot-orca`
- command: `python3`
- args: `/Users/<you>/.grok/plugins/grokbot-orca/bin/grokbot-orca-mcp.py`
- cwd: `/Users/<you>/.grok/plugins/grokbot-orca`

Do not paste a Cloudflare `/t/<token>/mcp` URL. That was orca-bridge. This plugin is local stdio.

Disable any leftover `orca-bridge` MCP so tools are not duplicated.

New chat:

> 用 Orca 让 grok 做个天气网页

If you installed from a checkout instead of `~/.grok/plugins`, Grok Build users can also run `grok plugin install /path/to/grokbot-orca --trust` and restart.

## Tools

| Tool | What it does |
| --- | --- |
| `orca_status` | `orca status --json` plus CLI drift. Mac colocation note if `orca` is missing. |
| `orca_dispatch` | New empty repo + `orca worktree create --agent --prompt`. Returns immediately. |
| `orca_ps` | Snapshot of `orca worktree ps` (done / working / interrupted). |
| `orca_watch` | Poll ps until Stop-hook `done` or `interrupted`. Default 45s, call again if needed. |
| `orca_read` | `orca terminal read` (screen buffer). |
| `orca_send` | Paste, then Enter (separate, so Grok does not eat CR inside bracketed paste). Confirm first. |
| `orca_stop` | `orca terminal send --interrupt`. Confirm first. |
| `orca_terminals` | Re-list before send. Handles go stale. |
| `orca_inbox` | Optional leftover `~/.config/grokbot-orca/inbox.jsonl` (falls back to orca-bridge). |
| `orca_import` | `orca repo add` for an absolute folder. |
| `orca_worker_read` | Orchestration dispatch only. Manual panes use `orca_read`. |
| `orca_gate_list` / `orca_gate_resolve` | Decision gates. Confirm before resolve. |

The skill `skills/grokbot-orca/SKILL.md` tells the agent when to use each tool and to confirm before send / stop / gate resolve.

## Layout

```text
plugin.json                 Agent Plugins 1.0.0 manifest
mcp.json                    stdio, cwd ${PLUGIN_ROOT}, python3 ./bin/grokbot-orca-mcp.py
bin/grokbot-orca-mcp.py     stdio MCP (newline JSON + Content-Length)
lib/grokbot_orca/           zero-dependency Python
skills/grokbot-orca/SKILL.md
scripts/install-mac.sh      Mac one-liner target
tests/                      fake `orca` CLI + unittest
```

No npm install. No secrets. `ORCA_CLI_COMMAND` overrides the binary name if `orca` is not on `PATH`.

## Tests (this environment has no Orca.app)

```sh
python3 -m unittest discover -s tests -v
python3 bin/grokbot-orca-mcp.py --list-tools
```

`orca` is not installed on the Linux cloud image. Doctor is expected to fail here:

```text
$ command -v orca || true
$ python3 bin/grokbot-orca-mcp.py --doctor
# ok: false, code: orca_unavailable
```

Mac prove for EDITH, after install, with Orca.app open:

```sh
orca status --json
python3 ~/.grok/plugins/grokbot-orca/bin/grokbot-orca-mcp.py --doctor
# then in Grok Bot: 用 Orca 让 grok 做个天气网页
# then: 怎么样了
```

## Migrate from orca-bridge

orca-bridge put Grok Bot's tools on cloud Linux and reached the Mac through a Cloudflare Worker, a launchd relay, and a Linear/Slack doorbell. That is the fragile path this plugin replaces.

On the MacBook:

1. Install grokbot-orca as above.
2. In Grok Bot, remove the HTTPS MCP whose URL looks like `https://….workers.dev/t/…/mcp`.
3. Disable the orca-bridge plugin if it is still under `~/.grok/plugins/orca-bridge`.
4. You can stop `dev.orca.orca-bridge-relay` and `dev.orca.orca-bridge-notify` (`launchctl bootout gui/$(id -u)/…`). Keep them only if Hermes or OpenClaw still use orca-bridge.
5. `orca_inbox` still reads leftover `~/.config/orca-bridge/inbox.jsonl` if the grokbot-orca inbox is empty.
6. Same pane verbs remain: `orca_ps`, `orca_read`, `orca_send`. New: `orca_dispatch`, `orca_watch`, `orca_status`, `orca_stop`.

Do not copy Worker tokens into this repo. This plugin does not need them.

## Privacy

The plugin only calls the local `orca` CLI. It does not send chat to the repo author. Do not commit DSH/Grok session exports, `.env`, Orca worktrees, or `~/.config/orca-bridge/*.token`.

## License

MIT
