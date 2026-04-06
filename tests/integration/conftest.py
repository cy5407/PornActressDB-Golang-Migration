import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def go_exe():
    """確認 classifier.exe 可用，否則 skip 整個 session。"""
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "classifier.exe",
        repo_root / "classifier",
        Path(os.getcwd()) / "classifier.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    pytest.skip(
        "classifier.exe 不存在，跳過 e2e 整合測試（需先執行 go build -o classifier.exe ./cmd/scanner）"
    )


@pytest.fixture
def temp_data_dir(tmp_path):
    """建立帶有最小初始資料的暫存資料目錄。"""
    data_dir = tmp_path / "json_db"
    data_dir.mkdir()
    (data_dir / "data.json").write_text(
        '{"videos": {}, "actresses": {}, "links": []}',
        encoding="utf-8",
    )
    return str(data_dir)


@pytest.fixture
def runner(go_exe):
    """回傳已初始化的 GoCommandRunner。"""
    from src.services.go_runner import GoCommandRunner

    return GoCommandRunner(go_exe)
