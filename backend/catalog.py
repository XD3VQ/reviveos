"""Developer B: validate local evidence records before exposing or using them."""
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

class CatalogError(ValueError):
    """Catalog contents or structure cannot be trusted for evaluation."""


def validate_catalog(operating_systems: list, applications: list) -> None:
    def require(condition, message):
        if not condition:
            raise CatalogError(message)
    def records(rows):
        require(isinstance(rows, list) and bool(rows), "Catalog must be a non-empty list.")
        ids = []
        for row in rows:
            require(isinstance(row, dict), "Catalog record must be an object.")
            require(isinstance(row.get("id"), str) and bool(row["id"]), "Record ID missing.")
            require(isinstance(row.get("name"), str) and bool(row["name"]), "Record name missing.")
            ids.append(row["id"])
        require(len(ids) == len(set(ids)), "Duplicate catalog IDs.")
    def evidence(item):
        require(isinstance(item, dict), "Missing source metadata.")
        require(urlparse(item.get("url", "")).scheme == "https" and bool(urlparse(item.get("url", "")).netloc), "Sources require an HTTPS URL.")
        try:
            checked = date.fromisoformat(item["checked_on"])
        except (KeyError, ValueError, TypeError) as error:
            raise CatalogError("Source requires a valid checked_on date.") from error
        require(checked <= date.today(), "Source date is in the future.")
        require(isinstance(item.get("note"), str) and bool(item["note"]), "Source note missing.")
    def resources(row, keys):
        require(isinstance(row, dict) and set(row) == set(keys), "Invalid resource fields.")
        for value in row.values():
            require(value is None or (type(value) in (int, float) and math.isfinite(value) and value > 0), "Resources must be positive finite numbers or null.")
    records(operating_systems)
    records(applications)
    os_ids = {row["id"] for row in operating_systems}
    for row in operating_systems:
        require(isinstance(row.get("categories", []), list) and all(tag in {"general", "lightweight", "gaming", "performance", "development"} for tag in row.get("categories", [])), "Invalid OS categories.")
        require(row.get("tpm_min_version") in (None, "2.0"), "Unsupported TPM requirement.")
        for field in ("version", "desktop", "family", "description"):
            require(isinstance(row.get(field), str) and bool(row[field]), f"Missing OS {field}.")
        require(isinstance(row.get("architectures"), list) and bool(row["architectures"]) and all(x in {"x86_64", "x86", "arm64", "armv7"} for x in row["architectures"]), "Invalid architectures.")
        resources(row.get("minimum"), ("memory_gb", "storage_gb", "cpu_mhz"))
        resources(row.get("recommended"), ("memory_gb", "storage_gb"))
        require(isinstance(row.get("assumptions"), list) and all(isinstance(x, str) for x in row["assumptions"]), "Invalid assumptions.")
        require(isinstance(row.get("sources"), list) and bool(row["sources"]), "OS sources missing.")
        for item in row["sources"]:
            evidence(item)
    for row in applications:
        requirements = row.get("requirements", {})
        resources(requirements.get("minimum"), ("memory_gb", "storage_gb", "cpu_mhz"))
        resources(requirements.get("recommended"), ("memory_gb", "cpu_mhz"))
        require(isinstance(requirements.get("sources"), list), "Application requirement sources missing.")
        if any(value is not None for part in ("minimum", "recommended") for value in requirements[part].values()):
            require(bool(requirements["sources"]), "Numeric app requirements require sources.")
        for item in requirements["sources"]:
            evidence(item)
        require(isinstance(row.get("availability"), dict), "Invalid application availability.")
        for os_id, entry in row["availability"].items():
            require(os_id in os_ids, "Availability references an unknown OS.")
            require(entry.get("status") in {"native", "alternative", "unsupported", "unknown"}, "Invalid compatibility status.")
            require(isinstance(entry.get("implementation"), str), "Implementation missing.")
            require(isinstance(entry.get("notes"), list) and all(isinstance(x, str) for x in entry["notes"]), "Compatibility notes missing.")
            evidence(entry.get("source"))


def load_catalog(data_dir: Path) -> tuple[list[dict], list[dict]]:
    try:
        systems = json.loads((Path(data_dir) / "operating_systems.json").read_text(encoding="utf-8"))
        apps = json.loads((Path(data_dir) / "applications.json").read_text(encoding="utf-8"))
        validate_catalog(systems, apps)
        return systems, apps
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise CatalogError("Catalog is unavailable or invalid; check the local JSON files and source metadata.") from error
