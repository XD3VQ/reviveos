"""Live desktop launcher. Runs as the live user; never touches raw devices."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def prepare_state(home, application, ai):
    state = home / ".local/share/reviveos"
    state.mkdir(parents=True, exist_ok=True)
    data = state / "data"
    if not data.exists():
        shutil.copytree(application / "data", data)
    os.environ["REVIVEOS_DATA_DIR"] = str(data)
    models = state / "models"
    bundled = ai / "models"
    if bundled.is_dir():
        (models / "blobs").mkdir(parents=True, exist_ok=True)
        for blob in (bundled / "blobs").iterdir():
            target = models / "blobs" / blob.name
            if blob.is_file() and not target.exists():
                target.symlink_to(blob)
        if not (models / "manifests").exists():
            shutil.copytree(bundled / "manifests", models / "manifests")
    return state, models


def main():
    import fcntl
    if os.geteuid() == 0:
        raise SystemExit("ReviveOS must run as the live desktop user, not root.")
    application = Path("/opt/reviveos")
    ai = Path("/opt/reviveos-ai")
    state, models = prepare_state(Path.home(), application, ai)
    lock = (state / "session.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        subprocess.Popen(["chromium", "--password-store=basic", "--app=http://127.0.0.1:5000/"])
        return
    engine = None
    log = (state / "local-ai.log").open("ab")
    executable = ai / "bin/ollama"
    if executable.is_file():
        environment = os.environ.copy()
        environment.update(OLLAMA_HOST="127.0.0.1:11434", OLLAMA_MODELS=str(models),
                           OLLAMA_NO_CLOUD="1", OLLAMA_NUM_PARALLEL="1",
                           OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_CONTEXT_LENGTH="4096",
                           CUDA_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1", OLLAMA_VULKAN="0")
        engine = subprocess.Popen([str(executable), "serve"], env=environment, stdout=log, stderr=log)
    sys.path.insert(0, str(application))
    from app import create_app
    from launch import serve_web
    def open_browser(url):
        # The disposable live profile has no saved accounts or persistent keyring.
        return subprocess.Popen(["chromium", "--password-store=basic", "--no-first-run",
                                 "--disable-session-crashed-bubble", "--app=" + url])
    def ready(url, browser):
        if browser is None:
            raise RuntimeError("The live browser did not start")
        (state / "session.json").write_text(json.dumps({"uid": os.geteuid(), "browser_pid": browser.pid,
            "url": url, "storage": "live-session user home", "ai_bundled": executable.is_file()}))
    try:
        serve_web(create_app(), port=5000, browser=open_browser, ready=ready)
    finally:
        if engine is not None:
            engine.terminate()
            try:
                engine.wait(timeout=10)
            except subprocess.TimeoutExpired:
                engine.kill()
                engine.wait()
        log.close()


if __name__ == "__main__":
    main()
