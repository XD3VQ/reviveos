"""One browser launcher for source development, packaged Python, and live USB."""
import argparse
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import threading
import time
import webbrowser


def enable_worker_stdout():
    # Windowed PyInstaller executables have no Python stdout object, even when
    # a worker was started with an inherited output pipe. Restore that pipe.
    if sys.stdout is None and os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt
        ctypes.windll.kernel32.GetStdHandle.restype = wintypes.HANDLE
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        sys.stdout = os.fdopen(descriptor, "w", encoding="utf-8", buffering=1)


def dispatch_worker(arguments):
    if len(arguments) == 2 and arguments[0] == "--reviveos-self-check":
        run_self_check(Path(arguments[1]))
        return True
    if len(arguments) < 2 or arguments[0] != "--reviveos-worker":
        return False
    enable_worker_stdout()
    if arguments[1] == "benchmark":
        from backend.benchmark_worker import execute
        print(json.dumps(execute(), allow_nan=False), flush=True)
    elif arguments[1] == "picker" and len(arguments) == 3 and arguments[2] in {"files", "folder"}:
        from backend.path_picker import main
        sys.argv = [sys.argv[0], arguments[2]]
        main()
    else:
        raise SystemExit("Unknown ReviveOS worker invocation.")
    return True


def run_self_check(report_path):
    """Developer check of the actual frozen app; no personal-file operations."""
    runtime = None
    report = {"status": "failed"}
    try:
        from config import APP_DIR
        from app import create_app
        runtime = PortableRuntime(APP_DIR)
        url = runtime.start()
        app = create_app({"TESTING": True, **({"OLLAMA_URL": url} if url else {})})
        client = app.test_client()
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        report["web_shell"] = "ok"
        hardware = client.get("/api/hardware")
        assert hardware.status_code == 200
        report["hardware"] = hardware.json["data"]["status"]
        report["tpm"] = hardware.json["data"]["tpm"]
        benchmark = client.post("/api/benchmarks", json={})
        assert benchmark.status_code == 200 and benchmark.json["data"]["status"] == "ok", benchmark.json
        report["packaged_benchmark_worker"] = "ok"
        status = client.get("/api/ai/status").json["data"]
        report["bundled_ai"] = status
        if (APP_DIR / "runtime").is_dir():
            assert status["available"] and any(row["id"] == "gemma2:2b" and row["installed"] for row in status["models"])
            response = client.post("/api/ai/chat", json={"model": "gemma2:2b", "question": "I need office documents and web browsing. Suggest questionnaire applications only. Keep the explanation brief."})
            assert response.status_code == 200, response.json
            report["real_packaged_ai_answer"] = response.json["data"]
        assert client.get("/api/preferences").json["data"]["applications"] == []
        report["ai_did_not_save_preferences"] = True
        report["status"] = "passed"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if runtime is not None:
            runtime.stop()
        with report_path.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
    if report["status"] != "passed":
        raise SystemExit(1)


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


class PortableRuntime:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.process = None
        self.log = None

    def start(self):
        executable = self.folder / "runtime" / ("ollama.exe" if os.name == "nt" else "ollama")
        if not executable.is_file():
            return None
        state = self.folder / "state"
        state.mkdir(exist_ok=True)
        self.log = (state / "local-ai.log").open("ab")
        port = free_port()
        environment = os.environ.copy()
        environment.update(OLLAMA_HOST=f"127.0.0.1:{port}", OLLAMA_MODELS=str(self.folder / "models"),
                           OLLAMA_NO_CLOUD="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1",
                           OLLAMA_CONTEXT_LENGTH="4096", CUDA_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1", OLLAMA_VULKAN="0")
        self.process = subprocess.Popen([str(executable), "serve"], env=environment, cwd=self.folder,
                                        stdout=self.log, stderr=subprocess.STDOUT,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        from backend.local_ai import LocalAI
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if self.process.poll() is not None:
                return None
            if LocalAI(url).status()["available"]:
                return url
            time.sleep(.1)
        return None

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log is not None:
            self.log.close()


def serve_web(application, port=5000, browser=None, ready=None, stop_event=None):
    """Serve only loopback, open the shared UI, and drain explicit file jobs on stop."""
    from werkzeug.serving import make_server
    application.config["DEBUG"] = False
    try:
        server = make_server("127.0.0.1", port, application, threaded=True)
    except SystemExit:
        # Werkzeug reports a used port with SystemExit. Never open another app's URL.
        if port == 0:
            raise
        server = make_server("127.0.0.1", 0, application, threaded=True)
    event = stop_event if stop_event is not None else threading.Event()
    previous_signals = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_signals[signum] = signal.signal(signum, lambda *_: event.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"ReviveOS is running at {url}\nKeep this server running. Press Ctrl+C to stop after file operations finish.", flush=True)
    try:
        try:
            handle = (browser or webbrowser.open)(url)
            if handle is False:
                print(f"Browser did not open. Open {url} manually.", flush=True)
        except OSError as error:
            handle = None
            print(f"Browser could not open: {error}. Open {url} manually.", flush=True)
        if ready:
            ready(url, handle)
        event.wait()
        if application.extensions["tasks"].active():
            print("Waiting for your active file operation to finish before stopping…", flush=True)
        while application.extensions["tasks"].active():
            time.sleep(.25)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for signum, handler in previous_signals.items():
            signal.signal(signum, handler)


def main():
    from config import APP_DIR, Config
    from app import create_app
    parser = argparse.ArgumentParser(description="Open the single local ReviveOS web interface")
    parser.add_argument("--port", type=int, default=Config.PORT)
    parser.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")
    runtime = PortableRuntime(APP_DIR)
    try:
        try:
            ai_url = runtime.start()
        except OSError as error:
            ai_url = None
            print(f"Optional local AI could not start: {error}. The questionnaire still works.", flush=True)
        application = create_app({"OLLAMA_URL": ai_url} if ai_url else None)
        serve_web(application, port=args.port, browser=(lambda url: True) if args.no_browser else None)
    finally:
        runtime.stop()


if __name__ == "__main__":
    if not dispatch_worker(sys.argv[1:]):
        main()
