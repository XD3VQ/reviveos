"""Bounded, session-owned background tasks for explicit file operations."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import secrets
import threading

class TaskError(ValueError):
    pass

class TaskService:
    def __init__(self, capacity=32):
        self.capacity = capacity
        self._records = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reviveos-files")

    def submit(self, owner, kind, function):
        with self._lock:
            if any(row["status"] in {"queued", "running"} for row in self._records.values()):
                raise TaskError("A file operation is already active. Wait for it to finish.")
            while len(self._records) >= self.capacity:
                del self._records[next(iter(self._records))]
            token = secrets.token_urlsafe(24)
            self._records[token] = {"owner": owner, "id": token, "kind": kind, "status": "queued", "progress": {}, "result": None, "error": None}
        def update(**progress):
            with self._lock:
                self._records[token]["progress"].update(progress)
        def execute():
            with self._lock: self._records[token]["status"] = "running"
            try:
                result = function(update)
                with self._lock:
                    self._records[token].update(status="complete", result=result)
            except Exception as error:
                with self._lock:
                    self._records[token].update(status="failed", error=str(error))
        self._executor.submit(execute)
        return token

    def get(self, owner, token):
        with self._lock:
            row = self._records.get(token)
            if not row or row["owner"] != owner: raise TaskError("Task not found in this browser session.")
            return {key: deepcopy(value) for key, value in row.items() if key != "owner"}

    def active(self):
        with self._lock:
            return any(row["status"] in {"queued", "running"} for row in self._records.values())
