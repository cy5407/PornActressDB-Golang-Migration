"""
測試 IncrementalJSONDB 的 Go 委派機制

驗證：
1. get_video_info 在 Go 可用時委派給 db_get_video
2. update_video 在 Go 可用時委派給 db_update_video
3. add_video / delete_video 在 Go 可用時委派給 Go CLI
4. Go 失敗時不會默默寫入 Python journal
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _make_db_with_go(tmp_path: Path, go_available: bool = True):
    """建立帶有 Go 委派設定的 IncrementalJSONDB 實例。"""
    import json as _json
    from pathlib import Path as _Path

    data_dir = tmp_path / "json_db"
    data_dir.mkdir(parents=True, exist_ok=True)
    # 寫入最小資料
    data_file = data_dir / "data.json"
    _json.dump(
        {
            "videos": {
                "SONE-001": {
                    "code": "SONE-001",
                    "title": "原始標題",
                    "search_status": "imported",
                }
            },
            "actresses": {},
            "video_actress_links": [],
        },
        data_file.open("w", encoding="utf-8"),
        ensure_ascii=False,
    )

    from models.incremental_json_database import IncrementalJSONDB

    db = IncrementalJSONDB(str(data_dir))
    db._GO_DB_AVAILABLE = go_available
    return db


class TestGetVideoInfoDelegation(unittest.TestCase):
    """get_video_info 委派測試"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)

    def test_get_video_info_calls_go_when_available(self):
        """Go 可用時呼叫 _go_db_get_video。"""
        db = _make_db_with_go(self._tmp_path, go_available=True)
        expected = {"code": "SONE-001", "title": "Go 標題"}

        with patch(
            "models.incremental_json_database._go_db_get_video",
            return_value=expected,
        ) as mock_go:
            result = db.get_video_info("SONE-001")

        mock_go.assert_called_once()
        args = mock_go.call_args[0]
        self.assertEqual(args[0], "SONE-001")
        self.assertEqual(result["title"], "Go 標題")

    def test_get_video_info_skips_go_when_unavailable(self):
        """Go 不可用時直接使用 Python 記憶體查詢。"""
        db = _make_db_with_go(self._tmp_path, go_available=False)

        with patch(
            "models.incremental_json_database._go_db_get_video"
        ) as mock_go:
            result = db.get_video_info("SONE-001")

        mock_go.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "SONE-001")

    def test_get_video_info_falls_back_on_go_error(self):
        """Go 拋出例外時 fallback 到 Python。"""
        from services.go_runner import GoBridgeError

        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_get_video",
            side_effect=GoBridgeError("CLI 故障"),
        ):
            result = db.get_video_info("SONE-001")

        # Python fallback 應回傳記憶體中的資料
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "SONE-001")

    def test_get_video_info_returns_none_when_not_found_via_go(self):
        """Go 回傳 None（影片不存在）時直接回傳 None，不 fallback。"""
        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_get_video",
            return_value=None,
        ):
            result = db.get_video_info("NOT-EXIST")

        self.assertIsNone(result)


class TestUpdateVideoDelegation(unittest.TestCase):
    """update_video 委派測試"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)

    def test_update_video_calls_go_when_available(self):
        """Go 可用時呼叫 _go_db_update_video 並傳入合併後的完整字典。"""
        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_update_video",
            return_value=True,
        ) as mock_go:
            db.update_video("SONE-001", {"title": "新標題"})

        mock_go.assert_called_once()
        code_arg, video_arg = mock_go.call_args[0][:2]
        self.assertEqual(code_arg, "SONE-001")
        # 傳入的應是合併後的完整字典（包含原始欄位 + 更新欄位）
        self.assertEqual(video_arg["title"], "新標題")
        self.assertEqual(video_arg["code"], "SONE-001")

    def test_update_video_syncs_memory_on_go_success(self):
        """Go 成功時應同步更新記憶體快取。"""
        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_update_video",
            return_value=True,
        ):
            db.update_video("SONE-001", {"title": "已更新"})

        # 記憶體中應立即反映
        cached = db.base_db.data["videos"].get("SONE-001", {})
        self.assertEqual(cached.get("title"), "已更新")

    def test_update_video_falls_back_on_go_exception(self):
        """Go 拋出例外時應 raise RuntimeError（不再寫入 journal）。"""
        from services.go_runner import GoBridgeError

        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_update_video",
            side_effect=GoBridgeError("CLI 故障"),
        ):
            with self.assertRaises(RuntimeError):
                db.update_video("SONE-001", {"title": "fallback 標題"})

    def test_update_video_skips_go_when_unavailable(self):
        """Go 不可用時應 raise RuntimeError。"""
        db = _make_db_with_go(self._tmp_path, go_available=False)

        with patch(
            "models.incremental_json_database._go_db_update_video"
        ) as mock_go:
            with self.assertRaises(RuntimeError):
                db.update_video("SONE-001", {"title": "Python 標題"})

        mock_go.assert_not_called()

    def test_update_video_raises_for_nonexistent_video(self):
        """更新不存在的影片時應拋出 JSONDatabaseError。"""
        from src.models.json_types import JSONDatabaseError

        db = _make_db_with_go(self._tmp_path, go_available=True)

        with patch(
            "models.incremental_json_database._go_db_update_video"
        ) as mock_go:
            with self.assertRaises(JSONDatabaseError):
                db.update_video("NOT-EXIST", {"title": "不存在"})

        mock_go.assert_not_called()

    def test_go_db_available_attribute_exists(self):
        """確認 _GO_DB_AVAILABLE 類別屬性存在。"""
        from models.incremental_json_database import IncrementalJSONDB
        self.assertIn("_GO_DB_AVAILABLE", IncrementalJSONDB.__dict__)


class TestAddDeleteVideoDelegation(unittest.TestCase):
    """add_video / delete_video 委派測試"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)

    def test_add_video_calls_go_when_available(self):
        db = _make_db_with_go(self._tmp_path, go_available=True)
        video = {"code": "SONE-777", "title": "新增標題"}

        with patch("models.incremental_json_database._go_db_update_video", return_value=True) as mock_go:
            db.add_video(video)

        mock_go.assert_called_once()
        code_arg, video_arg = mock_go.call_args[0][:2]
        self.assertEqual(code_arg, "SONE-777")
        self.assertEqual(video_arg["title"], "新增標題")
        self.assertIn("SONE-777", db.base_db.data["videos"])

    def test_add_video_raises_when_go_unavailable(self):
        db = _make_db_with_go(self._tmp_path, go_available=False)
        with patch("models.incremental_json_database._go_db_update_video") as mock_go:
            with self.assertRaises(RuntimeError):
                db.add_video({"code": "SONE-888", "title": "Python"})
        mock_go.assert_not_called()

    def test_delete_video_calls_go_when_available(self):
        db = _make_db_with_go(self._tmp_path, go_available=True)
        db.base_db.data["videos"]["SONE-999"] = {"code": "SONE-999", "title": "刪除標題"}

        with patch("models.incremental_json_database._go_db_delete_video", return_value=True) as mock_go:
            db.delete_video("SONE-999")

        mock_go.assert_called_once_with("SONE-999", str(db.data_dir))
        self.assertNotIn("SONE-999", db.base_db.data["videos"])

    def test_delete_video_raises_when_go_unavailable(self):
        db = _make_db_with_go(self._tmp_path, go_available=False)
        with patch("models.incremental_json_database._go_db_delete_video") as mock_go:
            with self.assertRaises(RuntimeError):
                db.delete_video("SONE-000")
        mock_go.assert_not_called()


if __name__ == "__main__":
    unittest.main()
