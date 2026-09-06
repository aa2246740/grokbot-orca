from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))

from grokbot_orca.cli import as_envelope, bind, command_names_from_agent_context, missing_required, parse_json_text
from grokbot_orca.domain import create_fresh_repo, hook_run_status, infer_agent, pick_worktree, stay_in_place, task_name
from tests.helpers import fake_runner, write_state


class InferTests(unittest.TestCase):
    def test_infer_grok_from_sentence(self):
        self.assertEqual(infer_agent(None, "帮我用 Orca 让 grok 做个上海天气网页"), "grok")

    def test_normalize_claude_and_agy(self):
        self.assertEqual(infer_agent("Claude Code", "fix login"), "claude")
        self.assertEqual(infer_agent("agy", "do it"), "antigravity")

    def test_unset_when_no_worker(self):
        self.assertIsNone(infer_agent(None, "用 Orca 做个天气网页"))

    def test_explicit_agent_wins(self):
        self.assertEqual(infer_agent("codex", "not grok this time"), "codex")


class StayTests(unittest.TestCase):
    def test_stay_is_opt_in(self):
        self.assertFalse(stay_in_place("帮我用 Orca 让 grok 做个天气网页"))
        self.assertTrue(stay_in_place("就在这个文件夹里改登录"))
        self.assertTrue(stay_in_place("stay in this folder and fix login"))


class FreshRepoTests(unittest.TestCase):
    def test_empty_git_repo(self):
        import os
        import tempfile
        from subprocess import check_output

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GROKBOT_ORCA_PROJECTS"] = tmp
            directory = create_fresh_repo(f"iso-test")
            self.assertTrue((Path(directory) / ".git").exists())
            files = check_output(["git", "-C", directory, "ls-files"], text=True).strip()
            self.assertEqual(files, "")


class WatchStatusTests(unittest.TestCase):
    def test_stop_hook_done(self):
        self.assertEqual(hook_run_status({"agents": [{"state": "done"}]}), "done")
        self.assertEqual(hook_run_status({"agents": [{"state": "working"}]}), "working")
        self.assertEqual(hook_run_status({"agents": [{"state": "done", "interrupted": True}]}), "interrupted")
        self.assertEqual(hook_run_status({"agents": []}), "unknown")

    def test_pick_worktree(self):
        rows = [
            {"worktreeId": "abc::/tmp/a", "displayName": "demo-page", "path": "/tmp/a"},
            {"worktreeId": "def::/tmp/b", "displayName": "other", "path": "/tmp/b"},
        ]
        self.assertEqual(pick_worktree(rows, "demo-page")["path"], "/tmp/a")
        self.assertEqual(pick_worktree(rows, "/tmp/b")["displayName"], "other")


class EnvelopeTests(unittest.TestCase):
    def test_parse_ignores_leading_noise(self):
        raw = parse_json_text('warn\n{"ok":true,"result":{"a":1}}\n')
        env = as_envelope(raw)
        self.assertTrue(env.ok)
        self.assertEqual(env.result, {"a": 1})

    def test_keepalive_without_ok(self):
        env = as_envelope({"name": "orca-cli", "markdown": "# hi"})
        self.assertTrue(env.ok)
        self.assertEqual(env.result["name"], "orca-cli")


class BinderTests(unittest.TestCase):
    def test_missing_worktree_create_is_drift(self):
        names = command_names_from_agent_context(
            {"schemaVersion": 1, "commands": [{"command": "status"}, {"command": "open"}]}
        )
        missing = missing_required(set(names))
        self.assertIn("worktree create", missing)

    def test_reads_commands_from_envelope(self):
        names = command_names_from_agent_context(
            {"ok": True, "result": {"schemaVersion": 1, "commands": [{"command": "worktree create"}]}}
        )
        self.assertEqual(names, ["worktree create"])

    def test_bind_fake_orca(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json")
            binder = bind(fake_runner(state))
            self.assertTrue(binder.ok)
            self.assertEqual(binder.app_version, "1.4.193")
            self.assertTrue(binder.reachable)


class TaskNameTests(unittest.TestCase):
    def test_keeps_cjk_slug(self):
        name = task_name(None, "帮我用 Orca 让 grok 做个上海天气网页")
        self.assertIn("上海天气", name)
        self.assertFalse(name.startswith("dsh-"))


if __name__ == "__main__":
    unittest.main()
