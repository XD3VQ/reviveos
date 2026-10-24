"""Worker invocations work in both Python source and frozen portable builds."""
import sys

MODULES = {"benchmark": "backend.benchmark_worker", "picker": "backend.path_picker"}


def worker_command(kind, *arguments):
    if kind not in MODULES:
        raise ValueError("Unknown worker kind.")
    if getattr(sys, "frozen", False):
        return [sys.executable, "--reviveos-worker", kind, *arguments]
    return [sys.executable, "-B", "-m", MODULES[kind], *arguments]
