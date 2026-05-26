"""
補充 incremental_json_database.py 覆蓋率測試

目標行：126, 128-132, 149-150, 174, 177-180, 198-202, 219-223,
        240, 246, 270-287, 293, 303-320, 335, 352-356, 365-369
"""
import json
import os
from datetime import UTC, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson
import pytest

from src.models.incremental_json_database import (
    JOURNAL_AGE_THRESHOLD,
    JOURNAL_SIZE_THRESHOLD,
    IncrementalJSONDB,
)
from src.models.json_database import JSONDBManager
from src.models.json_types import JSONDatabaseError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> IncrementalJSONDB:
    """建立並回傳初始化完成的 IncrementalJSONDB（含空資料庫）"""
    db_dir = str(tmp_path / "json_db")
    os.makedirs(db_dir, exist_ok=True)
    # 先用 JSONDBManager 建立合法的 data.json
    JSONDBManager(db_dir)
    return IncrementalJSONDB(db_dir)


# ---------------------------------------------------------------------------
# _init_journal：各種邊界情況
# ---------------------------------------------------------------------------

class TestInitJournal:
    def test_empty_created_at_in_index_uses_now(self, tmp_path):
        """index 中 created_at 為空時，應使用 datetime.now(UTC) (line 126)"""
        db_dir = str(tmp_path / "json_db")
        os.makedirs(db_dir, exist_ok=True)
        JSONDBManager(db_dir)  # 建立 data.json

        # 手動建立 journal + index（created_at 留空）
        journal_file = Path(db_dir) / "data.journal"
        index_file = Path(db_dir) / "data.index"
        journal_file.touch()
        index_data = {"videos": [], "actresses": [], "links": [], "journal_size": 5}
        index_file.write_bytes(orjson.dumps(index_data))

        db = IncrementalJSONDB(db_dir)
        assert db.journal_created_at is not None
        assert db.journal_size == 5

    def test_corrupt_index_resets_state(self, tmp_path):
        """index 檔案損壞時，應靜默重設狀態（lines 128-132）"""
        db_dir = str(tmp_path / "json_db")
        os.makedirs(db_dir, exist_ok=True)
        JSONDBManager(db_dir)

        journal_file = Path(db_dir) / "data.journal"
        index_file = Path(db_dir) / "data.index"
        journal_file.touch()
        index_file.write_bytes(b"NOT VALID JSON!!!")

        db = IncrementalJSONDB(db_dir)
        # 損壞的 index 應被靜默忽略，journal_size 重設為 0
        assert db.journal_size == 0


# ---------------------------------------------------------------------------
# _save_index：exception 路徑（lines 149-150）
# ---------------------------------------------------------------------------

class TestSaveIndex:
    def test_save_index_exception_is_silenced(self, tmp_path):
        """_save_index 拋例外時應靜默記錄（lines 149-150）"""
        db = _make_db(tmp_path)
        with patch("builtins.open", side_effect=OSError("disk full")):
            # 不應拋出例外
            db._save_index()


# ---------------------------------------------------------------------------
# update_video：錯誤路徑
# ---------------------------------------------------------------------------

class TestUpdateVideoErrors:
    def test_go_returns_false_raises_runtime_error(self, tmp_path):
        """Go 回傳 False 時應拋出 RuntimeError（line 174）"""
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_update_video",
            return_value=False,
        ), patch.object(db.base_db, "get_video_info", return_value={"code": "X-001"}):
            with pytest.raises(RuntimeError, match="回傳失敗"):
                db.update_video("X-001", {"title": "t"})

    def test_json_database_error_is_reraised(self, tmp_path):
        """JSONDatabaseError 應直接重新拋出（line 177）"""
        db = _make_db(tmp_path)
        with patch.object(
            db.base_db, "get_video_info", side_effect=JSONDatabaseError("not found")
        ), pytest.raises(JSONDatabaseError):
            db.update_video("MISSING", {"title": "t"})

    def test_unexpected_exception_wrapped_as_runtime(self, tmp_path):
        """其他例外應被包裝成 RuntimeError（lines 179-180）"""
        db = _make_db(tmp_path)
        with patch.object(
            db.base_db, "get_video_info", side_effect=ValueError("oops")
        ), pytest.raises(RuntimeError, match="Go update_video 失敗"):
            db.update_video("X-001", {"title": "t"})


# ---------------------------------------------------------------------------
# add_video：錯誤路徑（lines 198-202）
# ---------------------------------------------------------------------------

class TestAddVideoErrors:
    def test_go_returns_false_raises_runtime(self, tmp_path):
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_update_video",
            return_value=False,
        ), pytest.raises(RuntimeError, match="回傳失敗"):
            db.add_video({"code": "NEW-001", "title": "t"})

    def test_unexpected_exception_wrapped(self, tmp_path):
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_update_video",
            side_effect=ConnectionError("network"),
        ), pytest.raises(RuntimeError, match="Go add_video 失敗"):
            db.add_video({"code": "NEW-001", "title": "t"})


# ---------------------------------------------------------------------------
# delete_video：錯誤路徑（lines 219-223）
# ---------------------------------------------------------------------------

class TestDeleteVideoErrors:
    def test_go_returns_false_raises_runtime(self, tmp_path):
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_delete_video",
            return_value=False,
        ), pytest.raises(RuntimeError, match="回傳失敗"):
            db.delete_video("X-001")

    def test_unexpected_exception_wrapped(self, tmp_path):
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_delete_video",
            side_effect=OSError("io"),
        ), pytest.raises(RuntimeError, match="Go delete_video 失敗"):
            db.delete_video("X-001")


# ---------------------------------------------------------------------------
# data 屬性 / get_all_videos / analyze_actress_primary_studio（lines 240, 246, 293）
# ---------------------------------------------------------------------------

class TestCompatibilityInterface:
    def test_data_property_returns_base_db_data(self, tmp_path):
        """data 屬性應委派至 base_db.data（line 240）"""
        db = _make_db(tmp_path)
        assert db.data is db.base_db.data

    def test_get_all_videos_delegates(self, tmp_path):
        """get_all_videos 應委派至 base_db（line 246）"""
        db = _make_db(tmp_path)
        with patch.object(db.base_db, "get_all_videos", return_value=[]) as mock:
            result = db.get_all_videos()
        mock.assert_called_once_with(None)
        assert result == []

    def test_analyze_actress_primary_studio_delegates(self, tmp_path):
        """analyze_actress_primary_studio 應委派至 base_db（line 293）"""
        db = _make_db(tmp_path)
        expected = {"actress_name": "女優A", "primary_studio": "S1"}
        with patch.object(
            db.base_db, "analyze_actress_primary_studio", return_value=expected
        ) as mock:
            result = db.analyze_actress_primary_studio("女優A", {"S1"})
        mock.assert_called_once_with("女優A", {"S1"})
        assert result == expected


# ---------------------------------------------------------------------------
# add_or_update_video（lines 270-287）
# ---------------------------------------------------------------------------

class TestAddOrUpdateVideo:
    def test_update_existing_video(self, tmp_path):
        """已存在的影片應走 update_video 路徑（lines 270-274）"""
        db = _make_db(tmp_path)
        with patch.object(
            db.base_db, "get_video_info", return_value={"code": "E-001", "title": "old"}
        ), patch.object(db, "update_video") as mock_update:
            db.add_or_update_video("E-001", {"title": "new"})
        mock_update.assert_called_once_with("E-001", {"title": "new"})

    def test_add_new_video(self, tmp_path):
        """不存在的影片應走 add_video 路徑（lines 276-285）"""
        db = _make_db(tmp_path)
        with patch.object(db.base_db, "get_video_info", return_value=None):
            with patch.object(db, "add_video") as mock_add:
                db.add_or_update_video("NEW-002", {"title": "new"})
        assert mock_add.called
        added_video = mock_add.call_args[0][0]
        assert added_video["code"] == "NEW-002"


# ---------------------------------------------------------------------------
# compact_if_needed（lines 303-320）
# ---------------------------------------------------------------------------

class TestCompactIfNeeded:
    def test_no_compact_when_below_threshold(self, tmp_path):
        db = _make_db(tmp_path)
        db.journal_size = 0
        db.journal_created_at = datetime.now(UTC)
        with patch.object(db, "compact") as mock_compact:
            result = db.compact_if_needed()
        mock_compact.assert_not_called()
        assert result is False

    def test_compact_triggered_by_size(self, tmp_path):
        """journal_size >= 閾值時應觸發 compact（lines 303-308）"""
        db = _make_db(tmp_path)
        db.journal_size = JOURNAL_SIZE_THRESHOLD
        with patch.object(db, "compact") as mock_compact:
            result = db.compact_if_needed()
        mock_compact.assert_called_once()
        assert result is True

    def test_compact_triggered_by_age(self, tmp_path):
        """journal 年齡超過閾值時應觸發 compact（lines 310-318）"""
        db = _make_db(tmp_path)
        db.journal_size = 0
        # 設定為超過閾值的舊時間
        from datetime import timedelta
        db.journal_created_at = datetime.now(UTC) - timedelta(seconds=JOURNAL_AGE_THRESHOLD + 10)
        with patch.object(db, "compact") as mock_compact:
            result = db.compact_if_needed()
        mock_compact.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# compact：Go 回傳 False / 例外（lines 335, 352-356）
# ---------------------------------------------------------------------------

class TestCompactErrors:
    def test_compact_go_returns_false_raises(self, tmp_path):
        """compact 的 Go CLI 回傳 False 時應拋出 JSONDatabaseError（line 335）"""
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_compact_journal",
            return_value=False,
        ), pytest.raises(JSONDatabaseError):
            db.compact()

    def test_compact_unexpected_exception_raises(self, tmp_path):
        """compact 遇到非 JSONDatabaseError 時應包裝後拋出（lines 354-356）"""
        db = _make_db(tmp_path)
        with patch(
            "src.models.incremental_json_database._go_db_compact_journal",
            side_effect=RuntimeError("unexpected"),
        ), pytest.raises(JSONDatabaseError, match="合併失敗"):
            db.compact()


# ---------------------------------------------------------------------------
# get_stats（lines 365-369）
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_get_stats_returns_dict(self, tmp_path):
        """get_stats 應回傳包含 journal_size 等鍵的字典（lines 365-378）"""
        db = _make_db(tmp_path)
        stats = db.get_stats()
        assert "journal_size" in stats
        assert "dirty_videos" in stats
        assert "needs_compact" in stats
        assert "total_videos" in stats

    def test_get_stats_no_journal_created_at(self, tmp_path):
        """journal_created_at 為 None 時 age 應為 0（line 365）"""
        db = _make_db(tmp_path)
        db.journal_created_at = None
        stats = db.get_stats()
        assert stats["journal_age_seconds"] == 0
