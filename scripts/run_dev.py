"""Launch the local AeroCast-NCR stack in one command.

Starts the FastAPI backend (uvicorn) from the repository root; optionally
starts the Vite dev server too. Both subprocesses are terminated cleanly on
Ctrl+C.

Usage:
    python -m scripts.run_dev [--port 8000] [--frontend]
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wait_for_backend(url: str, timeout_s: float = 45.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend", action="store_true", help="also start the Vite dev server")
    args = parser.parse_args()

    procs = []
    backend_env = dict(os.environ)
    backend_env.setdefault("PYTHONPATH", ROOT)

    backend_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port)]
    procs.append(subprocess.Popen(backend_cmd, cwd=os.path.join(ROOT, "backend"), env=backend_env))

    if args.frontend:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        procs.append(
            subprocess.Popen([npm, "run", "dev"], cwd=os.path.join(ROOT, "frontend"))
        )

    health = f"http://localhost:{args.port}/health"
    if wait_for_backend(health):
        print(f"Backend ready at http://localhost:{args.port} (docs at /docs)")
    else:
        print("Backend did not become ready in time; see server.log", file=sys.stderr)

    if args.frontend:
        print("Frontend dev server at http://localhost:5173")

    print("Press Ctrl+C to stop the stack.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait(timeout=10)
    return 0


if __name__ == "__main__":
    main()