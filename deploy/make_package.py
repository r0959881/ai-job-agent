"""Build the web app and zip what the server needs, for uploading in cPanel's File Manager.

    python deploy/make_package.py            -> deploy/build/ai-job-agent-<date>.zip

Only the files below are packed. Personal data (resume_data.yaml, .env, jobs.db,
Google tokens, CV PDFs, output/) and development files never leave your computer.
"""
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FILES = [
    "passenger_wsgi.py", "manage.py", "requirements.txt", ".env.example",
    "agent_settings.py", "agent_log.py", "config.py", "database.py", "discovery.py", "generate_cover_letter.py",
    "generate_doc.py", "languages.py", "regions.py", "report.py", "tailor.py", "user_scope.py",
]
FOLDERS = ["api", "job_sources", "web/dist", "fonts"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def main():
    for stream in (sys.stdout, sys.stderr):  # emoji must not crash a cp1252 Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    from serve import build_frontend

    if not build_frontend(force=True):
        print("❌ The web app could not be built. Install Node.js 18+ and run `npm ci` in web/ first.")
        return 1
    out_dir = ROOT / "deploy" / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"ai-job-agent-{datetime.now():%Y%m%d-%H%M}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
            count += 1
        for folder in FOLDERS:
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and not SKIP_PARTS & set(path.parts) and path.suffix != ".pyc":
                    archive.write(path, path.relative_to(ROOT).as_posix())
                    count += 1
        # Passenger restarts the app when tmp/restart.txt changes.
        archive.writestr("tmp/restart.txt", datetime.now().isoformat())
    size = target.stat().st_size / 1024 / 1024
    print(f"📦 {target.relative_to(ROOT)}  ({count} files, {size:.1f} MB)")
    print("Upload it to the app folder in cPanel's File Manager and extract it there (see DEPLOYMENT.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
