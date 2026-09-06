"""Spawn the local `orca` CLI and parse its JSON envelopes."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

REQUIRED_CORE: tuple[str, ...] = (
    "open",
    "status",
    "repo add",
    "worktree create",
    "worktree ps",
    "worktree show",
    "terminal create",
    "terminal send",
    "terminal wait",
    "terminal list",
    "terminal read",
    "agent-context",
)

OPTIONAL_COMMANDS: tuple[str, ...] = (
    "agent hooks status",
    "agent hooks on",
    "orchestration run-create",
    "orchestration task-create",
    "orchestration worker-start",
    "orchestration check",
    "orchestration worker-stop",
    "orchestration worker-read",
    "orchestration gate-list",
    "orchestration gate-resolve",
    "skills get",
)


@dataclass(frozen=True)
class ExecResult:
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Envelope:
    ok: bool
    result: Any = None
    error_code: str = ""
    error_message: str = ""
    error_data: Any = None


@dataclass
class Binder:
    ok: bool
    cli: str
    app_version: str | None = None
    capabilities: tuple[str, ...] = ()
    command_set: frozenset[str] = field(default_factory=frozenset)
    missing: tuple[str, ...] = ()
    optional_missing: tuple[str, ...] = ()
    code: str = ""
    message: str = ""
    reachable: bool = False


Runner = Callable[[list[str], float], ExecResult]


def resolve_cli() -> str:
    from_env = (os.environ.get("ORCA_CLI_COMMAND") or "").strip()
    return from_env or "orca"


def default_runner(cli: str) -> Runner:
    def run(args: list[str], timeout_s: float) -> ExecResult:
        exe = cli if os.path.sep in cli else shutil.which(cli)
        if exe is None:
            return ExecResult(127, "", f"orca executable not found: {cli}")
        argv = list(args)
        if "--json" not in argv and "--help" not in argv:
            argv.append("--json")
        try:
            proc = subprocess.run(
                [exe, *argv],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(124, "", f"timeout after {timeout_s}s: {cli} {' '.join(args)}")
        except OSError as err:
            return ExecResult(127, "", str(err))
        return ExecResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    return run


def parse_json_text(text: str) -> Any:
    trimmed = text.strip()
    if not trimmed:
        raise ValueError("empty orca stdout")
    try:
        return json_loads(trimmed)
    except ValueError:
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start >= 0 and end > start:
            return json_loads(trimmed[start : end + 1])
        raise ValueError("orca stdout is not JSON") from None


def json_loads(text: str) -> Any:
    import json

    return json.loads(text)


def as_envelope(raw: Any) -> Envelope:
    if not isinstance(raw, dict):
        return Envelope(ok=True, result=raw)
    if raw.get("ok") is True:
        return Envelope(ok=True, result=raw.get("result"))
    if raw.get("ok") is False:
        err = raw.get("error")
        if isinstance(err, dict):
            return Envelope(
                ok=False,
                error_code=str(err.get("code") or "orca_error"),
                error_message=str(err.get("message") or "orca error"),
                error_data=err.get("data"),
            )
        return Envelope(ok=False, error_code="orca_error", error_message=str(err or "orca error"))
    return Envelope(ok=True, result=raw)


def record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def orca_json(run: Runner, args: list[str], timeout_s: float = 30.0) -> Envelope:
    ran = run(args, timeout_s)
    try:
        raw = parse_json_text(ran.stdout)
    except ValueError as err:
        hint = ran.stderr.strip() or str(err)
        code = "invalid_runtime_response" if ran.code == 0 else "orca_unavailable"
        return Envelope(ok=False, error_code=code, error_message=hint[:2000])
    env = as_envelope(raw)
    if not env.ok:
        return env
    if ran.code not in (0, None):
        return Envelope(
            ok=False,
            error_code="orca_exit",
            error_message=ran.stderr.strip() or f"orca exited {ran.code}",
        )
    return env


def command_names_from_agent_context(raw: Any) -> list[str]:
    rec = record(raw)
    result = rec.get("result") if rec and rec.get("ok") is True else raw
    body = record(result) or rec
    commands = body.get("commands") if body else None
    if not isinstance(commands, list):
        return []
    names: list[str] = []
    for item in commands:
        row = record(item)
        if row and isinstance(row.get("command"), str):
            names.append(row["command"])
    return names


def missing_required(command_set: Mapping[str, Any] | set[str] | frozenset[str]) -> list[str]:
    return [name for name in REQUIRED_CORE if name not in command_set]


def bind(run: Runner, cli: str | None = None) -> Binder:
    resolved = cli or resolve_cli()
    try:
        ctx_run = run(["agent-context"], 15.0)
        if ctx_run.code == 127:
            return Binder(
                ok=False,
                cli=resolved,
                code="orca_unavailable",
                message=ctx_run.stderr.strip() or f"orca executable not found: {resolved}",
                missing=REQUIRED_CORE,
            )
        ctx_raw = parse_json_text(ctx_run.stdout)
    except (ValueError, OSError) as err:
        return Binder(
            ok=False,
            cli=resolved,
            code="orca_unavailable",
            message=str(err),
            missing=REQUIRED_CORE,
        )
    command_set = frozenset(command_names_from_agent_context(ctx_raw))
    missing = tuple(missing_required(command_set))
    optional_missing = tuple(name for name in OPTIONAL_COMMANDS if name not in command_set)
    if missing:
        return Binder(
            ok=False,
            cli=resolved,
            code="orca_cli_drift",
            message=f"Orca CLI is missing required commands: {', '.join(missing)}",
            missing=missing,
            optional_missing=optional_missing,
            command_set=command_set,
        )

    app_version = None
    capabilities: tuple[str, ...] = ()
    reachable = False
    status = orca_json(run, ["status"], 20.0)
    if status.ok:
        result = record(status.result) or {}
        runtime = record(result.get("runtime")) or {}
        app = record(result.get("app")) or {}
        if isinstance(runtime.get("appVersion"), str):
            app_version = runtime["appVersion"]
        caps = runtime.get("capabilities")
        if isinstance(caps, list):
            capabilities = tuple(item for item in caps if isinstance(item, str))
        reachable = runtime.get("reachable") is True or app.get("running") is True

    return Binder(
        ok=True,
        cli=resolved,
        app_version=app_version,
        capabilities=capabilities,
        command_set=command_set,
        optional_missing=optional_missing,
        reachable=reachable,
    )


def ensure_runtime(run: Runner, binder: Binder) -> Binder:
    if not binder.ok:
        return binder
    if binder.reachable:
        return binder
    opened = orca_json(run, ["open"], 60.0)
    if not opened.ok:
        return Binder(
            ok=False,
            cli=binder.cli,
            code="orca_unavailable",
            message=opened.error_message or "orca open failed",
            app_version=binder.app_version,
            command_set=binder.command_set,
        )
    live = bind(run, binder.cli)
    return live


def fail_payload(binder: Binder) -> dict[str, Any]:
    return {
        "ok": False,
        "code": binder.code or "orca_unavailable",
        "message": binder.message,
        "missing": list(binder.missing),
        "appVersion": binder.app_version,
        "topology": (
            "grokbot-orca must run on the same Mac as Grok Bot desktop and Orca.app. "
            "A Linux cloud agent cannot call this Mac's orca CLI."
        ),
    }


def run_orca(args: list[str], timeout_s: float = 30.0, runner: Runner | None = None) -> ExecResult:
    run = runner or default_runner(resolve_cli())
    return run(args, timeout_s)
