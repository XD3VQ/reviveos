"""ReviveOS loopback web application. HTTP adapters stay separate from domain logic."""
import secrets
from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from config import Config
from backend.hardware import detect_hardware
from backend.catalog import CatalogError, load_catalog
from backend.compatibility import check_application_compatibility
from backend.recommender import recommend_operating_systems
from backend.analysis import AnalysisService, BenchmarkBusy
from backend.tasks import TaskService
from backend.routes import create_workflow_blueprint
from backend.local_ai import LocalAI
from backend.routes import create_extensions_blueprint
import os

DEFAULT_PREFERENCES = {"applications": [], "usage": "everyday", "experience": "beginner", "os_preference": "linux", "essential_notes": ""}


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(SECRET_KEY=secrets.token_hex(32), SESSION_COOKIE_SAMESITE="Strict",
                      SESSION_COOKIE_HTTPONLY=True, TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"])
    if test_config:
        app.config.update(test_config)
    analysis = AnalysisService(cooldown_seconds=app.config.get("BENCHMARK_COOLDOWN_SECONDS", 10))
    app.extensions["analysis"] = analysis
    app.extensions["tasks"] = TaskService()
    app.extensions["local_ai"] = LocalAI(os.environ.get("REVIVEOS_OLLAMA_URL", app.config["OLLAMA_URL"]))

    def respond(data=None, status="ok", message="", code=200):
        return jsonify(status=status, data=data, message=message), code

    def catalog():
        return load_catalog(app.config["DATA_DIR"])

    def empty_body():
        value = request.get_json(silent=True)
        return isinstance(value, dict) and not value

    @app.before_request
    def local_mutations_only():
        # JSON-only mutation requests plus same-origin checks prevent foreign
        # websites from triggering a workload on this local service.
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and origin != request.host_url.rstrip("/")):
                return respond(status="error", message="Cross-origin requests are not allowed.", code=403)

    @app.get("/")
    def index():
        _, applications = catalog()
        return render_template("index.html", applications=applications,
                               preferences=session.get("preferences", DEFAULT_PREFERENCES))

    @app.get("/api/health")
    def health():
        return respond({"service": "ReviveOS", "stage": "functional_core", "algorithm": "rules-v2"})

    @app.get("/api/hardware")
    def hardware():
        report = detect_hardware()
        return respond(report, report["status"], "Read-only detection of the host running the backend.")

    @app.get("/api/preferences")
    def current_preferences():
        return respond(session.get("preferences", DEFAULT_PREFERENCES))

    @app.post("/api/preferences")
    def preferences():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            return respond(status="error", message="A JSON object is required.", code=400)
        if set(value) - {"applications", "usage", "experience", "os_preference", "essential_notes"}:
            return respond(status="error", message="Unknown preference fields.", code=400)
        apps = value.get("applications", [])
        usage = value.get("usage", "everyday")
        experience = value.get("experience", "beginner")
        os_preference = value.get("os_preference", "linux")
        notes = value.get("essential_notes", "")
        _, applications = catalog()
        known = {entry["id"] for entry in applications}
        if (not isinstance(apps, list) or any(not isinstance(item, str) for item in apps)
                or any(item not in known for item in apps)
                or not isinstance(usage, str) or usage not in {"everyday", "study", "development", "media", "gaming", "office", "work", "other"}
                or not isinstance(experience, str) or experience not in {"beginner", "comfortable", "advanced"}
                or not isinstance(os_preference, str) or os_preference not in {"windows", "linux", "familiar"}
                or not isinstance(notes, str) or len(notes) > 1000):
            return respond(status="error", message="Invalid applications, usage, or experience.", code=400)
        clean = {"applications": list(dict.fromkeys(apps)), "usage": usage, "experience": experience, "os_preference": os_preference, "essential_notes": notes.strip()}
        session["preferences"] = clean
        for key in ("shortlist", "review_ack", "backup_confirmation", "handoff"):
            session.pop(key, None)
        return respond(clean, message="Preferences saved for this browser session only.")

    @app.post("/api/benchmarks")
    def benchmarks():
        if not empty_body():
            return respond(status="error", message="Send an empty JSON object to request the fixed safe benchmarks.", code=400)
        token, report = analysis.run(detect_hardware())
        session["benchmark_token"] = token
        return respond(report, report["status"], "Measured on this host. Results expire after ten minutes.")

    @app.post("/api/recommend")
    def recommend():
        if not empty_body():
            return respond(status="error", message="Send an empty JSON object; saved preferences and server measurements are used.", code=400)
        operating_systems, applications = catalog()
        hardware = detect_hardware()
        benchmarks = analysis.latest(session.get("benchmark_token"), hardware)
        preferences = session.get("preferences", DEFAULT_PREFERENCES)
        results = recommend_operating_systems(hardware, preferences, operating_systems, benchmarks, applications)
        return respond({"algorithm": "rules-v2", "recommendations": results, "hardware": hardware,
                        "preferences": preferences, "benchmarks": benchmarks,
                        "summary": {"meets_known_requirements": sum(row["status"] == "meets_known_requirements" for row in results),
                                    "needs_review": sum(row["status"] == "needs_review" for row in results),
                                    "incompatible": sum(row["status"] == "incompatible" for row in results)}},
                       message="Explainable policy scores, not predicted performance. Review warnings and live-test device support.")

    @app.post("/api/compatibility")
    def compatibility():
        value = request.get_json(silent=True)
        if not isinstance(value, dict) or set(value) - {"os_id", "applications"}:
            return respond(status="error", message="Expected os_id and optional applications.", code=400)
        systems, applications = catalog()
        os_id = value.get("os_id")
        app_ids = value.get("applications", session.get("preferences", DEFAULT_PREFERENCES)["applications"])
        if (not isinstance(os_id, str) or os_id not in {item["id"] for item in systems}
                or not isinstance(app_ids, list) or any(not isinstance(item, str) for item in app_ids)
                or any(item not in {row["id"] for row in applications} for item in app_ids)):
            return respond(status="error", message="Unknown OS or invalid application IDs.", code=400)
        return respond(check_application_compatibility(app_ids, os_id, detect_hardware(), applications))

    @app.get("/api/operating-systems")
    def operating_systems():
        systems, _ = catalog()
        return respond(systems, message="Sourced image-specific records. Null requirements are unverified, not zero.")

    @app.errorhandler(CatalogError)
    def catalog_error(error):
        app.logger.warning("Catalog unavailable: %s", error)
        return respond(status="error", message=str(error), code=503)

    @app.errorhandler(BenchmarkBusy)
    def benchmark_busy(error):
        return respond(status="error", message=str(error), code=409)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return respond(status="error", message=error.description, code=error.code)

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unexpected request failure")
        return respond(status="error", message="An internal error occurred. Check the local server log.", code=500)

    app.register_blueprint(create_workflow_blueprint(catalog))
    app.register_blueprint(create_extensions_blueprint())
    return app


if __name__ == "__main__":
    from launch import main
    main()
