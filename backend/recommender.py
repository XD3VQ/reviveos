"""Developer A: deterministic policy scoring; no model, training or host access."""
from .compatibility import check_application_compatibility, check_os_compatibility

# These values are ReviveOS product policy, not measured distro performance.
EXPERIENCE_POLICY = {
    "linux-mint": {"beginner": 10, "comfortable": 8, "advanced": 6},
    "debian": {"beginner": 4, "comfortable": 7, "advanced": 10},
    "lubuntu": {"beginner": 7, "comfortable": 8, "advanced": 7},
}
# A development preference favors configuration flexibility; other uses favor
# a familiar default desktop. Availability checks remain the actual app evidence.
USAGE_POLICY = {"linux-mint": {"everyday": 10, "study": 10, "development": 6, "media": 8, "gaming": 5, "office": 10, "work": 8, "other": 7},
                "debian": {"everyday": 6, "study": 7, "development": 10, "media": 6, "gaming": 5, "office": 7, "work": 8, "other": 7},
                "lubuntu": {"everyday": 8, "study": 8, "development": 6, "media": 7, "gaming": 5, "office": 8, "work": 7, "other": 7}}
BENCHMARK_REFERENCES = {"cpu_sha256_mib_s": (64, 4), "ram_copy_mib_s": (512, 4), "storage_read_mib_s": (20, 2)}

# Editorial planning budgets, not publisher requirements or benchmark findings.
APP_BUDGETS = {"web-browser": (4, 2, 2000), "office": (4, 4, 2000),
               "microsoft-office": (8, 10, 2000), "code-editor": (8, 5, 2000),
               "media-player": (2, 1, 1500), "photoshop": (16, 20, 2500)}


def planning_estimates(system, applications):
    categories = system.get("categories", [])
    ram, storage, cpu = ((16, 100, 2500) if "gaming" in categories else
                         (4, 32, 1500) if "lightweight" in categories else (8, 64, 2000))
    # A rough budget must never suggest less than a known publisher minimum.
    minimum = system["minimum"]
    rows = [{"name": system["name"], "memory_gb": max(ram, minimum.get("memory_gb") or 0),
             "storage_gb": max(storage, minimum.get("storage_gb") or 0),
             "cpu_mhz": max(cpu, minimum.get("cpu_mhz") or 0)}]
    for app in applications:
        ram, storage, cpu = APP_BUDGETS.get(app["application_id"], (8, 10, 2000))
        known = {check["field"]: check["required"] for check in app["checks"]}
        rows.append({"name": app["name"], "memory_gb": max(ram, known.get("memory_gb") or 0),
                     "storage_gb": max(storage, known.get("storage_gb") or 0),
                     "cpu_mhz": max(cpu, known.get("cpu_mhz") or 0)})
    return {"basis": "ReviveOS editorial estimates; not published minimums or measured performance",
            "used_for_compatibility": False, "rows": rows}


def explain_unknown(check, subject):
    label = {"memory_gb": "memory (RAM)", "storage_gb": "storage space", "cpu_mhz": "processor speed"}.get(check["field"], check["field"])
    if check.get("unknown_reason") == "No published numeric requirement recorded":
        return f"{subject}: we do not have a published minimum for {label}, so this check is still open."
    if check.get("unknown_reason") == "Hardware measurement unavailable":
        return f"{subject}: we could not measure this computer's {label}, so this check is still open."
    return f"{subject} — {label}: {check.get('unknown_reason') or 'this still needs checking on the computer'}."


def recommend_operating_systems(hardware: dict, preferences: dict,
                              operating_systems: list[dict], benchmarks: dict | None = None,
                              applications: list[dict] | None = None) -> list[dict]:
    """Suitability uses assessed factors only. Evidence coverage is independent.

    Null factors are omitted from both numerator and denominator. A high score
    with low evidence is not a verified recommendation. Known failures exclude
    a candidate; missing evidence is a distinct review state.
    """
    results = []
    for os in operating_systems:
        compatibility = check_os_compatibility(hardware, os)
        apps = check_application_compatibility(preferences.get("applications", []), os["id"], hardware, applications)
        warnings = list(compatibility["warnings"]) + list(hardware.get("warnings", []))
        reasons, components, weights, gaps = [], {}, {}, []
        for field in ("memory_gb", "storage_gb"):
            actual, minimum = hardware.get(field), os["minimum"].get(field)
            assessed = actual is not None and minimum is not None and actual > 0
            points = 20 * max(0, 1 - minimum / actual) if assessed else None
            components[field] = round(points, 2) if assessed else None
            weights[field] = 20 if assessed else 0
            if assessed:
                reasons.append(f"{field}: {actual:.2f} GB detected, {minimum:g} GB minimum; {points:.2f}/20 headroom points.")
        known_apps = [app for app in apps if app["status"] != "unknown"]
        app_points = [{"native": 1, "alternative": .4, "unsupported": 0}[app["status"]] if app["resource_status"] != "insufficient" else 0 for app in known_apps]
        components["applications"] = round(30 * sum(app_points) / len(app_points), 2) if app_points else (30 if not apps else None)
        weights["applications"] = 30 if app_points or not apps else 0
        for app in apps:
            reasons.append(f"{app['name']}: {app['status']} availability; resource check: {app['resource_status']}.")
            if app["status"] == "unknown":
                gaps.append(f"{app['name']}: no reviewed availability evidence for {os['name']}.")
            if app["status"] == "alternative":
                gaps.append(f"{app['name']}: a substitute needs your approval; it does not satisfy the exact application automatically.")
            for check in app["checks"]:
                if check["status"] == "unknown":
                    gaps.append(explain_unknown(check, app["name"]))
            for check in app["recommended_checks"]:
                if check["status"] == "fail":
                    warnings.append(f"{app['name']}: below the published {check['field']} recommendation (not a hard minimum).")
        if not apps:
            reasons.append("No required apps selected: application fit is neutral and verifies no program.")
        experience, usage = preferences.get("experience", "beginner"), preferences.get("usage", "everyday")
        components["preferences"] = EXPERIENCE_POLICY.get(os["id"], {}).get(experience, 5) + USAGE_POLICY.get(os["id"], {}).get(usage, 5)
        if os["id"] not in EXPERIENCE_POLICY and os.get("categories"):
            # Editorial purpose matching, not a benchmark or compatibility claim.
            categories = os["categories"]
            purpose = 10 if usage == "gaming" and "gaming" in categories else 9 if usage == "development" and "development" in categories else 8 if usage in {"everyday", "office", "work", "study"} and "general" in categories else 5
            components["preferences"] = 5 + purpose
        weights["preferences"] = 20
        reasons.append(f"Preference policy: {experience} / {usage}; {components['preferences']}/20 editorial points.")
        measured_points, measured_weight = 0, 0
        for name, (reference, weight) in BENCHMARK_REFERENCES.items():
            metric = (benchmarks or {}).get("metrics", {}).get(name, {})
            value = metric.get("value") if metric.get("status") == "ok" else None
            if value is not None:
                minimum_ram = os["minimum"].get("memory_gb")
                pressure = min(1, minimum_ram / 4) if minimum_ram is not None else 1
                measured_points += weight * (1 - (1 - min(1, value / reference)) * pressure)
                measured_weight += weight
                reasons.append(f"{name}: {value:.2f} MiB/s; policy reference {reference} MiB/s, weight {weight}.")
        components["benchmarks"] = round(measured_points, 2) if measured_weight else None
        weights["benchmarks"] = measured_weight
        if measured_weight:
            warnings.extend((benchmarks or {}).get("warnings", []))
        else:
            warnings.append("No fresh benchmark measurements used. Benchmarks are omitted from suitability, not scored as poor performance.")
        status = compatibility["status"]
        if preferences.get("essential_notes"):
            gaps.append("Additional essential apps/workflows have not been verified: " + preferences["essential_notes"])
            if status != "incompatible": status = "needs_review"
        if preferences.get("usage") == "gaming":
            gaps.append("GPU, game-specific requirements, anti-cheat and peripheral support require manual checks.")
            if status != "incompatible": status = "needs_review"
        exclusions = [f"{check['field']}: detected {check['actual']} does not meet {check['required']}." for check in compatibility["checks"] if check["status"] == "fail"]
        for app in apps:
            if app["status"] == "unsupported": exclusions.append(f"Required {app['name']} has no supported native version for this OS.")
            if app["resource_status"] == "insufficient": exclusions.append(f"Required {app['name']} fails a published resource minimum.")
        preference = preferences.get("os_preference", "linux")
        current_family = "Windows" if hardware.get("platform") == "Windows" else "Linux" if hardware.get("platform") == "Linux" else None
        if preference == "windows" and os["family"] != "Windows":
            exclusions.append("You requested Windows choices only.")
        if preference == "familiar" and current_family and os["family"] != current_family:
            exclusions.append(f"You requested the familiar {current_family} OS family.")
        if exclusions:
            status = "incompatible"
        elif status != "incompatible" and any(app["status"] != "native" or app["resource_status"] == "unknown" for app in apps):
            status = "needs_review"
        checks = [check for check in compatibility["checks"] if check["field"] != "cpu_mhz" or check["required"] is not None]
        outcomes = [check["status"] for check in checks]
        if preferences.get("essential_notes"):
            outcomes.append("unknown")
        if preferences.get("usage") == "gaming":
            outcomes.append("unknown")
        for app in apps:
            outcomes.append("unknown" if app["status"] == "unknown" else "pass" if app["status"] == "native" else "fail")
            outcomes.extend(check["status"] for check in app["checks"])
        for check in checks:
            if check["status"] == "unknown":
                description = explain_unknown(check, os["name"])
                if description not in gaps: gaps.append(description)
        assessed = sum(outcome != "unknown" for outcome in outcomes)
        denominator = sum(weights.values())
        raw = sum(value for value in components.values() if value is not None)
        results.append({"os_id": os["id"], "name": os["name"], "version": os["version"], "desktop": os["desktop"],
                        "categories": os.get("categories", []), "description": os["description"],
                        "family": os["family"], "status": status,
                        "score": None if status == "incompatible" or not denominator else round(100 * raw / denominator, 2),
                        "assessed_points": round(raw, 2), "assessed_maximum": denominator,
                        "evidence": {"assessed": assessed, "total": len(outcomes), "coverage_percent": round(100 * assessed / len(outcomes)) if outcomes else 0},
                        "evidence_gaps": list(dict.fromkeys(gaps)), "exclusion_reasons": exclusions,
                        "components": components, "component_weights": weights, "reasons": reasons,
                        "warnings": list(dict.fromkeys(warnings)), "hardware_checks": compatibility["checks"],
                        "applications": apps, "sources": os["sources"], "benchmark_used": bool(measured_weight),
                        "planning_estimates": planning_estimates(os, apps),
                        "explanation": "Known failures exclude a choice. Missing evidence lowers evidence coverage, not measured suitability. Scores are policy points, not a smoothness prediction."})
    order = {"meets_known_requirements": 0, "needs_review": 1, "incompatible": 2}
    return sorted(results, key=lambda row: (order[row["status"]], -(row["score"] or 0), row["os_id"]))
