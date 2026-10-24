"""Developer A: opt-in, bounded microbenchmarks with a process deadline."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .hardware import HardwareReport
from .runtime import worker_command

TIMEOUT_SECONDS = 6
METRIC_NAMES = ("cpu_sha256_mib_s", "ram_copy_mib_s", "storage_read_mib_s")


def run_benchmarks(hardware: HardwareReport) -> dict:
    """Run trusted fixed workloads, never a client-supplied path or command.

    CPU: one-thread SHA-256. RAM: <=16 MiB combined buffers, limited by current
    available memory. Storage: read <=8 MiB of the Python executable, no writes.
    Storage includes OS cache effects and is NOT physical-drive throughput.
    A subprocess deadline also bounds an unexpectedly blocked filesystem read.
    """
    warnings = ["Microbenchmarks reflect current load, Python/runtime and cache effects; they do not predict OS performance.",
                "Storage is a cached file-read test of the Python executable, not an installation target or raw disk test."]
    metrics = {name: {"status": "unavailable", "value": None, "unit": "MiB/s"} for name in METRIC_NAMES}
    try:
        result = subprocess.run(worker_command("benchmark"),
                                cwd=Path(__file__).resolve().parent.parent,
                                capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                                check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        payload = json.loads(result.stdout)
        for name in METRIC_NAMES:
            metric = payload["metrics"][name]
            value = metric["value"]
            if metric["status"] not in {"ok", "unavailable"}:
                raise ValueError("Invalid worker status")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1e12):
                raise ValueError("Invalid worker measurement")
            if (metric["status"] == "ok") != (value is not None):
                raise ValueError("Worker measurement/status mismatch")
            metrics[name] = metric
        warnings.extend(payload["warnings"])
        duration = payload["duration_seconds"]
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
        # Discard partial output on worker failure; never manufacture a number.
        metrics = {name: {"status": "unavailable", "value": None, "unit": "MiB/s"} for name in METRIC_NAMES}
        warnings.append("Benchmark worker failed or exceeded its six-second deadline. No results retained.")
        duration = None
    return {"status": "ok" if all(x["status"] == "ok" for x in metrics.values()) else "partial",
            "collected_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": duration,
            "metrics": metrics, "warnings": warnings,
            "hardware_signature": {key: hardware.get(key) for key in ("architecture", "memory_gb", "storage_path")}}
