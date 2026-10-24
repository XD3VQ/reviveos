"""Prepare a CPU-only portable Ollama store from the official verified archive."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from launch import PortableRuntime
from backend.local_ai import LocalAI, MODELS

ARCHIVE_SHA256 = "bda4a493ba8a7c24d57263cd843cd68cee84f44aed4299eeed532acad7eda12a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True, help="Official Ollama v0.40.11 Windows amd64 ZIP")
    parser.add_argument("--output", type=Path, required=True, help="New portable AI preparation directory")
    parser.add_argument("--model", choices=list(MODELS), default="gemma2:2b")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output folder; existing preparations are preserved.")
    digest = hashlib.sha256()
    with args.archive.open("rb") as source:
        while chunk := source.read(4 * 1024**2):
            digest.update(chunk)
    if digest.hexdigest() != ARCHIVE_SHA256:
        parser.error("Official runtime archive SHA-256 does not match the pinned release.")
    runtime_dir = args.output.resolve() / "runtime"
    runtime_dir.mkdir(parents=True)
    with ZipFile(args.archive) as archive:
        for entry in archive.infolist():
            parts = Path(entry.filename).parts
            if entry.is_dir() or any(part.startswith("cuda") or part == "vulkan" for part in parts):
                continue
            if entry.filename != "ollama.exe" and not entry.filename.startswith("lib/ollama/"):
                continue
            if Path(entry.filename).is_absolute() or ".." in parts:
                raise ValueError("Unsafe archive path.")
            target = runtime_dir / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("xb") as output:
                while chunk := source.read(1024**2):
                    output.write(chunk)
    with urlopen("https://raw.githubusercontent.com/ollama/ollama/v0.40.11/LICENSE", timeout=15) as response:
        (runtime_dir / "OLLAMA-LICENSE.txt").write_bytes(response.read(128 * 1024))
    runtime = PortableRuntime(args.output.resolve())
    try:
        url = runtime.start()
        if not url:
            raise RuntimeError("CPU runtime did not start; inspect the preparation state/local-ai.log.")
        engine = LocalAI(url)
        print("Portable CPU engine started. Preparing requested local model:", args.model, flush=True)
        last = {"bytes": 0, "status": ""}
        def progress(**values):
            completed = values.get("completed") or 0
            status = values.get("status") or ""
            if completed - last["bytes"] >= 64 * 1024**2 or status != last["status"]:
                print(f"{status}: {completed // 1024**2} MiB", flush=True)
                last.update(bytes=completed, status=status)
        result = engine.pull(args.model, progress)
        details = engine.json_request("/api/show", {"model": args.model}, timeout=15)
        (args.output / "MODEL-LICENSE.txt").write_text(details.get("license", "See the official model terms at https://ollama.com/library/" + args.model), encoding="utf-8")
        (args.output / "model-preparation.json").write_text(json.dumps({"model": args.model, "runtime": "Ollama v0.40.11 CPU-only",
            "runtime_archive_sha256": ARCHIVE_SHA256, "status": result["status"], "source": "https://ollama.com/library/" + args.model}, indent=2), encoding="utf-8")
        print("Model prepared locally; no paid API used.", flush=True)
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
