"""JSONDBManager Go 委派測試 (Phase 5 Task 5-4)。"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestGetVideoInfoDelegation:
    """get_video_info() Go 委派測試"""

    def test_delegates_to_go_when_available(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        with patch(
            "models.json_database._go_db_get_video",
            return_value={"code": "STARS-001"},
        ) as mock:
            result = db.get_video_info("STARS-001")
        mock.assert_called_once_with("STARS-001", data_dir=str(tmp_path))
        assert result == {"code": "STARS-001"}

    def test_returns_none_for_missing_video(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        with patch(
            "models.json_database._go_db_get_video",
            return_value=None,
        ):
            result = db.get_video_info("NONEXISTENT")
        assert result is None


class TestAddOrUpdateVideoDelegation:
    """add_or_update_video() Go 委派測試"""

    def test_delegates_to_go_when_available(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        with patch(
            "models.json_database._go_db_update_video", return_value=True
        ) as mock:
            code = db.add_or_update_video("STARS-001", {"title": "Test"})
        assert code == "STARS-001"
        assert mock.called

    def test_updates_memory_cache_after_go_write(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        with patch("models.json_database._go_db_update_video", return_value=True):
            db.add_or_update_video("STARS-001", {"title": "Test"})
        assert "STARS-001" in db.data["videos"]

    def test_raises_when_go_returns_failure(self, tmp_path):
        """Go db_update_video 回傳 False 時應 raise RuntimeError。"""
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        with patch("models.json_database._go_db_update_video", return_value=False):
            with pytest.raises(RuntimeError):
                db.add_or_update_video("STARS-001", {"title": "Test"})

    def test_accepts_video_dict_as_first_arg(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        with patch("models.json_database._go_db_update_video", return_value=True):
            code = db.add_or_update_video({"code": "STARS-002", "title": "Test 2"})
        assert code == "STARS-002"


class TestDeleteVideoDelegation:
    """delete_video() Go 委派測試"""

    def test_delegates_to_go_when_available(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
        with patch(
            "models.json_database._go_db_delete_video", return_value=True
        ) as mock:
            result = db.delete_video("STARS-001")
        assert result is True
        assert "STARS-001" not in db.data["videos"]
        mock.assert_called_once_with("STARS-001", data_dir=str(tmp_path))

    def test_cleans_up_links_after_go_delete(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
        db.data["links"] = [
            {"video_code": "STARS-001", "actress_id": "A1"},
            {"video_code": "STARS-002", "actress_id": "A2"},
        ]
        with patch("models.json_database._go_db_delete_video", return_value=True):
            db.delete_video("STARS-001")
        remaining_links = db.data.get("links", [])
        assert all(lnk["video_code"] != "STARS-001" for lnk in remaining_links)
        assert len(remaining_links) == 1

    def test_raises_on_go_exception(self, tmp_path):
        """Go 拋出例外時 delete_video 應 raise RuntimeError。"""
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db.data["videos"]["STARS-001"] = {"code": "STARS-001", "title": "T"}
        with patch(
            "models.json_database._go_db_delete_video",
            side_effect=Exception("Go 失敗"),
        ):
            with pytest.raises(RuntimeError):
                db.delete_video("STARS-001")


class TestGetAllVideosDelegation:
    """get_all_videos() Go 委派測試"""

    def test_delegates_to_go_when_available(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        mock_videos = [{"code": "STARS-001"}, {"code": "STARS-002"}]
        with patch(
            "models.json_database._go_db_get_all_videos", return_value=mock_videos
        ) as mock:
            result = db.get_all_videos()
        mock.assert_called_once_with(data_dir=str(tmp_path))
        assert len(result) == 2

    def test_applies_filter_after_go_fetch(self, tmp_path):
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        mock_videos = [
            {"code": "STARS-001", "studio": "ABC"},
            {"code": "STARS-002", "studio": "XYZ"},
        ]
        with patch(
            "models.json_database._go_db_get_all_videos", return_value=mock_videos
        ):
            result = db.get_all_videos(filter_dict={"studio": "ABC"})
        assert len(result) == 1
        assert result[0]["code"] == "STARS-001"

    def test_falls_back_to_python_on_go_unavailable(self, tmp_path):
        """Go 拋出例外時從記憶體返回影片清單。"""
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
        with patch(
            "models.json_database._go_db_get_all_videos",
            side_effect=Exception("fail"),
        ):
            result = db.get_all_videos()
        assert len(result) == 1

    def test_falls_back_to_python_on_go_failure(self, tmp_path):
        """Go 拋出例外時從記憶體返回影片清單。"""
        from models.json_database import JSONDBManager

        db = JSONDBManager(str(tmp_path))
        db._GO_DB_AVAILABLE = True
        db.data["videos"]["STARS-001"] = {"code": "STARS-001"}
        with patch(
            "models.json_database._go_db_get_all_videos",
            side_effect=Exception("fail"),
        ):
            result = db.get_all_videos()
        assert len(result) == 1
