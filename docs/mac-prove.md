# Mac prove (EDITH)

This Linux environment has no `orca` binary and no Orca.app. Unit tests wrap a fake CLI. Real prove is on Cola's MacBook, co-located with Grok Bot desktop.

## After install

```sh
command -v orca
orca status --json
python3 ~/.grok/plugins/grokbot-orca/bin/grokbot-orca-mcp.py --doctor
```

Expect `ok: true`, `reachable: true`, empty `missing`. Then quit and reopen Grok Bot.

## Chat

1. `用 Orca 让 grok 做个天气网页` → `orca_dispatch`, new folder under `~/orca/projects/`.
2. `怎么样了` → `orca_ps` with `state` working or done.
3. Confirm, then `再跟他说别改数据库` → `orca_send`.
4. Optional `盯着做完告诉我` → `orca_watch`.

Do not test this from a cloud Linux agent against the Mac CLI. That is the topology grokbot-orca refuses.
