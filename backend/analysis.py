"""Small in-memory coordinator: bounded per-browser cache and one active benchmark."""
import secrets
import threading
import time
from collections import OrderedDict
from .benchmark import run_benchmarks

class BenchmarkBusy(RuntimeError):
    pass

class AnalysisService:
    """Single-process local deployment. Restart clears all measurements.

    Tokens stay in signed browser sessions; measurements stay on the server.
    Monotonic time prevents wall-clock changes extending the ten-minute TTL.
    """
    def __init__(self, ttl_seconds=600, cooldown_seconds=10, capacity=32):
        self.ttl = ttl_seconds
        self.cooldown = cooldown_seconds
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._running = threading.Lock()
        self._last_started = float("-inf")

    def run(self, hardware: dict) -> tuple[str, dict]:
        if not self._running.acquire(blocking=False):
            raise BenchmarkBusy("A benchmark is already running. Try again when it finishes.")
        try:
            now = time.monotonic()
            if now - self._last_started < self.cooldown:
                raise BenchmarkBusy("Please wait ten seconds between benchmark starts.")
            self._last_started = now
            report = run_benchmarks(hardware)
            token = secrets.token_urlsafe(24)
            with self._lock:
                self._cache[token] = (time.monotonic(), report)
                while len(self._cache) > self.capacity:
                    self._cache.popitem(last=False)
            return token, report
        finally:
            self._running.release()

    def latest(self, token: str | None, hardware: dict) -> dict | None:
        signature = {key: hardware.get(key) for key in ("architecture", "memory_gb", "storage_path")}
        with self._lock:
            entry = self._cache.get(token)
            if entry is None:
                return None
            created, report = entry
            if time.monotonic() - created > self.ttl or report["hardware_signature"] != signature:
                del self._cache[token]
                return None
            return report
