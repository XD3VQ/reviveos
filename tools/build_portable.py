"""Create a Windows portable folder. No installer or machine settings changes."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "portable")
    parser.add_argument("--runtime", type=Path, help="Prepared official Ollama CPU runtime folder")
    parser.add_argument("--models", type=Path, help="Prepared local Ollama model store")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build this Windows edition on Windows.")
    output = args.output.resolve()
    if (output / "ReviveOS").exists():
        parser.error("Output already contains ReviveOS; choose a new output directory to preserve earlier builds.")
    build = output / "build-work"
    build.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console", "--name", "ReviveOS",
               "--distpath", str(output), "--workpath", str(build), "--specpath", str(build),
               "--exclude-module", "sklearn", "--exclude-module", "numpy", "--exclude-module", "scipy",
               "--exclude-module", "pytest", "--exclude-module", "playwright"]
    for folder in ("templates", "static"):
        command.extend(["--add-data", str(ROOT / folder) + ";" + folder])
    command.append(str(ROOT / "launch.py"))
    subprocess.run(command, cwd=ROOT, check=True)
    target = output / "ReviveOS"
    shutil.copytree(ROOT / "data", target / "data", ignore=shutil.ignore_patterns("catalog-before-*", "catalog-pending-*"))
    shutil.copyfile(ROOT / "README.md", target / "README.md")
    if args.runtime:
        shutil.copytree(args.runtime, target / "runtime")
    if args.models:
        shutil.copytree(args.models, target / "models")
        for name in ("MODEL-LICENSE.txt", "model-preparation.json"):
            candidate = args.models.parent / name
            if candidate.is_file():
                shutil.copyfile(candidate, target / name)
    (target / "START-HERE.txt").write_text("Double-click ReviveOS.exe. The same ReviveOS web interface opens in your default browser. Keep the server console open; press Ctrl+C after file operations finish to stop it. Copy this ENTIRE folder; Python is included, and the EXE alone is not sufficient. This launcher needs an existing Windows system; use the separately tested ISO for USB boot. Optional AI uses a local engine only. No Windows system settings are changed.\n", encoding="utf-8")
    print(f"Portable application: {target / 'ReviveOS.exe'}")


if __name__ == "__main__":
    main()
