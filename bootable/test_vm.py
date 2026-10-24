"""Boot an ISO in an isolated VM. No host disks or directories are attached."""
import argparse
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time


def qmp_command(socket_path, name, arguments=None):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(str(socket_path))
        stream = connection.makefile("rwb")
        json.loads(stream.readline())
        def command(name, arguments=None):
            stream.write((json.dumps({"execute": name, **({"arguments": arguments} if arguments else {})}) + "\n").encode())
            stream.flush()
            while True:
                answer = json.loads(stream.readline())
                if "return" in answer:
                    return answer["return"]
                if "error" in answer:
                    raise RuntimeError(answer["error"])
        command("qmp_capabilities")
        return command(name, arguments)


def screenshot(socket_path, output):
    qmp_command(socket_path, "screendump", {"filename": str(output)})


def run(iso, output, mode, timeout=240):
    if not iso.is_file() or iso.suffix.lower() != ".iso":
        raise ValueError("Select a regular ISO file, never a device.")
    output.mkdir(parents=True, exist_ok=False)
    serial = output / "serial.log"
    control = output / "qmp.sock"
    command = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-smp", "2", "-m", "4096",
               "-boot", "d", "-cdrom", str(iso), "-display", "none", "-vga", "std",
               "-serial", "file:" + str(serial), "-monitor", "none", "-no-reboot",
               "-qmp", f"unix:{control},server=on,wait=off", "-nic", "user,restrict=on"]
    if mode == "uefi":
        firmware = Path("/usr/share/OVMF")
        variables = output / "OVMF_VARS.fd"
        shutil.copyfile(firmware / "OVMF_VARS_4M.fd", variables)
        command.extend(["-drive", f"if=pflash,format=raw,readonly=on,file={firmware / 'OVMF_CODE_4M.fd'}",
                        "-drive", f"if=pflash,format=raw,file={variables}"])
    report = {"status": "failed", "boot_mode": mode, "iso": str(iso)}
    with (output / "qemu.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            # Debian's boot menu waits for Enter; select its default live entry.
            time.sleep(25 if mode == "uefi" else 15)
            if control.exists() and process.poll() is None:
                qmp_command(control, "human-monitor-command", {"command-line": "sendkey ret"})
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and process.poll() is None:
                text = serial.read_text(errors="replace") if serial.exists() else ""
                matches = re.findall(r"REVIVEOS_BOOT_CHECK (\{[^\r\n]+\})", text)
                if matches:
                    try:
                        guest = json.loads(matches[-1])
                    except json.JSONDecodeError:
                        # Serial output can be read halfway through a JSON line.
                        pass
                    else:
                        report["guest"] = guest
                        report["status"] = guest["status"]
                        break
                time.sleep(1)
            if report["status"] != "passed":
                report["error"] = "Guest did not report a successful startup. Inspect serial.log and the screenshot."
            if process.poll() is None and control.exists():
                # Allow Chromium's first page paint after guest startup checks.
                time.sleep(40)
                screenshot(control, output / "desktop.ppm")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["bios", "uefi"], required=True)
    args = parser.parse_args()
    report = run(args.iso.resolve(), args.output.resolve(), args.mode)
    print(json.dumps(report, indent=2), flush=True)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
