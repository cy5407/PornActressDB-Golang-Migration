import json
import subprocess
from pathlib import Path

from src.models.json_database import JSONDBManager
from src.services import go_cli


ROOT_DIR = Path(__file__).resolve().parents[2]
CLASSIFIER_EXE = ROOT_DIR / "classifier.exe"


def test_go_cli_is_available():
    assert go_cli.is_available() is True


def test_db_stats_smoke_returns_json(tmp_path):
    db_dir = tmp_path / "json_db"
    JSONDBManager(str(db_dir))

    result = subprocess.run(
        [
            str(CLASSIFIER_EXE),
            "db",
            "stats",
            "-data-dir",
            str(db_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["total_videos"] == 0
