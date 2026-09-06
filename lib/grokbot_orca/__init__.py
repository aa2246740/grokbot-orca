"""Local Orca control for Grok Bot desktop (same Mac as Orca.app)."""

from .cli import Envelope, ExecResult, bind, orca_json, run_orca
from .meta import SERVER_NAME, __version__
from .stdio import main as stdio_main
from .tools import TOOLS, call_tool, doctor

__all__ = [
    "Envelope",
    "ExecResult",
    "SERVER_NAME",
    "TOOLS",
    "__version__",
    "bind",
    "call_tool",
    "doctor",
    "orca_json",
    "run_orca",
    "stdio_main",
]
