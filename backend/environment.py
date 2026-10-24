"""Read-only runtime context. Never infer absent operating systems from mounted disks."""
import platform
from pathlib import Path
import psutil


def detect_environment() -> dict:
    system = platform.system()
    live = False
    if system == "Linux":
        try:
            with Path("/proc/cmdline").open(encoding="utf-8") as source:
                live = "boot=live" in source.read(4096).split()
        except OSError:
            pass
    message = "The running environment is detected. Other installed operating systems are not scanned; confirm the situation below."
    if live:
        message = "You are running from a live USB. App settings may reset when you restart. Save downloaded installers and other files to a mounted storage drive, not the temporary live desktop."
    return {"running_os": system, "live_environment": live,
            "installed_os": "unknown", "message": message,
            "bootable_build_available": True, "bootable_iso_built": False}


def mounted_destinations() -> list[dict]:
    """List already mounted local filesystems only; never mount a drive."""
    rows = []
    for partition in psutil.disk_partitions(all=False):
        if partition.fstype.lower() in {"nfs", "nfs4", "cifs", "smbfs", "fuse.sshfs"} or "cdrom" in partition.opts:
            continue
        rows.append({"mountpoint": partition.mountpoint, "device": partition.device,
                     "filesystem": partition.fstype, "removable": None,
                     "note": "Mounted filesystem; removable status is not verified. Confirm its identity yourself."})
    return rows
