from pathlib import Path

import pytest

from src.models.json_database import JSONDBManager
from src.models.json_types import VideoDict


@pytest.fixture
def temp_db_dir(tmp_path: Path) -> str:
    return str(tmp_path / "json_db")


@pytest.fixture
def db_manager(temp_db_dir: str) -> JSONDBManager:
    return JSONDBManager(temp_db_dir)


@pytest.fixture
def sample_video() -> VideoDict:
    return {
        "code": "TEST-001",
        "title": "測試影片",
        "studio": "測試片商",
        "release_date": "2024-01-01",
        "url": "",
        "actresses": [],
        "search_status": "success",
        "last_search_date": "2024-01-01",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "metadata": {"source": "test", "confidence": 1.0},
    }


@pytest.fixture
def seeded_db_manager(db_manager: JSONDBManager, sample_video: VideoDict) -> JSONDBManager:
    db_manager.add_or_update_video(sample_video)
    return db_manager
