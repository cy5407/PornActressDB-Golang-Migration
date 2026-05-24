from pathlib import Path

import pytest

from src.models.incremental_json_database import IncrementalJSONDB
from src.models.json_database import JSONDBManager

MODULES_WITHOUT_IMPORT_STUBS = [
    Path("src/models/json_database.py"),
    Path("src/models/incremental_json_database.py"),
    Path("src/scrapers/cache_manager.py"),
]


def _raise_runtime_error(*_args, **_kwargs):
    raise RuntimeError("boom")


def test_go_only_modules_do_not_use_importerror_stubs():
    for relative_path in MODULES_WITHOUT_IMPORT_STUBS:
        source = relative_path.read_text(encoding="utf-8")
        assert "except ImportError" not in source


def test_json_database_get_all_videos_raises_when_go_cli_fails(db_manager, monkeypatch):
    db_manager.data["videos"]["MEM-001"] = {
        "code": "MEM-001",
        "title": "memory only",
        "studio": "Test",
    }
    monkeypatch.setattr(
        "src.models.json_database._go_db_get_all_videos",
        _raise_runtime_error,
    )

    with pytest.raises(RuntimeError, match="Go get_all_videos 失敗"):
        db_manager.get_all_videos()


def test_incremental_json_database_get_video_info_raises_when_go_cli_fails(
    temp_db_dir, monkeypatch
):
    db = IncrementalJSONDB(str(temp_db_dir))
    monkeypatch.setattr(
        "src.models.incremental_json_database._go_db_get_video",
        _raise_runtime_error,
    )
    monkeypatch.setattr(
        db.base_db,
        "get_video_info",
        lambda _code: {"code": "MEM-001", "title": "memory fallback"},
    )

    with pytest.raises(RuntimeError, match="Go get_video_info 失敗"):
        db.get_video_info("MEM-001")

