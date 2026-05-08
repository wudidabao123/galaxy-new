"""
Galaxy New — 一键启动/停止/重启
用法:
  python launcher.py           交互菜单
  python launcher.py start     直接启动
  python launcher.py stop      停止端口
  python launcher.py restart   重启
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


PORT = 8502
ROOT = os.path.dirname(os.path.abspath(__file__))

# Auto-detect venv: first check .env, then common locations
def _find_venv() -> str:
    venv = os.environ.get("GALAXY_VENV", "")
    if venv and os.path.exists(os.path.join(venv, "Scripts", "python.exe")):
        return venv
    # Check sibling AutoGen/.venv
    candidate = os.path.normpath(os.path.join(ROOT, "..", "AutoGen", ".venv"))
    if os.path.exists(os.path.join(candidate, "Scripts", "python.exe")):
        return candidate
    # Fall back to current Python's venv
    return sys.prefix

VENV = _find_venv()
PYTHON = os.path.join(VENV, "Scripts", "python.exe") if os.path.exists(os.path.join(VENV, "Scripts", "python.exe")) else sys.executable


def find_pid_on_port(port: int) -> list[str]:
    """Return list of PIDs listening on the given port."""
    pids: list[str] = []
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pids.append(parts[-1])
    except Exception:
        pass
    return list(dict.fromkeys(pids))


def kill_pids(pids: list[str]) -> int:
    killed = 0
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", pid, "/F"],
                           capture_output=True, timeout=10)
            killed += 1
            print(f"  ✓ Killed PID {pid}")
        except Exception as e:
            print(f"  ✗ Failed to kill PID {pid}: {e}")
    return killed


def stop() -> bool:
    """Kill all processes on PORT. Returns True if anything was killed."""
    print("\n🔌 Stopping Galaxy New...")
    pids = find_pid_on_port(PORT)
    if not pids:
        print("  No process on port {}.".format(PORT))
        return False
    return kill_pids(pids) > 0


def start() -> None:
    """Launch Galaxy New in a new console window."""
    print("\n🚀 Starting Galaxy New on port {}...".format(PORT))
    print("  Python: {}".format(PYTHON))
    print("  Root:   {}".format(ROOT))

    # Ensure runtime dirs + DB
    subprocess.run(
        [PYTHON, "-c",
         "from config import ensure_runtime_dirs; ensure_runtime_dirs()"],
        cwd=ROOT, timeout=15,
    )
    subprocess.run(
        [PYTHON, "-c",
         "from data.database import init_db; init_db()"],
        cwd=ROOT, timeout=15,
    )

    # Open browser
    subprocess.Popen(
        ["cmd", "/c", "start", "http://localhost:{}".format(PORT)],
    )

    print("  Press Ctrl+C to stop.\n")
    try:
        subprocess.run(
            [PYTHON, "-m", "streamlit", "run", "app.py",
             "--server.port", str(PORT),
             "--server.address", "0.0.0.0"],
            cwd=ROOT,
        )
    except KeyboardInterrupt:
        print("\n\n👋 Stopped.")


def restart() -> None:
    stop()
    time.sleep(2)
    start()


def menu() -> None:
    print("""
╔══════════════════════════════════════════╗
║        🌌 Galaxy New 启动器               ║
╠══════════════════════════════════════════╣
║  [1]  启动 (start)                       ║
║  [2]  停止 (stop)                        ║
║  [3]  重启 (restart)                     ║
║  [4]  检查端口                           ║
║  [0]  退出                               ║
╚══════════════════════════════════════════╝
    """.strip())

    choice = input(">>> ").strip()
    if choice == "1":
        start()
    elif choice == "2":
        stop()
    elif choice == "3":
        restart()
    elif choice == "4":
        pids = find_pid_on_port(PORT)
        if pids:
            print(f"\n  Port {PORT}: PID(s) {', '.join(pids)}")
        else:
            print(f"\n  Port {PORT}: free")
        input("\n  Press Enter...")
        menu()
    elif choice == "0":
        print("👋")
    else:
        print("Unknown choice.")
        menu()


if __name__ == "__main__":
    os.chdir(ROOT)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    else:
        menu()
