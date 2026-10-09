"""Run the same gates as CI: lint, tests, frontend build. Usage: python scripts/check.py [--fast]"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A -m on the command line replaces the one in pytest.ini, so --fast has to repeat its exclusions.
FAST_MARKERS = "not slow and not realdata and not perf"


def run(name: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd, cwd=cwd, shell=sys.platform == "win32").returncode == 0
    print(f"--- {name}: {'ok' if ok else 'FAILED'}")
    return ok


def main() -> int:
    fast = "--fast" in sys.argv
    steps = [("lint", [sys.executable, "-m", "ruff", "check", "."]),
             ("tests", [sys.executable, "-m", "pytest", "-q", "-x"] + (["-m", FAST_MARKERS] if fast else []))]
    if not fast:
        steps.append(("frontend build", ["npm", "run", "build"], ROOT / "frontend"))
    results = [run(*s) for s in steps]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
