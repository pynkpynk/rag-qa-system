import subprocess
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
DOTENV = SCRIPT_DIR / "_dotenv.sh"


@pytest.mark.parametrize(
    "lines",
    [
        [
            "EMPTY=",
            "SINGLE_QUOTE='",
            'DOUBLE_QUOTE="',
            "TWO_SINGLE='''",
            'TWO_DOUBLE="""',
            "QUOTED_SINGLE='x'",
            'QUOTED_DOUBLE="x"',
            "MISMATCH='x",
            "PRESERVE=from_file",
        ]
    ],
)
def test_dotenv_load_handles_quotes(tmp_path: Path, lines: list[str]) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines))

    script = f"""
set -euo pipefail
source "{DOTENV}"
export PRESET=keep
dotenv_load_preserve_existing "$1"
printf 'EMPTY=%s\\n' "${{EMPTY-__unset__}}"
printf 'SINGLE_QUOTE=%s\\n' "${{SINGLE_QUOTE-__unset__}}"
printf 'DOUBLE_QUOTE=%s\\n' "${{DOUBLE_QUOTE-__unset__}}"
printf 'TWO_SINGLE=%s\\n' "${{TWO_SINGLE-__unset__}}"
printf 'TWO_DOUBLE=%s\\n' "${{TWO_DOUBLE-__unset__}}"
printf 'QUOTED_SINGLE=%s\\n' "${{QUOTED_SINGLE-__unset__}}"
printf 'QUOTED_DOUBLE=%s\\n' "${{QUOTED_DOUBLE-__unset__}}"
printf 'MISMATCH=%s\\n' "${{MISMATCH-__unset__}}"
printf 'PRESET=%s\\n' "${{PRESET-__unset__}}"
printf 'PRESERVE=%s\\n' "${{PRESERVE-__unset__}}"
"""
    result = subprocess.run(
        ["bash", "-c", script, "bash", str(env_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    expected = {
        "EMPTY": "",
        "SINGLE_QUOTE": "'",
        "DOUBLE_QUOTE": '"',
        "TWO_SINGLE": "",
        "TWO_DOUBLE": "",
        "QUOTED_SINGLE": "x",
        "QUOTED_DOUBLE": "x",
        "MISMATCH": "'x",
        "PRESET": "keep",
        "PRESERVE": "from_file",
    }
    actual = dict(
        line.split("=", 1) for line in result.stdout.strip().splitlines() if line
    )
    assert actual == expected
