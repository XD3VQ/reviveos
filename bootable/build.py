"""Generate a Debian live-build project; optionally build in a disposable Linux VM.

Never targets a physical disk. Output directory must not already exist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ["live-boot", "live-config", "live-config-systemd", "systemd-sysv", "linux-image-amd64", "xserver-xorg",
            "openbox", "lightdm", "lightdm-gtk-greeter", "chromium", "python3", "python3-flask",
            "python3-psutil", "python3-tk", "ca-certificates", "pcmanfm", "network-manager",
            "network-manager-gnome", "xterm", "dbus-x11", "sudo", "locales", "console-setup",
            "firmware-linux-free", "firmware-iwlwifi", "firmware-realtek", "firmware-amd-graphics",
            "firmware-intel-graphics", "exfatprogs", "udisks2", "gvfs-backends"]


def generate(output: Path, ai_runtime: Path | None = None, models: Path | None = None) -> Path:
    if models is not None and ai_runtime is None:
        raise ValueError("A Linux AI runtime is required when including models.")
    if ai_runtime is not None and not (ai_runtime / "bin/ollama").is_file():
        raise ValueError("Linux runtime must contain bin/ollama.")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    include = output / "config" / "includes.chroot"
    application = include / "opt" / "reviveos"
    application.mkdir(parents=True)
    for name in ("app.py", "config.py", "launch.py", "README.md"):
        shutil.copyfile(ROOT / name, application / name)
    for name in ("backend", "data", "static", "templates"):
        shutil.copytree(ROOT / name, application / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(ROOT / "bootable/session.py", application / "live_session.py")
    shutil.copyfile(ROOT / "bootable/selfcheck.py", application / "live_selfcheck.py")
    if ai_runtime is not None:
        shutil.copytree(ai_runtime, include / "opt/reviveos-ai")
    if models is not None:
        shutil.copytree(models, include / "opt/reviveos-ai/models")
        licence = models.parent / "MODEL-LICENSE.txt"
        if licence.is_file():
            shutil.copyfile(licence, include / "opt/reviveos-ai/MODEL-LICENSE.txt")
    def write(relative, content):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    write("config/package-lists/reviveos.list.chroot", "\n".join(PACKAGES) + "\n")
    write("config/includes.chroot/etc/skel/.config/openbox/autostart", """#!/bin/sh
python3 -B /opt/reviveos/live_session.py >/tmp/reviveos-server.log 2>&1 &
nm-applet &
pcmanfm --desktop &
""")
    write("config/includes.chroot/usr/share/applications/reviveos.desktop", "[Desktop Entry]\nType=Application\nName=ReviveOS\nComment=Bring older computers back to life\nExec=python3 -B /opt/reviveos/live_session.py\nIcon=computer\nTerminal=false\nCategories=System;\n")
    write("config/includes.chroot/etc/systemd/system/reviveos-check.service", "[Unit]\nDescription=ReviveOS startup check\nAfter=display-manager.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -B /opt/reviveos/live_selfcheck.py\nStandardOutput=journal+console\nTimeoutStartSec=240\n[Install]\nWantedBy=multi-user.target\n")
    write("config/hooks/live/0100-reviveos.hook.chroot", "#!/bin/sh\nset -eu\nsystemctl enable lightdm NetworkManager reviveos-check.service\nchmod +x /etc/skel/.config/openbox/autostart\n")
    (output / "config/hooks/live/0100-reviveos.hook.chroot").chmod(0o755)
    write("config/includes.chroot/etc/lightdm/lightdm.conf.d/90-reviveos.conf", "[Seat:*]\nautologin-user=revive\nautologin-session=openbox\nuser-session=openbox\n")
    write("config/includes.chroot/etc/xdg/pcmanfm/default/pcmanfm.conf", "[config]\nbm_open_method=0\n[volume]\nmount_on_startup=0\nmount_removable=0\nautorun=0\n[desktop]\nwallpaper_mode=0\ndesktop_bg=#000000\ndesktop_fg=#ffffff\nshow_wm_menu=0\n")
    write("BUILD-INSTRUCTIONS.txt", "Run lb config and lb build inside this directory in a disposable Debian 13 VM. This tree is not a bootable ISO until successfully built and tested. The application includes a short guide at /guides/bootable.\n")
    write("build-inputs.json", json.dumps({"distribution": "trixie", "architecture": "amd64",
          "packages": PACKAGES, "optional_ai_included": ai_runtime is not None,
          "source_sha256": {str(path.relative_to(application)).replace('\\', '/'):
                            hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in sorted(application.rglob('*')) if path.is_file()}}, indent=2) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="New, non-existing build directory")
    parser.add_argument("--build", action="store_true", help="Run live-build here; requires root in a disposable Debian 13 VM")
    parser.add_argument("--ai-runtime", type=Path, help="Prepared Linux CPU runtime directory with bin/ollama")
    parser.add_argument("--models", type=Path, help="Prepared GGUF model store; Windows Ollama stores are portable")
    args = parser.parse_args()
    if args.build and (platform.system() != "Linux" or getattr(os, "geteuid", lambda: -1)() != 0 or not shutil.which("lb")):
        parser.error("--build requires Linux, root, and Debian live-build. Use a disposable Debian 13 VM; generation alone also works on Windows.")
    output = generate(args.output, args.ai_runtime, args.models)
    if args.build:
        subprocess.run(["lb", "config", "--mode", "debian", "--distribution", "trixie", "--architecture", "amd64",
                        "--binary-image", "iso-hybrid", "--debian-installer", "none",
                        "--archive-areas", "main contrib non-free non-free-firmware", "--apt-recommends", "true",
                        "--mirror-bootstrap", "https://deb.debian.org/debian/", "--mirror-chroot", "https://deb.debian.org/debian/",
                        "--bootloaders", "syslinux,grub-efi", "--iso-application", "ReviveOS Live Assistant",
                        "--bootappend-live", "boot=live components username=revive hostname=reviveos locales=en_US.UTF-8 console=tty0 console=ttyS0,115200n8"], cwd=output, check=True)
        subprocess.run(["lb", "build"], cwd=output, check=True)
    print(f"{'Build completed; inspect ISO output and test in a VM' if args.build else 'Build project generated; ISO has NOT been built'}: {output}")


if __name__ == "__main__":
    main()
