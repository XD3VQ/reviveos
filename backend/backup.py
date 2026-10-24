"""Explicit, additive file backup. No overwrites, links, system images or deletion."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import time

class BackupError(ValueError):
    pass

MAX_FILES = 20000
MAX_BYTES = 100 * 1024**3


def checked_path(value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
        raise BackupError("Choose an existing absolute file/folder path.")
    raw = Path(value)
    for part in [raw, *raw.parents]:
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackupError("Symbolic links, junctions and reparse paths are not supported.")
    return raw.resolve(strict=True)


def inspect_backup(sources: list[str], destination: str) -> dict:
    """Read-only plan: reject overlapping sources, recursive targets, and links."""
    if not isinstance(sources, list) or not 1 <= len(sources) <= 20:
        raise BackupError("Choose one to twenty source files/folders.")
    target = checked_path(destination)
    if not target.is_dir(): raise BackupError("Destination must be an existing folder on the chosen backup drive.")
    roots = [checked_path(value) for value in sources]
    for index, root in enumerate(roots):
        if root == Path(root.anchor): raise BackupError("Choose personal files/folders, not an entire system drive.")
        if target == root or target.is_relative_to(root): raise BackupError("Backup destination cannot be inside a selected source.")
        if root.is_relative_to(target): raise BackupError("Choose a destination outside the selected source tree.")
        if any(root == other or root.is_relative_to(other) or other.is_relative_to(root) for other in roots[:index]):
            raise BackupError("Selected sources overlap; select each tree once.")
    entries, total = [], 0
    started = time.monotonic()
    def add(path, relative):
        nonlocal total
        checked = checked_path(str(path))
        info = checked.stat()
        if not stat.S_ISREG(info.st_mode): raise BackupError("Only regular files are supported.")
        total += info.st_size
        if len(entries) >= MAX_FILES or total > MAX_BYTES or time.monotonic() - started > 15:
            raise BackupError("Selection exceeds the preview limits: 20,000 files, 100 GiB, or 15 seconds. Split it into smaller backups.")
        entries.append({"source": str(checked), "relative": str(relative), "size": info.st_size, "mtime_ns": info.st_mtime_ns})
    for index, root in enumerate(roots):
        prefix = Path(f"{index+1:02d}-{root.name}")
        if root.is_file(): add(root, prefix)
        else:
            def fail(error): raise BackupError(f"Cannot inspect a selected folder: {error}")
            for current, directories, files in os.walk(root, followlinks=False, onerror=fail):
                if time.monotonic() - started > 15:
                    raise BackupError("Folder inspection exceeded 15 seconds. Select a smaller tree.")
                for name in directories: checked_path(str(Path(current) / name))
                for name in files:
                    child = Path(current) / name
                    add(child, prefix / child.relative_to(root))
    if not entries: raise BackupError("No regular files found in the selection.")
    free = shutil.disk_usage(target).free
    if free < total + 16 * 1024**2: raise BackupError("Destination has insufficient free space, including a 16 MiB safety margin.")
    same_device = any(root.stat().st_dev == target.stat().st_dev for root in roots)
    return {"sources": [str(root) for root in roots], "destination": str(target), "entries": entries,
            "file_count": len(entries), "total_bytes": total, "created_monotonic": time.monotonic(),
            "warnings": (["Source and destination share a filesystem. This does not protect against losing that drive; use a separate physical drive."] if same_device else []) + ["A file backup is not a bootable system image or an automatic OS rollback. Confirm the destination is a separate physical drive; this tool cannot certify that."]}


def copy_backup(plan: dict, update=lambda **values: None) -> dict:
    """Copy only previewed files into a unique folder; verify every copied hash.

    Incomplete output stays labelled incomplete; no cleanup deletes user files.
    This handles ordinary file copies, not live databases, ACLs or system restore.
    """
    if time.monotonic() - plan["created_monotonic"] > 600: raise BackupError("Backup preview expired. Preview the selection again.")
    destination = checked_path(plan["destination"])
    if shutil.disk_usage(destination).free < plan["total_bytes"] + 16 * 1024**2: raise BackupError("Insufficient destination space.")
    folder = destination / ("ReviveOS-backup-" + secrets.token_hex(8))
    folder.mkdir(exist_ok=False)
    manifest = {"status": "incomplete", "files": [], "warnings": plan["warnings"]}
    manifest_path = folder / "backup-manifest.json"
    def write_manifest():
        with manifest_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2)
    copied_bytes = 0
    try:
        for number, entry in enumerate(plan["entries"], 1):
            source = checked_path(entry["source"])
            before = source.stat()
            if before.st_size != entry["size"] or before.st_mtime_ns != entry["mtime_ns"]:
                raise BackupError("A source file changed since preview. Start a fresh preview.")
            target = folder / entry["relative"]
            if not target.is_relative_to(folder): raise BackupError("Invalid backup path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(source, flags), "rb") as original, target.open("xb") as output:
                opened = os.fstat(original.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino): raise BackupError("Source identity changed.")
                count = 0
                while chunk := original.read(1024**2):
                    count += len(chunk)
                    if count > entry["size"]: raise BackupError("Source grew during backup.")
                    output.write(chunk); digest.update(chunk)
                output.flush(); os.fsync(output.fileno())
            after = source.stat()
            if count != entry["size"] or after.st_mtime_ns != before.st_mtime_ns: raise BackupError("Source changed while copying.")
            verify = hashlib.sha256()
            with target.open("rb") as copied:
                while chunk := copied.read(1024**2): verify.update(chunk)
            if verify.digest() != digest.digest(): raise BackupError("Copied file failed verification.")
            copied_bytes += count
            manifest["files"].append({"path": entry["relative"], "bytes": count, "sha256": digest.hexdigest()})
            update(files_copied=number, total_files=plan["file_count"], bytes_copied=copied_bytes)
        manifest["status"] = "complete"
        write_manifest()
    except Exception as error:
        manifest["status"] = "incomplete"
        manifest["error"] = str(error)
        if not manifest_path.exists(): write_manifest()
        raise BackupError(f"Backup incomplete in {folder}: {error}. Partial output retained; do not rely on it.") from error
    return {"status": "complete", "folder": str(folder), "file_count": len(manifest["files"]), "bytes_copied": copied_bytes, "verification": "SHA-256 matched for every copied file", "warnings": plan["warnings"]}
