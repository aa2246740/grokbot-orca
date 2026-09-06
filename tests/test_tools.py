from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))

os.environ["GROKBOT_ORCA_SUBMIT_DELAY"] = "0"
os.environ["GROKBOT_ORCA_SUBMIT_RETRY"] = "0"
os.environ["GROKBOT_ORCA_POLL_S"] = "0.01"

from grokbot_orca.stdio import handle_rpc
from grokbot_orca.tools import TOOLS, call_tool
from tests.helpers import fake_runner, write_state


def payload(result: dict) -> dict:
    text = result["content"][0]["text"]
    return json.loads(text)


class DispatchTests(unittest.TestCase):
    def test_dispatch_creates_isolated_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GROKBOT_ORCA_PROJECTS"] = str(Path(tmp) / "projects")
            state = write_state(Path(tmp) / "state.json")
            result = call_tool(
                "orca_dispatch",
                {"prompt": "用 Orca 让 grok 做个天气网页 index.html"},
                runner=fake_runner(state),
            )
            body = payload(result)
            self.assertTrue(body["ok"], body)
            self.assertEqual(body["agent"], "grok")
            self.assertFalse(body["supervise"])
            self.assertTrue(body["repo"].startswith("path:"))
            self.assertIn("wt_", body["agentId"])
            saved = json.loads(state.read_text())
            create = saved["creates"][0]
            self.assertEqual(create["agent"], "grok")
            self.assertIn("--no-parent", saved["argvLog"][-2] if False else [a for a in saved["argvLog"] if a[:2] == ["worktree", "create"]][0])

    def test_dispatch_needs_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json")
            result = call_tool("orca_dispatch", {"prompt": "做个天气网页"}, runner=fake_runner(state))
            body = payload(result)
            self.assertFalse(body["ok"])
            self.assertEqual(body["code"], "need_agent")

    def test_ps_filters_by_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(
                Path(tmp) / "state.json",
                worktrees=[
                    {
                        "worktreeId": "wt_a",
                        "displayName": "weather-page",
                        "path": "/tmp/a",
                        "agents": [{"state": "working", "agentType": "grok", "interrupted": False}],
                    },
                    {
                        "worktreeId": "wt_b",
                        "displayName": "other",
                        "path": "/tmp/b",
                        "agents": [{"state": "done", "agentType": "codex", "interrupted": False}],
                    },
                ],
            )
            body = payload(call_tool("orca_ps", {"query": "weather"}, runner=fake_runner(state)))
            self.assertTrue(body["ok"])
            self.assertEqual(body["matchedPanes"], 1)
            self.assertEqual(body["panes"][0]["displayName"], "weather-page")

    def test_watch_sees_stop_hook_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GROKBOT_ORCA_CONFIG"] = str(Path(tmp) / "cfg")
            state = write_state(
                Path(tmp) / "state.json",
                worktrees=[
                    {
                        "worktreeId": "wt_done",
                        "displayName": "weather",
                        "path": tmp,
                        "agents": [{"state": "done", "agentType": "grok", "interrupted": False, "lastAssistantMessage": "wrote index.html"}],
                    }
                ],
            )
            body = payload(call_tool("orca_watch", {"worktree": "weather", "timeoutMs": 500}, runner=fake_runner(state)))
            self.assertTrue(body["ok"], body)
            self.assertEqual(body["status"], "done")

    def test_send_paste_then_enter(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json")
            body = payload(
                call_tool(
                    "orca_send",
                    {"terminal": "term_1", "text": "continue, do not touch the db"},
                    runner=fake_runner(state),
                )
            )
            self.assertTrue(body["submitted"], body)
            saved = json.loads(state.read_text())
            kinds = [(row.get("text") is not None, row.get("enter"), row.get("interrupt")) for row in saved["sends"]]
            self.assertIn((True, False, False), kinds)
            self.assertTrue(any(row.get("enter") for row in saved["sends"]))

    def test_stop_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(
                Path(tmp) / "state.json",
                worktrees=[
                    {
                        "worktreeId": "wt_1",
                        "displayName": "demo",
                        "agents": [{"state": "working", "agentType": "grok"}],
                    }
                ],
                terminals=[{"handle": "term_wt_1", "writable": True, "orphaned": False}],
            )
            body = payload(call_tool("orca_stop", {"worktree": "demo"}, runner=fake_runner(state)))
            self.assertTrue(body["ok"], body)
            self.assertTrue(body["interrupted"])

    def test_gate_list_empty_when_unbound(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json", gateError="run_required")
            body = payload(call_tool("orca_gate_list", {}, runner=fake_runner(state)))
            self.assertTrue(body["ok"])
            self.assertEqual(body["gates"], [])

    def test_inbox_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GROKBOT_ORCA_CONFIG"] = str(Path(tmp) / "cfg")
            from grokbot_orca.inbox import append_done

            item = append_done(worktree="wt_1", title="weather", summary="done")
            body = payload(call_tool("orca_inbox", {}, runner=fake_runner(write_state(Path(tmp) / "state.json"))))
            self.assertEqual(body["unread"], 1)
            self.assertEqual(body["items"][0]["id"], item["id"])
            marked = payload(
                call_tool("orca_inbox", {"mark": item["id"]}, runner=fake_runner(write_state(Path(tmp) / "s2.json")))
            )
            self.assertEqual(marked["marked"], item["id"])
            self.assertEqual(marked["unread"], 0)


class McpTests(unittest.TestCase):
    def test_initialize_and_tools_list(self):
        init = handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
            }
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "grokbot-orca")
        listed = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listed["result"]["tools"]]
        for required in (
            "orca_status",
            "orca_ps",
            "orca_dispatch",
            "orca_watch",
            "orca_inbox",
            "orca_read",
            "orca_send",
            "orca_stop",
        ):
            self.assertIn(required, names)
        self.assertEqual(len(names), len(TOOLS))

    def test_tools_call_status_with_fake_orca(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json")
            reply = handle_rpc(
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "orca_status", "arguments": {}}},
                runner=fake_runner(state),
            )
            body = json.loads(reply["result"]["content"][0]["text"])
            self.assertTrue(body["ok"])
            self.assertEqual(body["appVersion"], "1.4.193")
            self.assertEqual(body["topology"], "mac-colocated")


class StdioProcessTests(unittest.TestCase):
    def test_newline_stdio_against_fake_orca(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            state = write_state(Path(tmp) / "state.json")
            env = os.environ.copy()
            env["FAKE_ORCA_STATE"] = str(state)
            env["ORCA_CLI_COMMAND"] = str(ROOT / "tests" / "fake_orca.py")
            proc = subprocess.Popen(
                [sys.executable, str(ROOT / "bin" / "grokbot-orca-mcp.py")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(ROOT),
                env=env,
            )
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(
                    b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t"}}}\n'
                )
                proc.stdin.flush()
                init = json.loads(proc.stdout.readline().decode())
                self.assertEqual(init["result"]["serverInfo"]["name"], "grokbot-orca")
                proc.stdin.write(b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n')
                proc.stdin.flush()
                listed = json.loads(proc.stdout.readline().decode())
                names = [t["name"] for t in listed["result"]["tools"]]
                self.assertIn("orca_dispatch", names)
                proc.stdin.write(
                    b'{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"orca_status","arguments":{}}}\n'
                )
                proc.stdin.flush()
                status = json.loads(proc.stdout.readline().decode())
                body = json.loads(status["result"]["content"][0]["text"])
                self.assertTrue(body["ok"])
                self.assertEqual(body["appVersion"], "1.4.193")
            finally:
                if proc.stdin:
                    proc.stdin.close()
                proc.kill()
                proc.wait()
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()


class ManifestTests(unittest.TestCase):
    def test_plugin_json(self):
        plugin = json.loads((ROOT / "plugin.json").read_text())
        self.assertEqual(plugin["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(plugin["name"], "grokbot-orca")
        mcp = json.loads((ROOT / "mcp.json").read_text())
        self.assertEqual(mcp["$schema"], "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json")
        server = mcp["mcpServers"]["grokbot-orca"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["command"], "python3")
        self.assertEqual(server["args"], ["./bin/grokbot-orca-mcp.py"])
        self.assertEqual(server["cwd"], "${PLUGIN_ROOT}")
        skill = ROOT / "skills" / "grokbot-orca" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text()
        self.assertIn("Confirm", text)
        self.assertIn("orca_dispatch", text)


if __name__ == "__main__":
    unittest.main()
