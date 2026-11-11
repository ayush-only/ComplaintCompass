"""One command for the demo: (re)build results from cached model answers, start the app, check health.

    python demo.py               use the existing compass.db, start the dashboard and open it
    python demo.py --rescore     re-run stages 4-7 first (naming, dedupe, severity, score); quick
    python demo.py --rebuild     re-run the whole pipeline first (embeddings + clustering take a few minutes)
    python demo.py --live        allow live model calls for prompts not in .llm_cache (default: offline)
    python demo.py --check       start, verify /api/health, then stop (use before going on stage)

Options: --port 8000, --no-browser. Stop the server with Ctrl+C.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "compass.db"
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never send localhost through a proxy


def get_health(base_url: str, timeout: float = 2.0):
    """Return the /api/health JSON, or None if the server is not answering yet."""
    try:
        with _direct.open(base_url.rstrip("/") + "/api/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 - connection refused, 503 while starting, etc.
        return None


def wait_for_health(base_url: str, seconds: float = 40.0, proc=None):
    end = time.time() + seconds
    while time.time() < end:
        h = get_health(base_url)
        if h:
            return h
        if proc is not None and proc.poll() is not None:
            return None
        time.sleep(0.5)
    return None


def describe(h: dict) -> list[str]:
    lines = [f"OK: {h['complaints']:,} complaints, {h['issues']} issues, data as of {h.get('as_of', '?')[:10]}"]
    if not h.get("model_output", True):
        names, sev = h.get("issue_names", {}), h.get("severity", {})
        if not names.get("llm"):
            lines.append("Note: issue names are keyword placeholders (the model naming step has not run).")
        if not sev.get("llm"):
            lines.append("Note: severity uses the keyword rule (the model severity step has not run).")
        lines.append("      Add a key to .env, then run: python demo.py --rescore --live")
    return lines


def check_imports() -> bool:
    missing = [m for m in ("fastapi", "uvicorn", "pydantic") if __import__("importlib").util.find_spec(m) is None]
    if missing:
        print(f"Missing packages: {', '.join(missing)}. Run: pip install -r requirements.txt")
        return False
    return True


def build(stages: str, live: bool) -> None:
    sys.path.insert(0, str(ROOT))
    if not (ROOT / "data" / "complaints.csv").exists():
        print("== generating synthetic data")
        subprocess.run([sys.executable, str(ROOT / "data" / "generate.py")], check=True, cwd=ROOT)
    from pipeline.run_all import run
    run(start=stages, offline=not live)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the Complaint Compass demo")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--rebuild", action="store_true", help="re-run the whole pipeline first")
    g.add_argument("--rescore", action="store_true", help="re-run stages 4-7 first")
    ap.add_argument("--live", action="store_true", help="allow live model calls for uncached prompts")
    ap.add_argument("--check", action="store_true", help="start, verify health, stop")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    url = f"http://127.0.0.1:{a.port}/"
    os.chdir(ROOT)

    if not check_imports():
        return 1
    if a.rebuild or not DB.exists():
        print("== running the full pipeline" + ("" if a.live else " from cached model answers"))
        build("01", a.live)
    elif a.rescore:
        print("== re-scoring (stages 4-7)" + ("" if a.live else " from cached model answers"))
        build("04", a.live)

    already = get_health(url)
    if already:
        print(f"A server is already running at {url}")
        print("\n".join(describe(already)))
        if not a.no_browser and not a.check:
            webbrowser.open(url)
        return 0

    cmd = os.environ.get("DEMO_SERVER_CMD")  # tests swap in a stand-in server
    cmd = cmd.split() if cmd else [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(a.port)]
    print(f"== starting the API and dashboard on {url}")
    proc = subprocess.Popen(cmd, cwd=ROOT)
    try:
        h = wait_for_health(url, proc=proc)
        if not h:
            print("The server did not report healthy. Check the log above; is compass.db complete?")
            return 1
        print("\n".join(describe(h)))
        if a.check:
            return 0
        print(f"\nDashboard: {url}   (Ctrl+C to stop)")
        if not a.no_browser:
            webbrowser.open(url)
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
