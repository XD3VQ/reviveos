"""Fixed, short-lived benchmark worker. No filesystem writes or shell commands."""
import hashlib
import json
import sys
import time
from pathlib import Path
import psutil

MIB = 1024 * 1024
DURATION = 0.20
MAX_READ_BYTES = 8 * MIB


def measure_cpu() -> float:
    data = bytes(64 * 1024)
    total = 0
    start = time.perf_counter()
    while time.perf_counter() - start < DURATION:
        hashlib.sha256(data).digest()
        total += len(data)
    return total / MIB / (time.perf_counter() - start)


def measure_ram() -> float:
    available = psutil.virtual_memory().available
    if available < 32 * MIB:
        raise MemoryError("Less than 32 MiB available; RAM benchmark skipped.")
    # Two buffers together consume at most 1/32 of available RAM, capped at 16 MiB.
    size = min(8 * MIB, available // 64)
    source, target = bytearray(size), bytearray(size)
    total = 0
    start = time.perf_counter()
    while time.perf_counter() - start < DURATION:
        target[:] = source
        total += size
    return total / MIB / (time.perf_counter() - start)


def measure_storage() -> float:
    total = 0
    start = time.perf_counter()
    # Existing trusted executable only; read-only, no raw devices or user files.
    with Path(sys.executable).open("rb") as source:
        while total < MAX_READ_BYTES and time.perf_counter() - start < DURATION:
            chunk = source.read(min(64 * 1024, MAX_READ_BYTES - total))
            if not chunk:
                break
            total += len(chunk)
    if not total:
        raise OSError("No bytes read from the runtime executable.")
    return total / MIB / (time.perf_counter() - start)


def execute() -> dict:
    start = time.perf_counter()
    metrics, warnings = {}, []
    for name, function in [("cpu_sha256_mib_s", measure_cpu), ("ram_copy_mib_s", measure_ram), ("storage_read_mib_s", measure_storage)]:
        try:
            metrics[name] = {"status": "ok", "value": function(), "unit": "MiB/s"}
        except (OSError, MemoryError, RuntimeError, psutil.Error) as error:
            metrics[name] = {"status": "unavailable", "value": None, "unit": "MiB/s"}
            warnings.append(f"{name}: {type(error).__name__}; measurement unavailable.")
    return {"metrics": metrics, "warnings": warnings, "duration_seconds": time.perf_counter() - start}

if __name__ == "__main__":
    print(json.dumps(execute(), allow_nan=False))
