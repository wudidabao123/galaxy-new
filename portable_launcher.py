"""Portable launcher for Galaxy New.

Commands:
  python portable_launcher.py setup
  python portable_launcher.py start
  python portable_launcher.py public
  python portable_launcher.py stop
  python portable_launcher.py status
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("GALAXY_PORT", "8502"))
LOCAL_URL = f"http://localhost:{PORT}"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GALAXY_PORTABLE", "1")
    env.setdefault("GALAXY_DATA_DIR", str(ROOT / "workspace"))
    env.setdefault("PYTHONUTF8", "1")
    return env


def _python() -> str:
    embedded = ROOT / "runtime" / "python" / "python.exe"
    if embedded.exists():
        return str(embedded)
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


def _cloudflared() -> Path | None:
    packaged = ROOT / "tools" / "cloudflared.exe"
    if packaged.exists():
        return packaged
    desktop = Path(r"C:\Users\26043\Desktop\cloudflared-windows-amd64.exe")
    if desktop.exists():
        return desktop
    return None


def find_pid_on_port(port: int) -> list[str]:
    pids: list[str] = []
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in proc.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pids.append(parts[-1])
    except Exception:
        pass
    return list(dict.fromkeys(pids))


def _kill_pid(pid: str) -> None:
    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)


def stop() -> None:
    print(f"Stopping Galaxy New on port {PORT}...")
    for pid in find_pid_on_port(PORT):
        print(f"  killing PID {pid}")
        _kill_pid(pid)
    subprocess.run(["taskkill", "/IM", "cloudflared.exe", "/F"], capture_output=True, text=True)
    subprocess.run(
        ["taskkill", "/IM", "cloudflared-windows-amd64.exe", "/F"],
        capture_output=True,
        text=True,
    )
    print("Stopped.")


def status() -> None:
    pids = find_pid_on_port(PORT)
    print(f"Python      : {_python()}")
    print(f"App folder  : {ROOT}")
    print(f"Local URL   : {LOCAL_URL}")
    print(f"Port status : {'busy, PID(s) ' + ', '.join(pids) if pids else 'free'}")
    cf = _cloudflared()
    print(f"cloudflared : {cf if cf else 'not found'}")


def init_runtime() -> None:
    code = "from config import ensure_runtime_dirs; from data.database import init_db; ensure_runtime_dirs(); init_db()"
    subprocess.run([_python(), "-c", code], cwd=str(ROOT), env=_env(), check=True)


def start(foreground: bool = True) -> subprocess.Popen | None:
    init_runtime()
    pids = find_pid_on_port(PORT)
    if pids:
        print(f"Galaxy New is already running: {LOCAL_URL} (PID {', '.join(pids)})")
        webbrowser.open(LOCAL_URL)
        return None

    cmd = [
        _python(),
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(PORT),
        "--server.address",
        "0.0.0.0",
        "--server.headless",
        "true",
    ]
    print(f"Starting Galaxy New: {LOCAL_URL}")
    webbrowser.open(LOCAL_URL)
    if foreground:
        subprocess.run(cmd, cwd=str(ROOT), env=_env())
        return None
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    return subprocess.Popen(cmd, cwd=str(ROOT), env=_env(), creationflags=creationflags)


def public() -> None:
    start(foreground=False)
    time.sleep(5)
    cf = _cloudflared()
    if not cf:
        print("cloudflared was not found.")
        print(r"Expected packaged tools\cloudflared.exe or C:\Users\26043\Desktop\cloudflared-windows-amd64.exe")
        return
    print()
    print("Starting Cloudflare quick tunnel...")
    print("Look for the https://*.trycloudflare.com URL below.")
    print()
    subprocess.run([str(cf), "tunnel", "--url", LOCAL_URL], cwd=str(ROOT), env=_env())


def setup() -> None:
    subprocess.run([_python(), "portable_setup.py"], cwd=str(ROOT), env=_env())


def menu() -> None:
    while True:
        print()
        print("Galaxy New Portable")
        print("=" * 24)
        print("1. Setup / configure")
        print("2. Start local")
        print("3. Start with public tunnel")
        print("4. Stop")
        print("5. Status")
        print("0. Exit")
        choice = input("> ").strip()
        if choice == "1":
            setup()
        elif choice == "2":
            start(foreground=True)
        elif choice == "3":
            public()
        elif choice == "4":
            stop()
        elif choice == "5":
            status()
        elif choice == "0":
            return


def main() -> None:
    os.chdir(ROOT)
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "menu"
    if command in {"setup", "configure"}:
        setup()
    elif command in {"start", "local"}:
        start(foreground=True)
    elif command in {"public", "tunnel"}:
        public()
    elif command == "stop":
        stop()
    elif command == "status":
        status()
    else:
        menu()


if __name__ == "__main__":
    main()
