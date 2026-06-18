from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(script_name: str, backend_root: Path) -> dict:
    cmd = [sys.executable, str(backend_root / "scripts" / script_name)]
    proc = subprocess.run(cmd, cwd=str(backend_root), capture_output=True, text=True)
    return {
        "script": script_name,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    results = [
        _run("smoke_all_features.py", backend_root),
        _run("smoke_api_endpoints.py", backend_root),
        _run("smoke_alignment.py", backend_root),
    ]
    ok = all(item["returncode"] == 0 for item in results)
    output = {"ok": ok, "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
