"""Start the local web UI: build the frontend if needed, serve on 127.0.0.1, open the browser.

    python serve.py              # build if needed, serve, open the browser
    python serve.py --dev        # API only, for `npm run dev` on http://127.0.0.1:5173
    python serve.py --rebuild    # force a fresh frontend build
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from config import CODE_ROOT, WEB_DIST

WEB_DIR = CODE_ROOT / "web"
DEFAULT_PORT = 8765
DEV_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def newest_mtime(paths):
    newest = 0.0
    for root in paths:
        root = Path(root)
        if root.is_file():
            newest = max(newest, root.stat().st_mtime)
            continue
        for file in root.rglob("*"):
            if file.is_file():
                newest = max(newest, file.stat().st_mtime)
    return newest


def needs_build():
    index = WEB_DIST / "index.html"
    if not index.exists():
        return True
    sources = [WEB_DIR / "src", WEB_DIR / "index.html", WEB_DIR / "package.json", WEB_DIR / "tailwind.config.ts"]
    return newest_mtime(sources) > index.stat().st_mtime


def build_frontend(force=False):
    if not force and not needs_build():
        return True
    npm = shutil.which("npm")
    if not npm:
        if (WEB_DIST / "index.html").exists():
            print("⚠️ npm was not found, so the existing web build is used.")
            return True
        print("❌ npm (Node.js 18+) is needed to build the web UI the first time. Install it from nodejs.org.")
        return False
    if not (WEB_DIR / "node_modules").exists():
        print("📦 Installing web dependencies (first run only)...")
        subprocess.run([npm, "ci" if (WEB_DIR / "package-lock.json").exists() else "install", "--no-audit", "--no-fund"],
                       cwd=WEB_DIR, check=True)
    print("🛠️ Building the web UI...")
    subprocess.run([npm, "run", "build"], cwd=WEB_DIR, check=True)
    return True


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def pick_port(preferred):
    for port in range(preferred, preferred + 20):
        if port_is_free(port):
            return port
    raise SystemExit(f"❌ No free port between {preferred} and {preferred + 19}.")


def main(argv=None):
    # Emoji in log lines must not crash when output is redirected to a cp1252 file on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AI Job Agent web UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AI_JOB_AGENT_PORT", DEFAULT_PORT)))
    parser.add_argument("--dev", action="store_true", help="API only; use with `npm run dev` in web/")
    parser.add_argument("--rebuild", action="store_true", help="Force a fresh frontend build")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    args = parser.parse_args(argv)

    import uvicorn

    if not args.dev and not build_frontend(force=args.rebuild):
        return 1

    port = args.port if args.dev else pick_port(args.port)
    os.environ["AI_JOB_AGENT_PORT"] = str(port)
    if args.dev:
        os.environ["AI_JOB_AGENT_UI_ORIGIN"] = DEV_ORIGINS[0]

    from api.app import create_app

    app = create_app(dev_origins=DEV_ORIGINS if args.dev else ())
    url = DEV_ORIGINS[0] if args.dev else f"http://127.0.0.1:{port}"
    print(f"🌐 AI Job Agent UI: {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
