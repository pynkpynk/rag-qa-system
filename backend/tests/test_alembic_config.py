from __future__ import annotations

import configparser
from pathlib import Path


def test_alembic_script_location_resolves() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    ini_path = repo_root / "backend" / "alembic.ini"
    assert ini_path.exists()

    parser = configparser.ConfigParser()
    parser["DEFAULT"]["here"] = str(ini_path.parent)
    read_files = parser.read(ini_path)
    assert read_files, "alembic.ini could not be read"

    script_location_raw = parser.get("alembic", "script_location", fallback="").strip()
    assert script_location_raw, "script_location missing in alembic.ini"

    script_location = script_location_raw.replace("%(here)s", str(ini_path.parent))
    assert script_location, "script_location missing in alembic.ini"

    script_path = Path(script_location)
    if not script_path.is_absolute():
        script_path = (repo_root / script_path).resolve()
    script_dir = script_path
    assert script_dir.exists(), f"script_location path not found: {script_dir}"
    versions_dir = script_dir / "versions"
    assert versions_dir.exists(), f"versions dir not found under {script_dir}"
