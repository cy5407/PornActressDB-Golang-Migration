"""
db_get_all_videos() 函式測試

測試 go_api/db.py 的 db_get_all_videos 函式:
1. 回傳列表並呼叫正確命令 (含 --full 旗標)
2. 預設 data-dir 不帶 -data-dir 旗標
3. GoBridgeError 時回傳空列表
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.go_runner import GoBridgeError, GoCommandRunner
from services.go_api.db import db_get_all_videos


def _make_runner(stdout: str = "", returncode: int = 0) -> GoCommandRunner:
    runner = MagicMock(spec=GoCommandRunner)
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    runner.run.return_value = result
    runner.parse_json.side_effect = lambda s: json.loads(s)
    return runner


class TestDbGetAllVideos(unittest.TestCase):
    """db_get_all_videos 函式行為測試。"""

    def test_returns_list_and_uses_full_flag(self):
        """應回傳列表，且命令包含 --full 旗標。"""
        videos = [{"code": "ABC-001", "title": "Test"}, {"code": "DEF-002"}]
        runner = _make_runner(json.dumps(videos))

        result = db_get_all_videos(runner=runner)

        self.assertEqual(result, videos)
        runner.run.assert_called_once()
        cmd_args = runner.run.call_args[0][0]
        self.assertIn("--full", cmd_args)
        self.assertIn("db", cmd_args)
        self.assertIn("list", cmd_args)

    def test_default_data_dir_omits_flag(self):
        """預設 data_dir 時不應帶 -data-dir 旗標。"""
        runner = _make_runner(json.dumps([]))

        db_get_all_videos(data_dir="data/json_db", runner=runner)

        cmd_args = runner.run.call_args[0][0]
        self.assertNotIn("-data-dir", cmd_args)

    def test_custom_data_dir_includes_flag(self):
        """自訂 data_dir 時應包含 -data-dir 旗標。"""
        runner = _make_runner(json.dumps([{"code": "X-001"}]))

        db_get_all_videos(data_dir="/tmp/mydb", runner=runner)

        cmd_args = runner.run.call_args[0][0]
        self.assertIn("-data-dir", cmd_args)
        self.assertIn("/tmp/mydb", cmd_args)

    def test_returns_empty_list_on_go_bridge_error(self):
        """GoBridgeError 時應回傳空列表，不拋例外。"""
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI not found")

        result = db_get_all_videos(runner=runner)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
