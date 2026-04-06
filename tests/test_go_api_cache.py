"""
go_api/cache.py runner 注入模式測試

確認 cache_get / cache_set / cache_delete：
1. 不呼叫橋接層全域單例
2. 產生正確的 CLI 參數
3. 正確解析 runner 的回傳值（base64 解碼、success flag）
4. 失敗時回傳 None / False 而非拋出例外
"""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.go_runner import GoBridgeError, GoCommandRunner
from services.go_api.cache import cache_delete, cache_get, cache_set


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


class TestCacheGetRunnerInjection(unittest.TestCase):
    """cache_get 使用注入的 runner 並正確解析回傳值。"""

    def test_uses_injected_runner(self):
        payload = base64.b64encode(b"hello").decode()
        runner = _make_runner(stdout=json.dumps({"success": True, "value": payload}))
        result = cache_get("mykey", runner=runner)
        runner.run.assert_called_once()
        self.assertEqual(result, b"hello")

    def test_cmd_contains_cache_get_and_key(self):
        payload = base64.b64encode(b"data").decode()
        runner = _make_runner(stdout=json.dumps({"success": True, "value": payload}))
        cache_get("test-key", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("cache", args)
        self.assertIn("get", args)
        self.assertIn("test-key", args)

    def test_custom_cache_dir_passed(self):
        payload = base64.b64encode(b"x").decode()
        runner = _make_runner(stdout=json.dumps({"success": True, "value": payload}))
        cache_get("k", cache_dir="custom/cache", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-cache-dir", args)
        self.assertIn("custom/cache", args)

    def test_not_found_returns_none(self):
        runner = _make_runner(stdout=json.dumps({"success": False, "error": "not found"}))
        result = cache_get("missing", runner=runner)
        self.assertIsNone(result)

    def test_go_bridge_error_returns_none(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI 失敗")
        result = cache_get("key", runner=runner)
        self.assertIsNone(result)

    def test_empty_stdout_returns_none(self):
        runner = _make_runner(stdout="")
        result = cache_get("key", runner=runner)
        self.assertIsNone(result)

    def test_json_parse_error_returns_none(self):
        runner = _make_runner(stdout="not-json")
        runner.parse_json.side_effect = GoBridgeError("parse error")
        result = cache_get("key", runner=runner)
        self.assertIsNone(result)


class TestCacheSetRunnerInjection(unittest.TestCase):
    """cache_set 使用注入的 runner 並正確傳送 base64 值與 TTL。"""

    def test_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        result = cache_set("mykey", b"hello", runner=runner)
        runner.run.assert_called_once()
        self.assertTrue(result)

    def test_cmd_contains_cache_set_and_key_and_value(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_set("k", b"world", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("cache", args)
        self.assertIn("set", args)
        self.assertIn("k", args)
        expected_b64 = base64.b64encode(b"world").decode()
        self.assertIn(expected_b64, args)

    def test_default_ttl_hours_passed(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_set("k", b"v", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-ttl-hours", args)
        idx = args.index("-ttl-hours")
        self.assertEqual(args[idx + 1], "24")

    def test_custom_ttl_hours_passed(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_set("k", b"v", ttl_hours=48, runner=runner)
        args = runner.run.call_args[0][0]
        idx = args.index("-ttl-hours")
        self.assertEqual(args[idx + 1], "48")

    def test_custom_cache_dir_passed(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_set("k", b"v", cache_dir="my/cache", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-cache-dir", args)
        self.assertIn("my/cache", args)

    def test_failure_returns_false(self):
        runner = _make_runner(stdout=json.dumps({"success": False, "error": "disk full"}))
        result = cache_set("k", b"v", runner=runner)
        self.assertFalse(result)

    def test_go_bridge_error_returns_false(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI 失敗")
        result = cache_set("k", b"v", runner=runner)
        self.assertFalse(result)

    def test_empty_stdout_returns_false(self):
        runner = _make_runner(stdout="")
        result = cache_set("k", b"v", runner=runner)
        self.assertFalse(result)


class TestCacheDeleteRunnerInjection(unittest.TestCase):
    """cache_delete 使用注入的 runner 並正確解析 success flag。"""

    def test_uses_injected_runner(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        result = cache_delete("mykey", runner=runner)
        runner.run.assert_called_once()
        self.assertTrue(result)

    def test_cmd_contains_cache_delete_and_key(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_delete("del-key", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("cache", args)
        self.assertIn("delete", args)
        self.assertIn("del-key", args)

    def test_custom_cache_dir_passed(self):
        runner = _make_runner(stdout=json.dumps({"success": True}))
        cache_delete("k", cache_dir="alt/cache", runner=runner)
        args = runner.run.call_args[0][0]
        self.assertIn("-cache-dir", args)
        self.assertIn("alt/cache", args)

    def test_failure_returns_false(self):
        runner = _make_runner(stdout=json.dumps({"success": False, "error": "not found"}))
        result = cache_delete("k", runner=runner)
        self.assertFalse(result)

    def test_go_bridge_error_returns_false(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run.side_effect = GoBridgeError("CLI 失敗")
        result = cache_delete("k", runner=runner)
        self.assertFalse(result)

    def test_empty_stdout_returns_false(self):
        runner = _make_runner(stdout="")
        result = cache_delete("k", runner=runner)
        self.assertFalse(result)

    def test_json_parse_error_returns_false(self):
        runner = _make_runner(stdout="bad-json")
        runner.parse_json.side_effect = GoBridgeError("parse error")
        result = cache_delete("k", runner=runner)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
