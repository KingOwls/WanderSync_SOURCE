import os
from pathlib import Path
import subprocess
import sys


def test_gateway_helper_modules_import_with_backend_as_container_root():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "backend"
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import gateway.flight_connections; import gateway.route_coverage; print('GATEWAY HELPERS IMPORT OK')",
        ],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "GATEWAY HELPERS IMPORT OK" in proc.stdout
