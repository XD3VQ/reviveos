"""Developer B: evidence-based availability and resource checks, no host probing."""
from .catalog import load_catalog


def check_resources(hardware: dict, requirements: dict) -> list[dict]:
    """Compare decimal GB and MHz. Null is unknown, never zero or success."""
    checks = []
    for field, measured in [("memory_gb", "memory_gb"), ("storage_gb", "storage_gb"), ("cpu_mhz", "cpu_max_mhz")]:
        if field not in requirements:
            continue
        required, actual = requirements.get(field), hardware.get(measured)
        status = "unknown" if required is None or actual is None else ("pass" if actual >= required else "fail")
        unknown_reason = "No published numeric requirement recorded" if required is None else "Hardware measurement unavailable" if actual is None else None
        checks.append({"field": field, "required": required, "actual": actual, "status": status, "unknown_reason": unknown_reason})
    return checks


def check_os_compatibility(hardware: dict, operating_system: dict) -> dict:
    """Evaluate only catalogued image architecture and numeric minimums.

    Storage capacity is a screening value, not permission or proof of free
    installable partition space. GPU, firmware and peripherals are unverified.
    """
    architecture = hardware.get("architecture")
    checks = [{"field": "architecture", "required": operating_system["architectures"], "actual": architecture,
               "status": "unknown" if architecture is None else ("pass" if architecture in operating_system["architectures"] else "fail")}]
    checks.extend(check_resources(hardware, operating_system["minimum"]))
    if operating_system.get("tpm_min_version") == "2.0":
        tpm = hardware.get("tpm") or {}
        version = tpm.get("version") if tpm.get("status") == "detected" else None
        checks.append({"field": "TPM version", "required": "2.0", "actual": version,
                       "status": "pass" if version == "2.0" else "fail" if version == "1.2" else "unknown",
                       "unknown_reason": tpm.get("message", "TPM information unavailable") if version is None else None})
    # An unspecified CPU speed is not an invented requirement. RAM and disk
    # minimums, however, are essential to assess resource feasibility.
    critical = [x for x in checks if x["field"] != "cpu_mhz" or x["required"] is not None]
    status = "incompatible" if any(x["status"] == "fail" for x in critical) else (
        "needs_review" if any(x["status"] == "unknown" for x in critical) else "meets_known_requirements")
    warnings = list(operating_system["assumptions"])
    warnings.append("Graphics, display, Wi-Fi, firmware and boot support have not been verified. Test a live environment before installation.")
    free = hardware.get("storage_free_gb")
    needed = operating_system["minimum"]["storage_gb"]
    if needed is not None and (free is None or free < needed):
        warnings.append("Current system-filesystem free space is unknown or below the OS minimum. It is not an installation target assessment.")
    for requirement in operating_system.get("additional_requirements", []):
        checks.append({"field": requirement, "required": "Vendor verification required", "actual": None, "status": "unknown"})
        if status != "incompatible":
            status = "needs_review"
    return {"status": status, "checks": checks, "warnings": warnings}


def check_application_compatibility(application_ids: list[str], os_id: str,
                                    hardware: dict | None = None,
                                    applications: list[dict] | None = None) -> list[dict]:
    """Return sourced availability separately from hardware requirement checks.

    Unknown IDs and missing OS/application evidence stay unknown. An alternative
    never satisfies an exact required application automatically. This function
    does not inspect installed apps or download/install anything.
    """
    if applications is None:
        from config import Config
        _, applications = load_catalog(Config.DATA_DIR)
    by_id = {item["id"]: item for item in applications}
    results = []
    for app_id in dict.fromkeys(application_ids):
        application = by_id.get(app_id)
        entry = application.get("availability", {}).get(os_id) if application else None
        requirements = application["requirements"] if application else {"minimum": {}, "recommended": {}, "sources": []}
        checks = check_resources(hardware or {}, requirements["minimum"])
        advisories = check_resources(hardware or {}, requirements["recommended"])
        failed = any(item["status"] == "fail" for item in checks)
        required_checks = [item for item in checks if item["required"] is not None]
        resource_status = "insufficient" if failed else (
            "meets_known_requirements" if required_checks and all(item["status"] == "pass" for item in required_checks) else "unknown")
        results.append({"application_id": app_id, "name": application["name"] if application else app_id,
                        "os_id": os_id, "status": entry["status"] if entry else "unknown",
                        "implementation": entry["implementation"] if entry else None,
                        "source": entry["source"] if entry else None,
                        "notes": entry["notes"] if entry else ["No reviewed evidence for this application/OS pair."],
                        "resource_status": resource_status, "checks": checks,
                        "recommended_checks": advisories, "requirement_sources": requirements["sources"]})
    return results
