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


def test_go_cli_extract_code_uses_real_classifier():
    assert go_cli.extract_code("SONE-123 sample.mp4") == "SONE-123"
    assert go_cli.extract_code("FC2-PPV-1234567.mp4") is None


def test_go_cli_identify_studio_uses_real_classifier():
    assert go_cli.identify_studio("SONE-123") == "S1"
    assert go_cli.identify_studio("IPX-001") == "PREMIUM"
    assert go_cli.identify_studio("UNKNOWN-001") is None


def test_go_cli_normalize_studio_name_uses_real_classifier():
    assert go_cli.normalize_studio_name("MOODYZ DIVA") == "MOODYZ"
    assert go_cli.normalize_studio_name("Unknown Studio", video_code="SSIS-123") == "S1"


def test_go_cli_cache_round_trip_uses_real_classifier(tmp_path):
    cache_dir = tmp_path / "cache"
    payload = "真實 cache round-trip".encode("utf-8")

    assert go_cli.cache_set("demo-key", payload, ttl_hours=1, cache_dir=str(cache_dir)) is True
    assert go_cli.cache_get("demo-key", cache_dir=str(cache_dir)) == payload
    assert go_cli.cache_delete("demo-key", cache_dir=str(cache_dir)) is True
    assert go_cli.cache_get("demo-key", cache_dir=str(cache_dir)) is None


def test_go_cli_cache_stats_uses_real_classifier(tmp_path):
    cache_dir = tmp_path / "cache"
    payload = b"stats"

    assert go_cli.cache_set("stats-key", payload, ttl_hours=1, cache_dir=str(cache_dir)) is True
    stats = go_cli.cache_get_stats(cache_dir=str(cache_dir))

    assert isinstance(stats, dict)
    assert stats.get("total_files", 0) >= 1
