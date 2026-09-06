from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE = ROOT / "tests" / "fake_orca.py"


def write_state(path: Path, **updates) -> Path:
    from tests.fake_orca import default_state

    state = default_state()
    state.update(updates)
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def fake_runner(state_file: Path):
    from grokbot_orca.cli import ExecResult

    def run(args: list[str], timeout_s: float) -> ExecResult:
        env = os.environ.copy()
        env["FAKE_ORCA_STATE"] = str(state_file)
        proc = subprocess.run(
            [sys.executable, str(FAKE), *args],
            capture_output=True,
            text=True,
            timeout=timeout_s + 2,
            env=env,
            check=False,
        )
        return ExecResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    return run
