"""Developer A: read-only Windows/Linux probes; all sizes use decimal GB."""
import os
import ctypes
import json
import math
import re
import ntpath
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
import psutil
from .environment import detect_environment

GB = 1_000_000_000

class HardwareReport(TypedDict):
    status: str
    collected_at: str
    platform: str
    cpu: str | None
    architecture: str | None
    physical_cores: int | None
    logical_cores: int | None
    cpu_max_mhz: float | None
    memory_gb: float | None
    memory_available_gb: float | None
    storage_gb: float | None
    storage_free_gb: float | None
    storage_path: str
    warnings: list[str]
    tpm: dict
    cpu_rated_clocks: dict | None


def normalize_architecture(machine: str) -> str | None:
    """Normalize kernel machine type, not Python interpreter bitness."""
    return {"amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64",
            "i386": "x86", "i686": "x86", "x86": "x86", "i586": "x86",
            "aarch64": "arm64", "arm64": "arm64", "armv7l": "armv7"}.get(machine.lower())


def cpu_name(system: str) -> str | None:
    if system == "Linux":
        try:
            # procfs is a virtual read-only system interface; bounded read.
            with Path("/proc/cpuinfo").open(encoding="utf-8") as source:
                text = source.read(65536)
            for line in text.splitlines():
                key, _, value = line.partition(":")
                if key.strip().lower() in {"model name", "hardware"} and value.strip():
                    return value.strip()
        except OSError:
            pass
    if system == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (OSError, ImportError):
            pass
    return platform.processor() or None


def detect_hardware() -> HardwareReport:
    """Probe the running host without elevation or external commands.

    Storage describes ONLY the running system filesystem (Windows system drive or /), never
    an inferred installation target or an aggregate of unrelated volumes.
    Individual probe failures retain None and produce a partial report.
    """
    system = platform.system()
    root = (ntpath.splitdrive(os.environ.get("SystemRoot", "C:/Windows"))[0] + "/") if system == "Windows" else "/"
    warnings: list[str] = []
    def probe(label, function):
        try:
            value = function()
            if value is None:
                warnings.append(f"{label} is unavailable.")
            return value
        except (OSError, RuntimeError, ValueError, NotImplementedError, psutil.Error):
            warnings.append(f"{label} could not be read.")
            return None

    memory = probe("Memory", psutil.virtual_memory)
    disk = probe("System filesystem", lambda: psutil.disk_usage(root))
    if system == "Linux" and detect_environment()["live_environment"]:
        disk = None
        warnings.append("Running from a live USB: the internal installation drive has not been selected. Storage fit still needs checking.")
    frequency = probe("CPU frequency", psutil.cpu_freq)
    architecture = probe("Architecture", lambda: normalize_architecture(platform.machine()))
    name = probe("CPU name", lambda: cpu_name(system))
    physical = probe("Physical cores", lambda: psutil.cpu_count(logical=False))
    logical = probe("Logical cores", lambda: psutil.cpu_count(logical=True))
    if system not in {"Windows", "Linux"}:
        warnings.append("This host platform has not been validated; Windows and Linux are the supported hosts.")
    maximum = frequency.max if frequency and frequency.max > 0 else None
    if frequency and maximum is None:
        warnings.append("Maximum CPU frequency is unavailable; current frequency is not a substitute.")
    return {"status": "partial" if warnings else "ok", "collected_at": datetime.now(timezone.utc).isoformat(),
            "platform": system, "cpu": name, "architecture": architecture,
            "physical_cores": physical, "logical_cores": logical, "cpu_max_mhz": maximum,
            "cpu_rated_clocks": rated_cpu_clocks(name),
            "memory_gb": memory.total / GB if memory else None,
            "memory_available_gb": memory.available / GB if memory else None,
            "storage_gb": disk.total / GB if disk else None,
            "storage_free_gb": disk.free / GB if disk else None,
            "storage_path": str(root), "warnings": warnings, "tpm": detect_tpm(system)}


# Reviewed manufacturer ratings (never substituted for OS readings).
def normalize_model(value):
    value = re.sub(r"\(r\)|\(tm\)|®|™|\bprocessor\b", " ", value, flags=re.I)
    return " ".join(value.lower().split())


def rated_cpu_clocks(name, data_dir=None):
    if not isinstance(name, str):
        return None
    if data_dir is None:
        from config import Config
        data_dir = Config.DATA_DIR
    try:
        rows = json.loads((Path(data_dir) / "cpu_specifications.json").read_text(encoding="utf-8"))
        for row in rows:
            if normalize_model(name) != normalize_model(row["model"]):
                continue
            if not row["source"].startswith("https://"):
                return None
            if not all(type(row[key]) in (int, float) and math.isfinite(row[key]) and row[key] > 0 for key in ("base_mhz", "max_boost_mhz")):
                return None
            return row
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None

# Read-only TPM device metadata.
class DeviceInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ("structVersion", "tpmVersion", "tpmInterfaceType", "tpmImpRevision")]


def windows_device_info():
    library = ctypes.WinDLL("tbs.dll", winmode=0x00000800)  # System32 only
    function = library.Tbsi_GetDeviceInfo
    function.argtypes = [ctypes.c_uint32, ctypes.POINTER(DeviceInfo)]
    function.restype = ctypes.c_uint32
    information = DeviceInfo()
    information.structVersion = 2
    code = function(ctypes.sizeof(information), ctypes.byref(information))
    return code, information.tpmVersion


def detect_tpm(system, sysfs=Path("/sys/class/tpm")):
    result = {"status": "unknown", "present": None, "version": None,
              "source": None, "message": "TPM detection is unavailable on this platform."}
    try:
        if system == "Windows":
            result["source"] = "Windows TPM Base Services"
            code, version = windows_device_info()
            if code == 0:
                result.update(status="detected", present=True, version={1: "1.2", 2: "2.0"}.get(version),
                              message="TPM detected. This checks presence/version, not provisioning or health.")
            elif code == 0x8028400F:
                result.update(status="not_detected", present=False,
                              message="No TPM is exposed to Windows. It may be absent, disabled or hidden by the environment.")
            else:
                result["message"] = f"Windows could not read TPM information (0x{code:08X})."
        elif system == "Linux":
            result["source"] = "Linux TPM sysfs"
            devices = sorted(sysfs.glob("tpm[0-9]*"))
            if not devices:
                result.update(status="not_detected", present=False,
                              message="No TPM is exposed through Linux sysfs; firmware or virtual-machine settings may hide it.")
            else:
                versions = []
                for device in devices[:16]:
                    with (device / "tpm_version_major").open(encoding="ascii") as source:
                        versions.append(source.read(16).strip())
                version = "2.0" if "2" in versions else "1.2" if "1" in versions else None
                result.update(status="detected", present=True, version=version,
                              message="TPM device detected. Provisioning and health were not tested.")
    except (OSError, AttributeError, ValueError):
        result["message"] = "TPM metadata could not be read. No TPM settings were changed."
    return result
