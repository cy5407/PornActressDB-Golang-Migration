"""
go_api runner 注入模式測試

確認 go_api/db.py 與 go_api/identify.py 的函式在注入自訂 runner 時：
1. 不呼叫橋接層全域單例
2. 產生正確的 CLI 參數
3. 正確解析 runner 的回傳值
4. GoBridge 實例方法將 self._runner 傳入 go_api 函式
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.go_runner import GoBridgeError, GoCommandRunner
from services.go_api.db import (
    db_compact_journal,
    db_delete_video,
    db_get_stats,
    db_get_video,
    db_list_videos,
    db_update_video,
)
from services.go_api.identify import (
    get_studio_prefixes,
    identify_studio,
    identify_studios_batch,
    list_studios,
)


def _make_runner(stdout: str = "", returncode: int = 0) -> GoCommandRunner:
    """建立回傳指定 JSON 輸出的假 runner。"""
    runner = MagicMock(spec=GoCommandRunner)
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    runner.run.return_value = result
    runner.parse_json.side_effect = lambda s: json.loads(s)
    return runner


class TestDbRunnerInjection(unittest.TestCase):
    """db.py 函式接受注入的 runner 並正確使用它。"""

    def test_db_get_video_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001", "title": "Test"}))
        result = db_get_video("SONE-001", runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("db", args)
        self.assertIn("get", args)
        self.assertIn("SONE-001", args)
        self.assertEqual(result["code"], "SONE-001")

    def test_db_get_video_null_returns_none(self):
        runner = _make_runner(stdout="null")
        result = db_get_video("MISSING", runner=runner)
        self.assertIsNone(result)

    def test_db_get_video_custom_data_dir(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001"}))
        db_get_video("SONE-001", data_dir="custom/path", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-data-dir", args)
        self.assertIn("custom/path", args)

    def test_db_get_video_default_data_dir_omitted(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001"}))
        db_get_video("SONE-001", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertNotIn("-data-dir", args)

    def test_db_list_videos_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps(["SONE-001", "SSIS-123"]))
        result = db_list_videos(runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("db", args)
        self.assertIn("list", args)
        self.assertEqual(result, ["SONE-001", "SSIS-123"])

    def test_db_list_videos_custom_data_dir(self):
        runner = _make_runner(stdout="[]")
        db_list_videos(data_dir="other/path", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-data-dir", args)
        self.assertIn("other/path", args)

    def test_db_get_stats_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"total": 5}))
        result = db_get_stats(runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("stats", args)
        self.assertEqual(result["total"], 5)

    def test_db_delete_video_success(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        ok = db_delete_video("SONE-001", runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("delete", args)
        self.assertIn("SONE-001", args)
        self.assertTrue(ok)

    def test_db_delete_video_failure_returns_false(self):
        runner = _make_runner(stdout=json.dumps({"success": False}))
        ok = db_delete_video("SONE-001", runner=runner)
        self.assertFalse(ok)

    def test_db_compact_journal_success(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        ok = db_compact_journal(runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("compact", args)
        self.assertIn("-json", args)
        self.assertTrue(ok)

    def test_db_compact_journal_failure_returns_false(self):
        runner = _make_runner(stdout=json.dumps({"success": False}))
        ok = db_compact_journal(runner=runner)
        self.assertFalse(ok)

    def test_db_update_video_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        ok = db_update_video("SONE-001", {"title": "新標題"}, runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("update", args)
        self.assertIn("-json", args)
        self.assertIn("SONE-001", args)
        self.assertTrue(ok)

    def test_db_update_video_failure_returns_false(self):
        runner = _make_runner(stdout=json.dumps({"success": False}))
        ok = db_update_video("SONE-001", {"title": "x"}, runner=runner)
        self.assertFalse(ok)

    def test_db_list_videos_error_returns_empty(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI not found")
        result = db_list_videos(runner=runner)
        self.assertEqual(result, [])

    def test_db_get_stats_error_returns_empty_dict(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI not found")
        result = db_get_stats(runner=runner)
        self.assertEqual(result, {})


class TestIdentifyRunnerInjection(unittest.TestCase):
    """identify.py 函式接受注入的 runner 並正確使用它。"""

    def test_identify_studio_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001", "studio": "S1"}))
        result = identify_studio("SONE-001", runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("identify", args)
        self.assertIn("SONE-001", args)
        self.assertEqual(result["studio"], "S1")

    def test_identify_studio_check_major_adds_flag(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001", "studio": "S1"}))
        identify_studio("SONE-001", check_major=True, runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-major", args)

    def test_identify_studio_no_major_omits_flag(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001", "studio": "S1"}))
        identify_studio("SONE-001", check_major=False, runner=runner)
        args = runner.run.call_args[0][0]
        self.assertNotIn("-major", args)

    def test_identify_studio_error_returns_unknown(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("failed")
        result = identify_studio("BAD", runner=runner)
        self.assertEqual(result["studio"], "UNKNOWN")
        self.assertEqual(result["code"], "BAD")

    def test_identify_studios_batch_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps([{"code": "SONE-001", "studio": "S1"}]))
        result = identify_studios_batch(["SONE-001"], runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("identify", args)
        self.assertIn("-batch", args)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["studio"], "S1")

    def test_identify_studios_batch_error_returns_empty(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("failed")
        result = identify_studios_batch(["SONE-001"], runner=runner)
        self.assertEqual(result, [])

    def test_list_studios_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps([{"studio": "S1"}, {"studio": "MOODYZ"}]))
        result = list_studios(runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("-list", args)
        self.assertIn("-json", args)
        self.assertEqual(result, ["S1", "MOODYZ"])

    def test_list_studios_filters_non_string_entries(self):
        runner = _make_runner(stdout=json.dumps([{"studio": "S1"}, {"studio": 123}, {}]))
        result = list_studios(runner=runner)
        self.assertEqual(result, ["S1"])

    def test_get_studio_prefixes_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"prefixes": ["SONE", "SSIS"]}))
        result = get_studio_prefixes("S1", runner=runner)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("-prefixes", args)
        self.assertIn("-json", args)
        self.assertIn("S1", args)
        self.assertEqual(result, ["SONE", "SSIS"])

    def test_get_studio_prefixes_error_returns_empty(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("failed")
        result = get_studio_prefixes("UNKNOWN_STUDIO", runner=runner)
        self.assertEqual(result, [])


class TestGoBridgeInstanceMethods(unittest.TestCase):
    """GoBridge 實例方法將 self._runner 傳入 go_api 函式。"""

    def _make_bridge(self, runner: GoCommandRunner):
        """建立繞過 exe 偵測的假 GoBridge 實例。"""
        from services.go_bridge import GoBridge
        bridge = GoBridge.__new__(GoBridge)
        bridge._runner = runner
        bridge.log_dir = "logs"
        bridge.default_workers = 10
        bridge.default_strategy = "skip"
        bridge._available = True
        return bridge

    def test_bridge_db_get_video_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001"}))
        bridge = self._make_bridge(runner)
        result = bridge.db_get_video("SONE-001")
        runner.run.assert_called_once()
        self.assertEqual(result["code"], "SONE-001")

    def test_bridge_db_list_videos_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps(["SONE-001"]))
        bridge = self._make_bridge(runner)
        result = bridge.db_list_videos()
        runner.run.assert_called_once()
        self.assertEqual(result, ["SONE-001"])

    def test_bridge_db_get_stats_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"total": 3}))
        bridge = self._make_bridge(runner)
        result = bridge.db_get_stats()
        runner.run.assert_called_once()
        self.assertEqual(result["total"], 3)

    def test_bridge_db_delete_video_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        bridge = self._make_bridge(runner)
        ok = bridge.db_delete_video("SONE-001")
        runner.run.assert_called_once()
        self.assertTrue(ok)

    def test_bridge_db_compact_journal_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        bridge = self._make_bridge(runner)
        ok = bridge.db_compact_journal()
        runner.run.assert_called_once()
        self.assertTrue(ok)

    def test_bridge_identify_studio_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"code": "SONE-001", "studio": "S1"}))
        bridge = self._make_bridge(runner)
        result = bridge.identify_studio("SONE-001")
        runner.run.assert_called_once()
        self.assertEqual(result["studio"], "S1")

    def test_bridge_list_studios_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps([{"studio": "S1"}, {"studio": "MOODYZ"}]))
        bridge = self._make_bridge(runner)
        result = bridge.list_studios()
        runner.run.assert_called_once()
        self.assertEqual(result, ["S1", "MOODYZ"])

    def test_bridge_get_studio_prefixes_uses_own_runner(self):
        runner = _make_runner(stdout=json.dumps({"prefixes": ["SONE"]}))
        bridge = self._make_bridge(runner)
        result = bridge.get_studio_prefixes("S1")
        runner.run.assert_called_once()
        self.assertEqual(result, ["SONE"])


if __name__ == "__main__":
    unittest.main()
