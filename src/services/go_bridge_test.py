"""
Go 橋接層單元測試
"""

import json
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 將 src 加入路徑
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.go_bridge import (
    GoBridge,
    GoBridgeError,
    ScanResult,
    MoveResult,
    BatchMoveResult,
    get_bridge,
    scan_directory_go,
    move_file_go,
    db_update_video,
    db_delete_video,
    db_compact_journal,
    list_studios,
    get_studio_prefixes,
)


class TestGoBridgeFindExe(unittest.TestCase):
    """測試 exe 偵測"""
    
    def test_find_exe_in_project_root(self):
        """測試在專案根目錄找到 exe"""
        bridge = GoBridge()
        # 應該能找到 classifier.exe（如果存在）
        self.assertIsNotNone(bridge.exe_path)
    
    def test_custom_exe_path(self):
        """測試自訂 exe 路徑"""
        bridge = GoBridge(exe_path="/custom/path/classifier.exe")
        self.assertEqual(bridge.exe_path, "/custom/path/classifier.exe")


class TestGoBridgeAvailability(unittest.TestCase):
    """測試可用性檢查"""
    
    def test_is_available_with_real_exe(self):
        """測試真實 exe 的可用性"""
        bridge = GoBridge()
        # 這個測試依賴實際的 classifier.exe
        result = bridge.is_available
        # 不管結果如何，應該是 bool
        self.assertIsInstance(result, bool)
    
    @patch('subprocess.run')
    def test_is_available_exe_not_found(self, mock_run):
        """測試找不到 exe 的情況"""
        mock_run.side_effect = FileNotFoundError()
        bridge = GoBridge(exe_path="nonexistent.exe")
        bridge._available = None  # 重置快取
        self.assertFalse(bridge.is_available)


class TestGoBridgeScan(unittest.TestCase):
    """測試掃描功能"""
    
    @patch('subprocess.run')
    def test_scan_directory_success(self, mock_run):
        """測試掃描成功"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"path": "D:\\Videos\\SONE-123.mp4", "code": "SONE-123"},
                {"path": "D:\\Videos\\MIDV-456.mp4", "code": "MIDV-456"},
            ]),
            stderr="",
        )
        
        bridge = GoBridge()
        results = bridge.scan_directory("D:\\Videos")
        
        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], ScanResult)
        self.assertEqual(results[0].code, "SONE-123")
        self.assertEqual(results[1].code, "MIDV-456")
    
    @patch('subprocess.run')
    def test_scan_directory_empty(self, mock_run):
        """測試空目錄"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr="",
        )
        
        bridge = GoBridge()
        results = bridge.scan_directory("D:\\Empty")
        
        self.assertEqual(len(results), 0)
    
    @patch('subprocess.run')
    def test_scan_directory_with_workers(self, mock_run):
        """測試指定並發數"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr="",
        )
        
        bridge = GoBridge()
        bridge.scan_directory("D:\\Videos", workers=20)
        
        # 檢查命令參數
        call_args = mock_run.call_args[0][0]
        self.assertIn("-workers", call_args)
        self.assertIn("20", call_args)


class TestGoBridgeMove(unittest.TestCase):
    """測試移動功能"""
    
    @patch('subprocess.run')
    def test_move_file_success(self, mock_run):
        """測試移動成功"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source": "a.mp4",
                "destination": "dest/a.mp4",
                "success": True,
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        result = bridge.move_file("a.mp4", "dest/a.mp4")
        
        self.assertIsInstance(result, MoveResult)
        self.assertTrue(result.success)
        self.assertEqual(result.source, "a.mp4")
    
    @patch('subprocess.run')
    def test_move_file_not_exists(self, mock_run):
        """測試來源不存在"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source": "notexists.mp4",
                "destination": "dest/notexists.mp4",
                "success": False,
                "error": "來源檔案不存在",
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        result = bridge.move_file("notexists.mp4", "dest/notexists.mp4")
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "來源檔案不存在")
    
    @patch('subprocess.run')
    def test_move_file_skipped(self, mock_run):
        """測試跳過衝突"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source": "a.mp4",
                "destination": "dest/a.mp4",
                "success": True,
                "skipped": True,
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        result = bridge.move_file("a.mp4", "dest/a.mp4", strategy="skip")
        
        self.assertTrue(result.success)
        self.assertTrue(result.skipped)
    
    @patch('subprocess.run')
    def test_move_file_dry_run(self, mock_run):
        """測試模擬執行"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source": "a.mp4",
                "destination": "dest/a.mp4",
                "success": True,
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        bridge.move_file("a.mp4", "dest/a.mp4", dry_run=True)
        
        # 檢查命令參數包含 -dry-run
        call_args = mock_run.call_args[0][0]
        self.assertIn("-dry-run", call_args)


class TestGoBridgeBatchMove(unittest.TestCase):
    """測試批次移動"""
    
    @patch('subprocess.run')
    def test_batch_move_success(self, mock_run):
        """測試批次移動成功"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "total_items": 3,
                "success_count": 3,
                "failed_count": 0,
                "skipped_count": 0,
                "results": [
                    {"source": "a.mp4", "destination": "dest/a.mp4", "success": True},
                    {"source": "b.mp4", "destination": "dest/b.mp4", "success": True},
                    {"source": "c.mp4", "destination": "dest/c.mp4", "success": True},
                ],
                "duration": "100ms",
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        items = [
            {"source": "a.mp4", "destination": "dest/a.mp4"},
            {"source": "b.mp4", "destination": "dest/b.mp4"},
            {"source": "c.mp4", "destination": "dest/c.mp4"},
        ]
        result = bridge.batch_move(items)
        
        self.assertIsInstance(result, BatchMoveResult)
        self.assertEqual(result.total_items, 3)
        self.assertEqual(result.success_count, 3)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), 3)
    
    @patch('subprocess.run')
    def test_batch_move_partial_failure(self, mock_run):
        """測試批次移動部分失敗"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "total_items": 2,
                "success_count": 1,
                "failed_count": 1,
                "skipped_count": 0,
                "results": [
                    {"source": "a.mp4", "destination": "dest/a.mp4", "success": True},
                    {"source": "b.mp4", "destination": "dest/b.mp4", "success": False, "error": "來源檔案不存在"},
                ],
                "duration": "50ms",
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        items = [
            {"source": "a.mp4", "destination": "dest/a.mp4"},
            {"source": "b.mp4", "destination": "dest/b.mp4"},
        ]
        result = bridge.batch_move(items)
        
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failed_count, 1)

    @patch('services.go_bridge.os.unlink', side_effect=PermissionError("locked"))
    @patch('services.go_bridge.tempfile.NamedTemporaryFile')
    @patch('subprocess.run')
    def test_batch_move_cleanup_failure_does_not_override_result(
        self, mock_run, mock_tempfile, mock_unlink
    ):
        """測試暫存檔清理失敗不會覆蓋批次移動結果"""
        class FakeNamedTemporaryFile(io.StringIO):
            def __init__(self, name: str):
                super().__init__()
                self.name = name

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.close()
                return False

        mock_tempfile.return_value = FakeNamedTemporaryFile("batch-move-test.json")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "total_items": 1,
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "results": [
                    {"source": "a.mp4", "destination": "dest/a.mp4", "success": True},
                ],
                "duration": "10ms",
            }),
            stderr="",
        )

        bridge = GoBridge()
        result = bridge.batch_move([{"source": "a.mp4", "destination": "dest/a.mp4"}])

        self.assertEqual(result.success_count, 1)
        mock_unlink.assert_called_once()


class TestGoBridgeHistory(unittest.TestCase):
    """測試操作歷史"""
    
    @patch('subprocess.run')
    def test_list_operations_empty(self, mock_run):
        """測試空操作歷史"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr="",
        )
        
        bridge = GoBridge()
        logs = bridge.list_operations()
        
        self.assertEqual(len(logs), 0)

    @patch('subprocess.run')
    def test_list_operations_rejects_legacy_table_stdout(self, mock_run):
        """測試舊表格輸出不再被 bridge 吞掉，而是回傳空列表"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ID 時間 類型 狀態\n----\nabc123 2026-03-10 13:00:00 batch_move completed",
            stderr="",
        )

        bridge = GoBridge()
        logs = bridge.list_operations()

        self.assertEqual(logs, [])
    
    @patch('subprocess.run')
    def test_rollback(self, mock_run):
        """測試回滾"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "total_items": 1,
                "success_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
                "results": [
                    {"source": "dest/a.mp4", "destination": "a.mp4", "success": True},
                ],
                "duration": "10ms",
            }),
            stderr="",
        )
        
        bridge = GoBridge()
        result = bridge.rollback("abc123")
        
        self.assertIsInstance(result, BatchMoveResult)
        self.assertEqual(result.success_count, 1)

    @patch('subprocess.run')
    def test_rollback_rejects_mixed_stdout(self, mock_run):
        """測試回滾輸出若混入文字會視為契約違反"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='✅ 回滾完成: 成功 1, 失敗 0\n{"success_count": 1}',
            stderr="",
        )

        bridge = GoBridge()
        with self.assertRaises(GoBridgeError):
            bridge.rollback("abc123")

    @patch('subprocess.run')
    def test_move_dir_success(self, mock_run):
        """測試目錄移動走 CLI 的 dir 契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source_dir": "src",
                "dest_dir": "dst",
                "files_moved": 2,
                "files_total": 2,
                "success": True,
                "deleted_src": True,
            }),
            stderr="",
        )

        bridge = GoBridge()
        result = bridge.move_dir("src", "dst")

        self.assertTrue(result["success"])
        self.assertEqual(result["files_moved"], 2)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-kind", call_args)
        self.assertIn("dir", call_args)

    @patch('subprocess.run')
    def test_get_operation_normalizes_legacy_move_batch_type(self, mock_run):
        """測試舊 move_batch 日誌會被正規化為 batch_move"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "id": "abc123",
                "timestamp": "2026-03-10T13:00:00Z",
                "type": "move_batch",
                "status": "completed",
                "items": [],
            }),
            stderr="",
        )

        bridge = GoBridge()
        log = bridge.get_operation("abc123")

        self.assertIsNotNone(log)
        self.assertEqual(log.type, "batch_move")


class TestConvenienceFunctions(unittest.TestCase):
    """測試便捷函式"""
    
    def test_get_bridge_singleton(self):
        """測試單例模式"""
        bridge1 = get_bridge()
        bridge2 = get_bridge()
        self.assertIs(bridge1, bridge2)
    
    @patch('subprocess.run')
    def test_scan_directory_go(self, mock_run):
        """測試便捷掃描函式"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"path": "D:\\Videos\\SONE-123.mp4", "code": "SONE-123"},
            ]),
            stderr="",
        )
        
        results = scan_directory_go("D:\\Videos")
        
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["code"], "SONE-123")
    
    @patch('subprocess.run')
    def test_move_file_go(self, mock_run):
        """測試便捷移動函式"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "source": "a.mp4",
                "destination": "dest/a.mp4",
                "success": True,
            }),
            stderr="",
        )
        
        result = move_file_go("a.mp4", "dest/a.mp4")
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result["success"])


class TestGoBridgeDatabaseAndStudioHelpers(unittest.TestCase):
    """測試會建立暫存檔的便捷 helper"""

    @patch('subprocess.run')
    def test_db_update_video_uses_json_contract(self, mock_run):
        """測試 db update 走 JSON 成功契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "action": "update",
                "code": "SSIS-001",
                "data_dir": "data/json_db",
            }),
            stderr="",
        )

        result = db_update_video("SSIS-001", {"code": "SSIS-001"})

        self.assertTrue(result)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-json", call_args)

    @patch('subprocess.run')
    def test_db_delete_video_uses_json_contract(self, mock_run):
        """測試 db delete 走 JSON 成功契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "action": "delete",
                "code": "SSIS-001",
                "data_dir": "data/json_db",
            }),
            stderr="",
        )

        result = db_delete_video("SSIS-001")

        self.assertTrue(result)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-json", call_args)

    @patch('subprocess.run')
    def test_db_compact_journal_uses_json_contract(self, mock_run):
        """測試 db compact 走 JSON 成功契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "action": "compact",
                "data_dir": "data/json_db",
            }),
            stderr="",
        )

        result = db_compact_journal()

        self.assertTrue(result)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-json", call_args)

    @patch('subprocess.run')
    def test_list_studios_uses_json_contract(self, mock_run):
        """測試列出片商改走 JSON 契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"studio": "S1", "is_major": True},
                {"studio": "MOODYZ", "is_major": True},
            ]),
            stderr="",
        )

        result = list_studios()

        self.assertEqual(result, ["S1", "MOODYZ"])
        call_args = mock_run.call_args[0][0]
        self.assertIn("-json", call_args)

    @patch('subprocess.run')
    def test_get_studio_prefixes_uses_json_contract(self, mock_run):
        """測試片商前綴查詢改走 JSON 契約"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "studio": "S1",
                "prefixes": ["SSIS", "SONE"],
            }),
            stderr="",
        )

        result = get_studio_prefixes("S1")

        self.assertEqual(result, ["SSIS", "SONE"])
        call_args = mock_run.call_args[0][0]
        self.assertIn("-json", call_args)

    @patch('services.go_bridge.os.unlink', side_effect=PermissionError("locked"))
    @patch('subprocess.run')
    def test_identify_studios_batch_cleanup_failure_does_not_return_empty(
        self, mock_run, mock_unlink
    ):
        """測試批次片商識別成功結果不會被清理失敗覆蓋"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{"code": "SSIS-001", "studio": "S1"}]),
            stderr="",
        )

        from services.go_bridge import identify_studios_batch

        result = identify_studios_batch(["SSIS-001"])

        self.assertEqual(result, [{"code": "SSIS-001", "studio": "S1"}])
        mock_unlink.assert_called_once()


class TestGoBridgeIntegration(unittest.TestCase):
    """整合測試（需要實際的 classifier.exe）"""
    
    @classmethod
    def setUpClass(cls):
        """檢查 classifier.exe 是否可用"""
        cls.bridge = GoBridge()
        cls.skip_integration = not cls.bridge.is_available
        if cls.skip_integration:
            print("⚠️ classifier.exe 不可用，跳過整合測試")
    
    def setUp(self):
        if self.skip_integration:
            self.skipTest("classifier.exe 不可用")
        
        # 建立暫時目錄
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_real_scan(self):
        """測試真實掃描"""
        # 建立測試檔案
        test_file = Path(self.temp_dir) / "SONE-123.mp4"
        test_file.write_text("test")
        
        results = self.bridge.scan_directory(self.temp_dir)
        
        # 應該找到一個檔案
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "SONE-123")
    
    def test_real_move(self):
        """測試真實移動"""
        # 建立測試檔案
        source = Path(self.temp_dir) / "source.txt"
        source.write_text("test content")
        dest = Path(self.temp_dir) / "dest" / "source.txt"
        
        result = self.bridge.move_file(str(source), str(dest))
        
        self.assertTrue(result.success)
        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())
    
    def test_real_history(self):
        """測試真實操作歷史"""
        logs = self.bridge.list_operations()
        
        # 應該返回列表（可能為空）
        self.assertIsInstance(logs, list)


if __name__ == "__main__":
    unittest.main()
