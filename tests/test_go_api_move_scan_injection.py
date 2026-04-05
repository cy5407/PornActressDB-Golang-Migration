"""
go_api move.py 與 scan.py runner 注入模式測試

確認 go_api/move.py 與 go_api/scan.py 的函式在注入自訂 runner 時：
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
from services.go_api.move import (
    batch_move,
    get_operation,
    list_operations,
    move_dir,
    move_file,
    rollback,
    rollback_last,
)
from services.go_api.scan import scan_directory


_LOG_DIR = "logs"
_STRATEGY = "skip"


def _make_runner(stdout: str = "", returncode: int = 0) -> GoCommandRunner:
    """建立回傳指定 JSON 輸出的假 runner。"""
    runner = MagicMock(spec=GoCommandRunner)
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    runner.run.return_value = result
    runner.parse_json.side_effect = lambda s: json.loads(s)
    runner.run_json.side_effect = lambda args, **kwargs: json.loads(stdout)
    return runner


# ──────────────────────────────────────────────
# move_file
# ──────────────────────────────────────────────

class TestMoveFileRunnerInjection(unittest.TestCase):
    """move_file() 接受注入的 runner 並正確使用它。"""

    def test_uses_injected_runner(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_file("a.mp4", "dest/a.mp4", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        runner.run_json.assert_called_once()
        args = runner.run_json.call_args[0][0]
        self.assertIn("move", args)
        self.assertIn("-src", args)
        self.assertIn("a.mp4", args)
        self.assertIn("-dst", args)
        self.assertIn("dest/a.mp4", args)
        self.assertTrue(result.success)

    def test_strategy_passed_to_args(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        move_file("a.mp4", "dest/a.mp4", strategy="overwrite", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        args = runner.run_json.call_args[0][0]
        self.assertIn("-strategy", args)
        self.assertIn("overwrite", args)

    def test_dry_run_adds_flag(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        move_file("a.mp4", "dest/a.mp4", dry_run=True, runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        args = runner.run_json.call_args[0][0]
        self.assertIn("-dry-run", args)

    def test_dry_run_false_omits_flag(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        move_file("a.mp4", "dest/a.mp4", dry_run=False, runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        args = runner.run_json.call_args[0][0]
        self.assertNotIn("-dry-run", args)

    def test_log_dir_passed_to_args(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        move_file("a.mp4", "dest/a.mp4", runner=runner, log_dir="custom/logs", default_strategy=_STRATEGY)
        args = runner.run_json.call_args[0][0]
        self.assertIn("-log-dir", args)
        self.assertIn("custom/logs", args)

    def test_failure_result_returns_false(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": False, "error": "file exists"}
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_file("a.mp4", "dest/a.mp4", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "file exists")

    def test_skipped_result(self):
        payload = {"source": "a.mp4", "destination": "dest/a.mp4", "success": False, "skipped": True}
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_file("a.mp4", "dest/a.mp4", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        self.assertTrue(result.skipped)


# ──────────────────────────────────────────────
# move_dir
# ──────────────────────────────────────────────

class TestMoveDirRunnerInjection(unittest.TestCase):
    """move_dir() 接受注入的 runner 並正確使用它。"""

    def test_uses_injected_runner(self):
        payload = {"source_dir": "src/", "dest_dir": "dst/", "success": True, "files_moved": 3, "files_total": 3}
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_dir("src/", "dst/", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        runner.run_json.assert_called_once()
        args = runner.run_json.call_args[0][0]
        self.assertIn("move", args)
        self.assertIn("-kind", args)
        self.assertIn("dir", args)
        self.assertIn("-src", args)
        self.assertIn("src/", args)
        self.assertIn("-dst", args)
        self.assertIn("dst/", args)
        self.assertTrue(result["success"])

    def test_dry_run_adds_flag(self):
        payload = {"source_dir": "src/", "dest_dir": "dst/", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        move_dir("src/", "dst/", dry_run=True, runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        args = runner.run_json.call_args[0][0]
        self.assertIn("-dry-run", args)

    def test_files_moved_returned(self):
        payload = {"source_dir": "src/", "dest_dir": "dst/", "success": True, "files_moved": 5, "files_total": 5}
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_dir("src/", "dst/", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        self.assertEqual(result["files_moved"], 5)
        self.assertEqual(result["files_total"], 5)

    def test_errors_aggregated(self):
        payload = {
            "source_dir": "src/",
            "dest_dir": "dst/",
            "success": False,
            "errors": [{"error": "permission denied"}],
        }
        runner = _make_runner(stdout=json.dumps(payload))
        result = move_dir("src/", "dst/", runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "permission denied")


# ──────────────────────────────────────────────
# batch_move
# ──────────────────────────────────────────────

class TestBatchMoveRunnerInjection(unittest.TestCase):
    """batch_move() 接受注入的 runner 並正確使用它。"""

    def _batch_payload(self, n: int = 2) -> dict:
        return {
            "operation_id": "op-001",
            "total_items": n,
            "success_count": n,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [
                {"source": f"f{i}.mp4", "destination": f"dst/f{i}.mp4", "success": True}
                for i in range(n)
            ],
            "status": "completed",
            "summary": f"{n} 個檔案已移動",
            "duration": "0.1s",
        }

    def test_uses_injected_runner(self):
        payload = self._batch_payload(2)
        runner = _make_runner(stdout=json.dumps(payload))
        items = [{"source": "f0.mp4", "destination": "dst/f0.mp4"}, {"source": "f1.mp4", "destination": "dst/f1.mp4"}]
        result = batch_move(items, runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("move", args)
        self.assertIn("-batch", args)
        self.assertIn("-log-dir", args)
        self.assertEqual(result.success_count, 2)
        self.assertEqual(result.operation_id, "op-001")

    def test_dry_run_adds_flag(self):
        payload = self._batch_payload(1)
        runner = _make_runner(stdout=json.dumps(payload))
        batch_move([{"source": "f.mp4", "destination": "dst/f.mp4"}], dry_run=True, runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)
        args = runner.run.call_args[0][0]
        self.assertIn("-dry-run", args)

    def test_on_conflict_injected_when_missing(self):
        """Items lacking 'on_conflict' should get the effective strategy."""
        payload = self._batch_payload(1)
        runner = _make_runner(stdout=json.dumps(payload))
        import tempfile as _tempfile
        import json as _json

        # Capture the batch file contents
        batch_file_contents = {}
        original_run = runner.run.side_effect

        def capture_run(args, **kwargs):
            batch_file = args[args.index("-batch") + 1]
            with open(batch_file, encoding="utf-8") as f:
                batch_file_contents["data"] = _json.load(f)
            result = MagicMock()
            result.returncode = 0
            result.stdout = _json.dumps(payload)
            result.stderr = ""
            return result

        runner.run.side_effect = capture_run

        batch_move([{"source": "f.mp4", "destination": "dst/f.mp4"}], runner=runner, log_dir=_LOG_DIR, default_strategy="overwrite")
        self.assertEqual(batch_file_contents["data"][0]["on_conflict"], "overwrite")

    def test_error_raises_bridge_error(self):
        runner = MagicMock(spec=GoCommandRunner)
        result_mock = MagicMock()
        result_mock.returncode = 1
        result_mock.stdout = ""
        result_mock.stderr = "CLI failed"
        runner.run.return_value = result_mock
        with self.assertRaises(GoBridgeError):
            batch_move([{"source": "f.mp4", "destination": "dst/f.mp4"}], runner=runner, log_dir=_LOG_DIR, default_strategy=_STRATEGY)


# ──────────────────────────────────────────────
# list_operations / get_operation / rollback / rollback_last
# ──────────────────────────────────────────────

class TestOperationHistoryRunnerInjection(unittest.TestCase):
    """歷史操作函式接受注入的 runner 並正確使用它。"""

    def _op_payload(self, op_id: str = "op-001") -> dict:
        return {
            "id": op_id,
            "timestamp": "2026-04-01T10:00:00Z",
            "type": "batch_move",
            "status": "completed",
            "items": [],
            "total_items": 2,
            "success_count": 2,
            "failed_count": 0,
            "skipped_count": 0,
        }

    def test_list_operations_uses_injected_runner(self):
        payload = [self._op_payload("op-001"), self._op_payload("op-002")]
        runner = _make_runner(stdout=json.dumps(payload))
        results = list_operations(runner=runner, log_dir=_LOG_DIR)
        runner.run_json.assert_called_once()
        args = runner.run_json.call_args[0][0]
        self.assertIn("history", args)
        self.assertIn("list", args)
        self.assertIn("-json", args)
        self.assertIn("-log-dir", args)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, "op-001")

    def test_list_operations_limit_applied(self):
        payload = [self._op_payload(f"op-{i:03d}") for i in range(5)]
        runner = _make_runner(stdout=json.dumps(payload))
        results = list_operations(limit=3, runner=runner, log_dir=_LOG_DIR)
        self.assertEqual(len(results), 3)

    def test_list_operations_error_returns_empty(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run_json.side_effect = GoBridgeError("CLI not found")
        results = list_operations(runner=runner, log_dir=_LOG_DIR)
        self.assertEqual(results, [])

    def test_get_operation_uses_injected_runner(self):
        payload = self._op_payload("op-abc")
        runner = _make_runner(stdout=json.dumps(payload))
        result = get_operation("op-abc", runner=runner, log_dir=_LOG_DIR)
        runner.run_json.assert_called_once()
        args = runner.run_json.call_args[0][0]
        self.assertIn("history", args)
        self.assertIn("show", args)
        self.assertIn("op-abc", args)
        self.assertIn("-json", args)
        self.assertEqual(result.id, "op-abc")

    def test_get_operation_error_returns_none(self):
        runner = MagicMock(spec=GoCommandRunner)
        runner.run_json.side_effect = GoBridgeError("not found")
        result = get_operation("op-missing", runner=runner, log_dir=_LOG_DIR)
        self.assertIsNone(result)

    def test_rollback_uses_injected_runner(self):
        payload = {
            "operation_id": "op-001",
            "total_items": 1,
            "success_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
            "status": "rolled_back",
            "summary": "回滾成功",
            "duration": "0.1s",
        }
        runner = _make_runner(stdout=json.dumps(payload))
        result = rollback("op-001", runner=runner, log_dir=_LOG_DIR)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("history", args)
        self.assertIn("rollback", args)
        self.assertIn("op-001", args)
        self.assertIn("-json", args)
        self.assertEqual(result.status, "rolled_back")

    def test_rollback_failure_raises_bridge_error(self):
        runner = MagicMock(spec=GoCommandRunner)
        result_mock = MagicMock()
        result_mock.returncode = 1
        result_mock.stdout = ""
        result_mock.stderr = "operation not found"
        runner.run.return_value = result_mock
        with self.assertRaises(GoBridgeError):
            rollback("bad-id", runner=runner, log_dir=_LOG_DIR)

    def test_rollback_last_passes_last_flag(self):
        payload = {
            "operation_id": "op-999",
            "total_items": 1,
            "success_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
            "status": "rolled_back",
            "summary": "回滾成功",
            "duration": "0.1s",
        }
        runner = _make_runner(stdout=json.dumps(payload))
        result = rollback_last(runner=runner, log_dir=_LOG_DIR)
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("--last", args)
        self.assertEqual(result.status, "rolled_back")

    def test_normalize_move_batch_type(self):
        """舊日誌的 type=move_batch 應正規化為 batch_move。"""
        payload = [
            {
                "id": "op-legacy",
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "move_batch",
                "status": "completed",
                "items": [],
            }
        ]
        runner = _make_runner(stdout=json.dumps(payload))
        results = list_operations(runner=runner, log_dir=_LOG_DIR)
        self.assertEqual(results[0].type, "batch_move")


# ──────────────────────────────────────────────
# scan_directory
# ──────────────────────────────────────────────

class TestScanDirectoryRunnerInjection(unittest.TestCase):
    """scan_directory() 接受注入的 runner 並正確使用它。"""

    def test_uses_injected_runner(self):
        payload = [{"path": "/videos/SONE-001.mp4", "code": "SONE-001"}]
        runner = _make_runner(stdout=json.dumps(payload))
        results = scan_directory("/videos", runner=runner, default_workers=10)
        runner.run_json.assert_called_once()
        args = runner.run_json.call_args[0][0]
        self.assertIn("scan", args)
        self.assertIn("-dir", args)
        self.assertIn("/videos", args)
        self.assertIn("-workers", args)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "SONE-001")
        self.assertEqual(results[0].path, "/videos/SONE-001.mp4")

    def test_workers_passed_to_args(self):
        runner = _make_runner(stdout="[]")
        scan_directory("/videos", workers=20, runner=runner, default_workers=10)
        args = runner.run_json.call_args[0][0]
        self.assertIn("20", args)

    def test_default_workers_used_when_none_given(self):
        runner = _make_runner(stdout="[]")
        scan_directory("/videos", runner=runner, default_workers=8)
        args = runner.run_json.call_args[0][0]
        self.assertIn("8", args)

    def test_non_recursive_adds_flag(self):
        runner = _make_runner(stdout="[]")
        scan_directory("/videos", recursive=False, runner=runner, default_workers=10)
        args = runner.run_json.call_args[0][0]
        self.assertIn("-recursive=false", args)

    def test_recursive_true_omits_flag(self):
        runner = _make_runner(stdout="[]")
        scan_directory("/videos", recursive=True, runner=runner, default_workers=10)
        args = runner.run_json.call_args[0][0]
        self.assertNotIn("-recursive=false", args)

    def test_empty_result_returns_empty_list(self):
        runner = _make_runner(stdout="[]")
        results = scan_directory("/empty", runner=runner, default_workers=10)
        self.assertEqual(results, [])

    def test_multiple_results_parsed(self):
        payload = [
            {"path": "/v/SONE-001.mp4", "code": "SONE-001"},
            {"path": "/v/SSIS-123.mp4", "code": "SSIS-123"},
        ]
        runner = _make_runner(stdout=json.dumps(payload))
        results = scan_directory("/v", runner=runner, default_workers=10)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[1].code, "SSIS-123")


# ──────────────────────────────────────────────
# GoBridge instance methods → pass self._runner
# ──────────────────────────────────────────────

class TestGoBridgeMoveAndScanMethods(unittest.TestCase):
    """GoBridge 實例方法將 self._runner 傳入 go_api 移動與掃描函式。"""

    def _make_bridge(self, runner: GoCommandRunner):
        from services.go_bridge import GoBridge
        bridge = GoBridge.__new__(GoBridge)
        bridge._runner = runner
        bridge.log_dir = _LOG_DIR
        bridge.default_workers = 10
        bridge.default_strategy = _STRATEGY
        bridge._available = True
        return bridge

    def test_bridge_scan_directory_uses_own_runner(self):
        payload = [{"path": "/v/SONE-001.mp4", "code": "SONE-001"}]
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        results = bridge.scan_directory("/v")
        runner.run_json.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "SONE-001")

    def test_bridge_move_file_uses_own_runner(self):
        payload = {"source": "a.mp4", "destination": "dst/a.mp4", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.move_file("a.mp4", "dst/a.mp4")
        runner.run_json.assert_called_once()
        self.assertTrue(result.success)

    def test_bridge_move_dir_uses_own_runner(self):
        payload = {"source_dir": "src/", "dest_dir": "dst/", "success": True}
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.move_dir("src/", "dst/")
        runner.run_json.assert_called_once()
        self.assertTrue(result["success"])

    def test_bridge_batch_move_uses_own_runner(self):
        payload = {
            "operation_id": "op-001",
            "total_items": 1,
            "success_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [{"source": "a.mp4", "destination": "dst/a.mp4", "success": True}],
            "status": "completed",
            "summary": "完成",
            "duration": "0.1s",
        }
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.batch_move([{"source": "a.mp4", "destination": "dst/a.mp4"}])
        runner.run.assert_called_once()
        self.assertEqual(result.success_count, 1)

    def test_bridge_list_operations_uses_own_runner(self):
        payload = [
            {
                "id": "op-001",
                "timestamp": "2026-04-01T10:00:00Z",
                "type": "batch_move",
                "status": "completed",
                "items": [],
            }
        ]
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        results = bridge.list_operations()
        runner.run_json.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "op-001")

    def test_bridge_get_operation_uses_own_runner(self):
        payload = {
            "id": "op-abc",
            "timestamp": "2026-04-01T10:00:00Z",
            "type": "batch_move",
            "status": "completed",
            "items": [],
        }
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.get_operation("op-abc")
        runner.run_json.assert_called_once()
        self.assertEqual(result.id, "op-abc")

    def test_bridge_rollback_uses_own_runner(self):
        payload = {
            "operation_id": "op-001",
            "total_items": 1,
            "success_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
            "status": "rolled_back",
            "summary": "回滾完成",
            "duration": "0.1s",
        }
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.rollback("op-001")
        runner.run.assert_called_once()
        self.assertEqual(result.status, "rolled_back")

    def test_bridge_rollback_last_uses_own_runner(self):
        payload = {
            "operation_id": "op-last",
            "total_items": 1,
            "success_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "results": [],
            "status": "rolled_back",
            "summary": "回滾完成",
            "duration": "0.1s",
        }
        runner = _make_runner(stdout=json.dumps(payload))
        bridge = self._make_bridge(runner)
        result = bridge.rollback_last()
        runner.run.assert_called_once()
        args = runner.run.call_args[0][0]
        self.assertIn("--last", args)
        self.assertEqual(result.status, "rolled_back")


if __name__ == "__main__":
    unittest.main()
