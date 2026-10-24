"""Guest-local startup checks, logged to the VM console. No file operations."""
import json
import configparser
from pathlib import Path
import time
from urllib.request import urlopen
from urllib.error import HTTPError


def main():
    report = {"status": "failed"}
    for _ in range(180):
        try:
            with urlopen("http://127.0.0.1:5000/", timeout=2) as response:
                assert response.status == 200
            def get(path):
                with urlopen("http://127.0.0.1:5000" + path, timeout=3) as response:
                    return json.load(response)["data"]
            report["catalog_count"] = len(get("/api/operating-systems"))
            with urlopen("http://127.0.0.1:5000/static/app.js", timeout=3) as response:
                script = response.read().decode()
            assert 'matching.slice(0, 3)' in script
            assert 'Rough planning estimates' in script
            report["top_three_interface_and_estimates"] = True
            assert Path("/opt/reviveos/launch.py").is_file()
            assert 'from launch import serve_web' in Path('/opt/reviveos/live_session.py').read_text()
            report["unified_browser_launcher"] = True
            desktop = configparser.ConfigParser()
            desktop.read('/etc/xdg/pcmanfm/default/pcmanfm.conf')
            assert all(desktop.get('volume', key) == '0' for key in ('mount_on_startup', 'mount_removable', 'autorun'))
            report['automatic_mounting_disabled'] = True
            assert not Path("/opt/reviveos/backend/database.py").exists()
            assert not Path("/opt/reviveos/data/requirements-template.xlsx").exists()
            try:
                urlopen("http://127.0.0.1:5000/api/database/template", timeout=2)
                raise AssertionError("Spreadsheet import endpoint still exists")
            except HTTPError as error:
                assert error.code == 404
            report["spreadsheet_imports_removed"] = True
            report["hardware"] = get("/api/hardware")
            session = json.loads(Path("/home/revive/.local/share/reviveos/session.json").read_text())
            assert session["uid"] != 0
            assert Path(f"/proc/{session['browser_pid']}").exists()
            report["session"] = session
            report["ai"] = get("/api/ai/status")
            if session["ai_bundled"]:
                assert report["ai"]["available"], "Bundled AI engine has not started"
            report["status"] = "passed"
            report.pop("error", None)
            break
        except Exception as error:
            report["error"] = str(error)
            time.sleep(1)
    Path("/tmp/reviveos-boot-check.json").write_text(json.dumps(report, indent=2))
    print("REVIVEOS_BOOT_CHECK " + json.dumps(report), flush=True)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
