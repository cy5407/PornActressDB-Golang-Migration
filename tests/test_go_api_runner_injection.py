"""
Go API runner 注入測試

驗證 db.py / identify.py 遵循與 scan.py / move.py 相同的 runner-injection 模式：
每個函式都接受 runner: GoCommandRunner | None，當傳入 mock runner 時，
函式不會呼叫 _get_bridge()，而是直接使用注入的 runner。
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.go_runner import GoCommandRunner


def _make_runner(stdout_data) -> GoCommandRunner:
    """建立回傳固定 JSON 的 mock runner。"""
    runner = MagicMock(spec=GoCommandRunner)
    result = MagicMock()
    result.returncode = 0
    result.stdout = json.dumps(stdout_data)
    result.stderr = ""
    runner.run.return_value = result
    runner.parse_json.return_value = stdout_data
    return runner


class TestDbRunnerInjection(unittest.TestCase):
    """驗證 db.py 所有公開函式支援 runner 注入，且不依賴 _get_bridge() singleton。"""

    def test_db_get_video_uses_injected_runner(self):
        """db_get_video 應使用注入的 runner 而非 singleton bridge。"""
        from services.go_api.db import db_get_video

        video_data = {"code": "SONE-001", "title": "測試影片", "studio": "S1"}
        runner = _make_runner(video_data)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_get_video("SONE-001", runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("get", call_args)
        self.assertIn("SONE-001", call_args)
        self.assertEqual(result, video_data)

    def test_db_get_video_returns_none_for_null_stdout(self):
        """db_get_video 對 null stdout 回傳 None。"""
        from services.go_api.db import db_get_video

        runner = MagicMock(spec=GoCommandRunner)
        result_mock = MagicMock()
        result_mock.returncode = 0
        result_mock.stdout = "null"
        runner.run.return_value = result_mock

        result = db_get_video("MISSING-001", runner=runner)
        self.assertIsNone(result)

    def test_db_update_video_uses_injected_runner(self):
        """db_update_video 應透過注入的 runner 呼叫 db update 命令。"""
        from services.go_api.db import db_update_video

        success_resp = {"success": True, "action": "update", "code": "SONE-001", "data_dir": "data/json_db"}
        runner = _make_runner(success_resp)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_update_video("SONE-001", {"title": "新標題"}, runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("update", call_args)
        self.assertIn("-json", call_args)
        self.assertTrue(result)

    def test_db_delete_video_uses_injected_runner(self):
        """db_delete_video 應透過注入的 runner 呼叫 db delete 命令。"""
        from services.go_api.db import db_delete_video

        success_resp = {"success": True, "action": "delete", "code": "SONE-001", "data_dir": "data/json_db"}
        runner = _make_runner(success_resp)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_delete_video("SONE-001", runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("delete", call_args)
        self.assertIn("-json", call_args)
        self.assertTrue(result)

    def test_db_list_videos_uses_injected_runner(self):
        """db_list_videos 應透過注入的 runner 呼叫 db list 命令。"""
        from services.go_api.db import db_list_videos

        codes = ["SONE-001", "SSIS-123"]
        runner = _make_runner(codes)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_list_videos(runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("list", call_args)
        self.assertEqual(result, codes)

    def test_db_get_stats_uses_injected_runner(self):
        """db_get_stats 應透過注入的 runner 呼叫 db stats 命令。"""
        from services.go_api.db import db_get_stats

        stats = {"total_videos": 100, "go_accelerated": True}
        runner = _make_runner(stats)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_get_stats(runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("stats", call_args)
        self.assertEqual(result, stats)

    def test_db_compact_journal_uses_injected_runner(self):
        """db_compact_journal 應透過注入的 runner 呼叫 db compact 命令。"""
        from services.go_api.db import db_compact_journal

        success_resp = {"success": True, "action": "compact", "data_dir": "data/json_db"}
        runner = _make_runner(success_resp)

        with patch("services.go_api.db._get_bridge") as mock_get_bridge:
            result = db_compact_journal(runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("db", call_args)
        self.assertIn("compact", call_args)
        self.assertIn("-json", call_args)
        self.assertTrue(result)

    def test_db_custom_data_dir_forwarded(self):
        """自訂 data_dir 應透過 -data-dir 旗標傳入命令。"""
        from services.go_api.db import db_list_videos

        runner = _make_runner([])

        db_list_videos(data_dir="custom/dir", runner=runner)

        call_args = runner.run.call_args[0][0]
        self.assertIn("-data-dir", call_args)
        self.assertIn("custom/dir", call_args)


class TestIdentifyRunnerInjection(unittest.TestCase):
    """驗證 identify.py 所有公開函式支援 runner 注入，且不依賴 _get_bridge() singleton。"""

    def test_identify_studio_uses_injected_runner(self):
        """identify_studio 應透過注入的 runner 呼叫 identify 命令。"""
        from services.go_api.identify import identify_studio

        response = {"code": "SSIS-001", "studio": "S1", "prefix": "SSIS"}
        runner = _make_runner(response)

        with patch("services.go_api.identify._get_bridge") as mock_get_bridge:
            result = identify_studio("SSIS-001", runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("identify", call_args)
        self.assertIn("SSIS-001", call_args)
        self.assertEqual(result, response)

    def test_identify_studio_check_major_flag(self):
        """check_major=True 應插入 -major 旗標。"""
        from services.go_api.identify import identify_studio

        runner = _make_runner({"code": "SSIS-001", "studio": "S1"})

        identify_studio("SSIS-001", check_major=True, runner=runner)

        call_args = runner.run.call_args[0][0]
        self.assertIn("-major", call_args)

    def test_identify_studios_batch_uses_injected_runner(self):
        """identify_studios_batch 應透過注入的 runner 呼叫 identify -batch 命令。"""
        from services.go_api.identify import identify_studios_batch

        batch_resp = [{"code": "SSIS-001", "studio": "S1"}, {"code": "MIDV-456", "studio": "MOODYZ"}]
        runner = _make_runner(batch_resp)

        with patch("services.go_api.identify._get_bridge") as mock_get_bridge:
            result = identify_studios_batch(["SSIS-001", "MIDV-456"], runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("identify", call_args)
        self.assertIn("-batch", call_args)
        self.assertEqual(result, batch_resp)

    def test_list_studios_uses_injected_runner(self):
        """list_studios 應透過注入的 runner 呼叫 identify -list -json 命令。"""
        from services.go_api.identify import list_studios

        studios_resp = [{"studio": "S1", "is_major": True}, {"studio": "MOODYZ", "is_major": True}]
        runner = _make_runner(studios_resp)

        with patch("services.go_api.identify._get_bridge") as mock_get_bridge:
            result = list_studios(runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("identify", call_args)
        self.assertIn("-list", call_args)
        self.assertIn("-json", call_args)
        self.assertEqual(result, ["S1", "MOODYZ"])

    def test_get_studio_prefixes_uses_injected_runner(self):
        """get_studio_prefixes 應透過注入的 runner 呼叫 identify -prefixes -json 命令。"""
        from services.go_api.identify import get_studio_prefixes

        prefixes_resp = {"studio": "S1", "prefixes": ["SSIS", "SONE"]}
        runner = _make_runner(prefixes_resp)

        with patch("services.go_api.identify._get_bridge") as mock_get_bridge:
            result = get_studio_prefixes("S1", runner=runner)

        mock_get_bridge.assert_not_called()
        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        self.assertIn("identify", call_args)
        self.assertIn("-prefixes", call_args)
        self.assertIn("-json", call_args)
        self.assertIn("S1", call_args)
        self.assertEqual(result, ["SSIS", "SONE"])


class TestGoBridgeClassMethodsDelegation(unittest.TestCase):
    """驗證 GoBridge 實例方法將 self._runner 注入至 go_api 函式（與 scan/move 模式一致）。"""

    def _make_bridge_with_mock_runner(self):
        from services.go_bridge import GoBridge

        bridge = GoBridge(exe_path="/nonexistent/classifier")
        bridge._runner = MagicMock(spec=GoCommandRunner)
        return bridge

    def test_bridge_db_get_video_passes_runner(self):
        """GoBridge.db_get_video 應將 self._runner 注入至 api.db_get_video。"""
        bridge = self._make_bridge_with_mock_runner()
        video_data = {"code": "SONE-001", "studio": "S1"}

        with patch("services.go_api.db_get_video") as mock_fn:
            mock_fn.return_value = video_data
            bridge.db_get_video("SONE-001")

        mock_fn.assert_called_once_with("SONE-001", "data/json_db", runner=bridge._runner)

    def test_bridge_db_update_video_passes_runner(self):
        """GoBridge.db_update_video 應將 self._runner 注入至 api.db_update_video。"""
        bridge = self._make_bridge_with_mock_runner()

        with patch("services.go_api.db_update_video") as mock_fn:
            mock_fn.return_value = True
            bridge.db_update_video("SONE-001", {"title": "X"})

        mock_fn.assert_called_once_with("SONE-001", {"title": "X"}, "data/json_db", runner=bridge._runner)

    def test_bridge_list_studios_passes_runner(self):
        """GoBridge.list_studios 應將 self._runner 注入至 api.list_studios。"""
        bridge = self._make_bridge_with_mock_runner()

        with patch("services.go_api.list_studios") as mock_fn:
            mock_fn.return_value = ["S1"]
            bridge.list_studios()

        mock_fn.assert_called_once_with(runner=bridge._runner)

    def test_bridge_identify_studio_passes_runner(self):
        """GoBridge.identify_studio 應將 self._runner 注入至 api.identify_studio。"""
        bridge = self._make_bridge_with_mock_runner()

        with patch("services.go_api.identify_studio") as mock_fn:
            mock_fn.return_value = {"code": "SSIS-001", "studio": "S1"}
            bridge.identify_studio("SSIS-001")

        mock_fn.assert_called_once_with("SSIS-001", False, runner=bridge._runner)


if __name__ == "__main__":
    unittest.main()
