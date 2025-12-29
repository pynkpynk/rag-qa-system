import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPTS = [
    Path(__file__).resolve().parents[1] / "scripts/_dotenv.sh",
    Path(__file__).resolve().parents[1] / "scripts/dev_up.sh",
    Path(__file__).resolve().parents[1] / "scripts/dev_down.sh",
    Path(__file__).resolve().parents[1] / "scripts/dev_status.sh",
]


@pytest.mark.parametrize("script_path", SCRIPTS)
def test_dev_scripts_have_valid_syntax(script_path: Path) -> None:
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash not available on PATH")
    result = subprocess.run(
        [bash, "-n", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{script_path} failed syntax check: {result.stderr.strip()}"
