"""HTTP boundaries for guided preparation, and local AI."""
from collections import OrderedDict
import secrets
import threading
import json
import subprocess
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request, session
from .backup import inspect_backup, copy_backup
from .downloads import download_image, PROVIDERS
from .environment import detect_environment, mounted_destinations
from .hardware import detect_hardware
from .installer import prepare_installation
from .recommender import recommend_operating_systems
from .tasks import TaskError
from .runtime import worker_command
from .catalog import load_catalog
from .local_ai import AIError, MODELS


def respond(data=None, message="", code=200):
    return jsonify(status="error" if code >= 400 else "ok", data=data, message=message), code


def owner():
    if "workflow_owner" not in session:
        session["workflow_owner"] = secrets.token_urlsafe(24)
    return session["workflow_owner"]


def body(fields):
    value = request.get_json(silent=True)
    if not isinstance(value, dict) or set(value) - set(fields):
        raise ValueError("Send a JSON object with the expected fields only.")
    return value


# Backup, download, and installation preparation.
def create_workflow_blueprint(catalog):
    blueprint = Blueprint("workflow", __name__)
    plans, lock = OrderedDict(), threading.Lock()

    def assessed_choice(os_id):
        if not isinstance(os_id, str) or os_id not in session.get("shortlist", []):
            raise ValueError("Keep one or two OS choices before preparing installation.")
        systems, apps = catalog()
        hardware = detect_hardware()
        benchmarks = current_app.extensions["analysis"].latest(session.get("benchmark_token"), hardware)
        rows = recommend_operating_systems(hardware, session.get("preferences", {}), systems, benchmarks, apps)
        row = next((row for row in rows if row["os_id"] == os_id), None)
        if row is None or row["status"] == "incompatible": raise ValueError("This choice now fails known requirements or preferences. Compare again.")
        if row["status"] == "needs_review" and session.get("review_ack") is not True:
            raise ValueError("Review and acknowledge the evidence gaps before continuing.")
        return row

    @blueprint.errorhandler(ValueError)
    @blueprint.errorhandler(OSError)
    def invalid(error):
        return respond(message=str(error), code=400)

    @blueprint.errorhandler(TaskError)
    def task_busy(error):
        return respond(message=str(error), code=409)

    @blueprint.post("/api/paths/pick")
    def pick_path():
        value = body({"kind"})
        if not isinstance(value.get("kind"), str) or value["kind"] not in {"files", "folder"}:
            raise ValueError("Choose files or folder.")
        try:
            result = subprocess.run(worker_command("picker", value["kind"]),
                                    cwd=Path(__file__).resolve().parent.parent, capture_output=True,
                                    text=True, timeout=120, check=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            payload = json.loads(result.stdout)
            if "error" in payload: raise ValueError(payload["error"])
            return respond(payload)
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
            raise ValueError("Picker unavailable or timed out. Enter an absolute path manually.") from error

    @blueprint.get("/guides/bootable")
    def bootable_guide():
        return current_app.response_class(
            "ReviveOS bootable USB\n\n"
            "Use the separately built ReviveOS ISO. A Windows EXE is not a bootable image. "
            "Test the resulting ISO in a VM before preparing a physical USB.\n\n"
            "For two USB partitions, Ventoy provides a large data partition and a small boot partition. "
            "Installing Ventoy erases the selected USB: confirm its identity and save its files first. "
            "Copy ReviveOS.iso onto the data partition. Boot the USB, select the ISO, then choose Live system.\n\n"
            "Save downloads to a mounted storage drive; live desktop settings reset after restart. "
            "The download demo creates no installer. Obtain and verify real installers from their publishers. "
            "Secure Boot and physical-device compatibility require separate checks.\n\n"
            "Official USB preparation instructions: https://www.ventoy.net/en/doc_start.html\n",
            mimetype="text/plain")

    @blueprint.get("/api/workflow")
    def workflow():
        return respond({"environment": detect_environment(), "entry_branch": session.get("entry_branch"),
                        "shortlist": session.get("shortlist", []), "backup_confirmation": session.get("backup_confirmation"),
                        "backup_task": session.get("backup_task"), "download_task": session.get("download_task"),
                        "handoff": session.get("handoff"),
                        "windows_check_url": "https://www.microsoft.com/en-us/windows/windows-11-specifications"})

    @blueprint.post("/api/workflow/start")
    def entry():
        value = body({"existing_os"})
        if not isinstance(value.get("existing_os"), str) or value["existing_os"] not in {"yes", "no", "unsure"}: raise ValueError("Confirm yes, no, or unsure.")
        session["entry_branch"] = value["existing_os"]
        return respond({"branch": value["existing_os"], "next": "preferences",
                        "guidance": "Continue from your existing OS." if value["existing_os"] == "yes" else "Use a separately prepared live USB to run ReviveOS on a machine without a working OS. Open the bootable USB guide for preparation steps."})

    @blueprint.post("/api/shortlist")
    def shortlist():
        value = body({"os_ids", "acknowledge_review"})
        ids = value.get("os_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 2 or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("Keep one or two different operating systems.")
        systems, apps = catalog()
        hardware = detect_hardware()
        rows = recommend_operating_systems(hardware, session.get("preferences", {}), systems, current_app.extensions["analysis"].latest(session.get("benchmark_token"), hardware), apps)
        by_id = {row["os_id"]: row for row in rows}
        if any(item not in by_id or by_id[item]["status"] == "incompatible" for item in ids):
            raise ValueError("Excluded or unknown choices cannot be kept.")
        if any(by_id[item]["status"] == "needs_review" for item in ids) and value.get("acknowledge_review") is not True:
            raise ValueError("Acknowledge the specific unverified requirements before keeping a review choice.")
        session["shortlist"] = ids
        session["review_ack"] = value.get("acknowledge_review") is True
        session.pop("backup_confirmation", None)
        session.pop("handoff", None)
        return respond({"shortlist": ids}, "Choices saved. Continue to backup and installation preparation.")

    @blueprint.get("/api/destinations")
    def destinations():
        return respond(mounted_destinations(), "Already mounted filesystems only. Choose and verify the correct destination yourself.")

    @blueprint.post("/api/backup/preview")
    def preview():
        value = body({"sources", "destination"})
        if not session.get("shortlist"): raise ValueError("Keep an OS choice before the backup checkpoint.")
        plan = inspect_backup(value.get("sources"), value.get("destination"))
        token = secrets.token_urlsafe(24)
        with lock:
            plans[token] = (owner(), plan)
            while len(plans) > 32: plans.popitem(last=False)
        return respond({"plan_id": token, **{key: plan[key] for key in ("sources", "destination", "file_count", "total_bytes", "warnings")}}, "Preview only. No files copied. This plan expires after ten minutes.")

    @blueprint.post("/api/backup/start")
    def backup_start():
        value = body({"plan_id", "consent"})
        if value.get("consent") is not True: raise ValueError("Explicit backup consent is required.")
        token = value.get("plan_id")
        if not isinstance(token, str): raise ValueError("Preview a backup first.")
        with lock:
            record = plans.get(token)
            if not record or record[0] != owner(): raise ValueError("Backup preview not found for this session.")
            plan = record[1]
            task = current_app.extensions["tasks"].submit(owner(), "backup", lambda update: copy_backup(plan, update))
            del plans[token]
        session["backup_task"] = task
        session.pop("backup_confirmation", None)
        return respond({"task_id": task}, "Backup started into a new folder. Existing files are not overwritten.", 202)

    @blueprint.post("/api/backup/confirm")
    def backup_confirm():
        value = body({"method", "confirmed"})
        if not session.get("shortlist") or value.get("confirmed") is not True or not isinstance(value.get("method"), str) or value["method"] not in {"external", "reviveos"}:
            raise ValueError("Confirm that you inspected a separate-drive backup before continuing.")
        if value["method"] == "reviveos":
            task = current_app.extensions["tasks"].get(owner(), session.get("backup_task"))
            if task["kind"] != "backup" or task["status"] != "complete": raise ValueError("The ReviveOS backup is not complete.")
        session["backup_confirmation"] = {"method": value["method"], "confirmed": True,
                                           "verification": "user_attestation"}
        return respond(session["backup_confirmation"], "Your backup confirmation was recorded; this is not a verified system-recovery image.")

    @blueprint.get("/api/installation/<os_id>")
    def preparation(os_id):
        row = assessed_choice(os_id)
        systems, _ = catalog()
        record = next(item for item in systems if item["id"] == os_id)
        return respond({**prepare_installation(os_id, record), "assessment": row, "backup_confirmation": session.get("backup_confirmation")})

    @blueprint.post("/api/downloads/demo")
    def download_demo():
        value = body({"os_id", "destination", "consent"})
        if value.get("consent") is not True:
            raise ValueError("Confirm that you understand this is a demo.")
        systems, _ = catalog()
        if value.get("os_id") not in {row["id"] for row in systems}:
            raise ValueError("Choose an operating system from the catalog.")
        return respond({"demo": True, "downloaded": False, "verified": False,
                        "steps": ["Demo: choose the official installer.",
                                  "Demo: choose where to save it.",
                                  "Demo: download and verify it using the publisher's instructions.",
                                  "No file was created. Obtain a real installer before preparing a USB."]},
                       "Demo finished. Nothing was downloaded or verified; no installer is ready.")

    @blueprint.post("/api/downloads/start")
    def download_start():
        value = body({"os_id", "destination", "consent"})
        if value.get("consent") is not True: raise ValueError("Explicit permission to download is required.")
        if not session.get("backup_confirmation"): raise ValueError("Complete the backup checkpoint before downloading.")
        os_id = value.get("os_id")
        assessed_choice(os_id)
        if os_id not in PROVIDERS: raise ValueError("Use the official manual download instructions for this OS.")
        from .backup import checked_path
        destination = str(checked_path(value.get("destination")))
        task = current_app.extensions["tasks"].submit(owner(), "download", lambda update: download_image(os_id, destination, update))
        session["download_task"] = task
        return respond({"task_id": task}, "Download explicitly requested. Signature verification remains a separate step.", 202)

    @blueprint.get("/api/tasks/<token>")
    def task_status(token):
        try: return respond(current_app.extensions["tasks"].get(owner(), token))
        except TaskError: return respond(message="Task not found for this session.", code=404)

    @blueprint.post("/api/installation/handoff")
    def handoff():
        value = body({"os_id", "method", "device_label", "media_verified", "signature_verified", "recovery_ack", "usb_erasure_ack", "separate_usb_confirmed"})
        assessed_choice(value.get("os_id"))
        if not session.get("backup_confirmation"): raise ValueError("Confirm a backup first.")
        if not isinstance(value.get("method"), str) or value["method"] not in {"rufus", "manual"}: raise ValueError("Choose a supported manual media-creation method.")
        label = value.get("device_label")
        if not isinstance(label, str) or not 3 <= len(label.strip()) <= 200: raise ValueError("Record the USB's identifying model/label and capacity.")
        for key in ("media_verified", "signature_verified", "recovery_ack", "usb_erasure_ack", "separate_usb_confirmed"):
            if value.get(key) is not True: raise ValueError("Complete every handoff safety confirmation.")
        systems, _ = catalog()
        record = next(item for item in systems if item["id"] == value["os_id"])
        result = {"status": "ready_for_manual_handoff", "installation_started": False,
                  "os_id": value["os_id"], "device_label": label.strip(), "method": value["method"],
                  "verification": "user_attestation", "automatic_rollback": False,
                  "instructions": prepare_installation(value["os_id"], record)["checklist"],
                  "message": "Preparation checklist recorded. ReviveOS has not written media, rebooted, or started an installation. Use the one-time boot menu yourself."}
        session["handoff"] = {key: result[key] for key in ("os_id", "status", "installation_started")}
        return respond(result)

    return blueprint


# Local AI.
def create_extensions_blueprint():
    blueprint = Blueprint("extensions", __name__)

    @blueprint.errorhandler(ValueError)
    @blueprint.errorhandler(OSError)
    def invalid(error):
        return respond(message=str(error), code=400)

    @blueprint.errorhandler(AIError)
    def unavailable(error):
        return respond(message=str(error), code=503)

    @blueprint.get("/api/ai/status")
    def ai_status():
        result = current_app.extensions["local_ai"].status()
        result["task_id"] = session.get("model_task")
        return respond(result)

    @blueprint.post("/api/ai/setup")
    def ai_setup():
        data = body({"model", "consent"})
        model = data.get("model")
        if not isinstance(model, str) or model not in MODELS or data.get("consent") is not True:
            raise ValueError("Choose a supported model and explicitly approve the model download.")
        engine = current_app.extensions["local_ai"]
        if not engine.status()["available"]:
            raise AIError("Start the portable AI edition or a local Ollama engine before downloading a model.")
        task = current_app.extensions["tasks"].submit(owner(), "model", lambda update: engine.pull(model, update))
        session["model_task"] = task
        return respond({"task_id": task}, "Local model download requested. No paid API is used.", 202)

    @blueprint.post("/api/ai/chat")
    def ai_chat():
        data = body({"question", "model"})
        question, model = data.get("question"), data.get("model", "gemma2:2b")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1500 or not isinstance(model, str) or model not in MODELS:
            raise ValueError("Enter a question up to 1,500 characters and choose a supported local model.")
        systems, apps = load_catalog(current_app.config["DATA_DIR"])
        hardware = detect_hardware()
        preferences = session.get("preferences", {})
        benchmarks = current_app.extensions["analysis"].latest(session.get("benchmark_token"), hardware)
        ranked = recommend_operating_systems(hardware, preferences, systems, benchmarks, apps)
        context = {"hardware": {key: hardware.get(key) for key in ("platform", "architecture", "cpu", "memory_gb", "storage_gb", "cpu_max_mhz", "tpm")},
                   "catalog_requirements": [{key: system.get(key) for key in ("id", "name", "version", "desktop", "architectures", "minimum", "recommended", "assumptions", "additional_requirements", "sources")} for system in systems if system["id"] in {row["os_id"] for row in ranked[:5]}],
                   "preferences": preferences, "applications": [{"id": app["id"], "name": app["name"]} for app in apps],
                   "current_checked_results": [{"name": row["name"], "id": row["os_id"], "status": row["status"],
                       "suitability": row["score"], "evidence": row["evidence"],
                       "known_failures": row["exclusion_reasons"][:3], "unverified": row["evidence_gaps"][:3]} for row in ranked[:5]],
                   "limits": "No speed prediction, installation or rollback. The database and rules, not the model, decide known checks."}
        return respond(current_app.extensions["local_ai"].chat(question.strip(), model, context, [app["id"] for app in apps]))

    return blueprint
