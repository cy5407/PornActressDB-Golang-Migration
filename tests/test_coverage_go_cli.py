"""
補充 go_cli.py 覆蓋率測試

策略：mock run() 控制所有下游路徑；用 patch 操控 exe 搜尋邏輯
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

import src.services.go_cli as go_cli_module
from src.services.go_cli import (
    GoError,
    GoNotFoundError,
    _find_exe_from_path,
    _find_exe_in_dir,
    _wsl_to_posix_path,
    batch_move,
    cache_clear,
    cache_delete,
    cache_get_stats,
    cache_prune,
    cache_set,
    db_backup_cleanup,
    db_backup_create,
    db_backup_list,
    db_backup_restore,
    db_compact_journal,
    db_delete_actress,
    db_delete_video,
    db_get_actress,
    db_get_all_videos,
    db_get_video,
    db_update_actress,
    list_operations,
    move_dir,
    move_file,
    rollback,
    rollback_last,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_run(return_value):
    return patch("src.services.go_cli.run", return_value=return_value)


def _mock_run_raise(exc):
    return patch("src.services.go_cli.run", side_effect=exc)


# ---------------------------------------------------------------------------
# _find_exe_in_dir / _find_exe_from_path（lines 36, 40-44）
# ---------------------------------------------------------------------------

class TestFindExePaths:
    def test_find_exe_in_dir_returns_none_when_no_exe(self, tmp_path):
        """當目錄中找不到執行檔時應回傳 None（line 36）"""
        result = _find_exe_in_dir(str(tmp_path))
        assert result is None

    def test_find_exe_in_dir_prefers_linux_binary_under_wsl(self, tmp_path):
        classifier = tmp_path / "classifier"
        classifier.write_text("", encoding="utf-8")
        classifier.chmod(0o755)

        windows_classifier = tmp_path / "classifier.exe"
        windows_classifier.write_text("", encoding="utf-8")
        windows_classifier.chmod(0o755)

        with patch("src.services.go_cli._running_under_wsl", return_value=True):
            result = _find_exe_in_dir(str(tmp_path))
        assert result == str(classifier)

    def test_find_exe_from_path_returns_none_when_not_in_path(self):
        """shutil.which 找不到時應回傳 None（lines 40-44）"""
        with patch("shutil.which", return_value=None):
            result = _find_exe_from_path()
        assert result is None

    def test_find_exe_from_path_returns_found(self):
        """shutil.which 找到時應回傳路徑"""
        with patch("shutil.which", return_value="/usr/local/bin/classifier.exe"):
            result = _find_exe_from_path()
        assert result == "/usr/local/bin/classifier.exe"


# ---------------------------------------------------------------------------
# _resolve_exe：cwd / PATH 搜尋路徑（lines 66-75）
# ---------------------------------------------------------------------------

class TestResolveExe:
    def _reset_exe_cache(self):
        go_cli_module._EXE_SEARCH_DONE = False
        go_cli_module._EXE_PATH = None

    def test_resolve_finds_exe_in_cwd(self, tmp_path):
        """在 cwd 中找到執行檔（line 66-68）"""
        self._reset_exe_cache()
        fake_exe = str(tmp_path / "classifier.exe")
        open(fake_exe, "w").close()

        with patch.dict("os.environ", {"CLASSIFIER_EXE": ""}, clear=False):
            with patch("src.services.go_cli._find_exe_in_dir") as mock_find:
                # 第一次（root）找不到，第二次（cwd）找到
                mock_find.side_effect = [None, fake_exe]
                with patch("os.getcwd", return_value=str(tmp_path)):
                    from src.services.go_cli import _resolve_exe
                    result = _resolve_exe()
        assert result == fake_exe
        self._reset_exe_cache()

    def test_resolve_falls_back_to_path(self, tmp_path):
        """root 和 cwd 都找不到時，退回 PATH 搜尋（lines 70-73）"""
        self._reset_exe_cache()
        with patch.dict("os.environ", {"CLASSIFIER_EXE": ""}, clear=False):
            with patch("src.services.go_cli._find_exe_in_dir", return_value=None):
                with patch("src.services.go_cli._find_exe_from_path", return_value="/bin/classifier"):
                    from src.services.go_cli import _resolve_exe
                    result = _resolve_exe()
        assert result == "/bin/classifier"
        self._reset_exe_cache()

    def test_resolve_returns_none_when_nothing_found(self):
        """全部找不到時應回傳 None"""
        self._reset_exe_cache()
        with patch.dict("os.environ", {"CLASSIFIER_EXE": ""}, clear=False):
            with patch("src.services.go_cli._find_exe_in_dir", return_value=None):
                with patch("src.services.go_cli._find_exe_from_path", return_value=None):
                    from src.services.go_cli import _resolve_exe
                    result = _resolve_exe()
        assert result is None
        self._reset_exe_cache()

    def test_resolve_prefers_classifier_env_var(self):
        self._reset_exe_cache()
        # 下行使用的 /tmp 路徑只是測試替身字串，整段以 patch 攔截系統呼叫，不會實際碰到檔案系統。
        env_classifier = "/tmp/classifier"  # nosec B108
        with patch.dict("os.environ", {"CLASSIFIER_EXE": env_classifier}, clear=False):
            with patch("src.services.go_cli._is_executable_file", side_effect=lambda path: path == env_classifier):
                from src.services.go_cli import _resolve_exe
                result = _resolve_exe()
        assert result == env_classifier
        self._reset_exe_cache()


class TestWslPathHelpers:
    def test_wsl_to_posix_path_returns_original_for_posix_path(self):
        with patch("src.services.go_cli._running_under_wsl", return_value=True):
            assert _wsl_to_posix_path("/mnt/c/Temp/demo.json") == "/mnt/c/Temp/demo.json"

    def test_wsl_to_posix_path_converts_windows_path(self):
        completed = subprocess.CompletedProcess(["wslpath", "-u", r"C:\\Temp\\demo.json"], 0, stdout="/mnt/c/Temp/demo.json\n", stderr="")
        with patch("src.services.go_cli._running_under_wsl", return_value=True):
            with patch("src.services.go_cli.subprocess.run", return_value=completed):
                assert _wsl_to_posix_path(r"C:\Temp\demo.json") == "/mnt/c/Temp/demo.json"

    def test_wsl_to_posix_path_returns_none_on_failed_conversion(self):
        completed = subprocess.CompletedProcess(["wslpath", "-u", r"C:\\Temp\\demo.json"], 1, stdout="", stderr="bad path")
        with patch("src.services.go_cli._running_under_wsl", return_value=True):
            with patch("src.services.go_cli.subprocess.run", return_value=completed):
                assert _wsl_to_posix_path(r"C:\Temp\demo.json") is None


# ---------------------------------------------------------------------------
# run()：GoNotFoundError / FileNotFoundError / TimeoutExpired（lines 103, 115）
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_raises_go_not_found_when_no_exe(self):
        """找不到執行檔時應拋出 GoNotFoundError（line 103）"""
        with patch("src.services.go_cli._resolve_exe", return_value=None):
            with pytest.raises(GoNotFoundError):
                run(["scan", "test.mp4"])

    def test_run_raises_go_not_found_on_file_not_found(self):
        """FileNotFoundError 應包裝成 GoNotFoundError（line 115）"""
        with patch("src.services.go_cli._resolve_exe", return_value="/fake/classifier.exe"):
            with patch("subprocess.run", side_effect=FileNotFoundError("no file")):
                with pytest.raises(GoNotFoundError):
                    run(["scan", "test.mp4"])

    def test_run_raises_go_error_on_timeout(self):
        """TimeoutExpired 應包裝成 GoError"""
        with patch("src.services.go_cli._resolve_exe", return_value="/fake/classifier.exe"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 30)):
                with pytest.raises(GoError):
                    run(["scan", "test.mp4"])

    def test_run_raises_go_error_on_nonzero_exit(self):
        """非零 exit code 應拋出 GoError"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        with patch("src.services.go_cli._resolve_exe", return_value="/fake/classifier.exe"):
            with patch("subprocess.run", return_value=mock_result):
                with pytest.raises(GoError):
                    run(["scan", "test.mp4"])


# ---------------------------------------------------------------------------
# db_get_video：GoError + raise 路徑（lines 179-180）
# ---------------------------------------------------------------------------

class TestDbGetVideo:
    def test_non_not_found_error_reraises(self):
        """非 'not found' GoError 應重新拋出（lines 179-180）"""
        with _mock_run_raise(GoError("connection error")):
            with pytest.raises(GoError):
                db_get_video("STARS-001")

    def test_not_found_error_returns_none(self):
        """'not found' GoError 應回傳 None"""
        with _mock_run_raise(GoError("item not found")):
            result = db_get_video("MISSING-001")
        assert result is None


# ---------------------------------------------------------------------------
# db_delete_video / db_get_all_videos / db_compact_journal（lines 216-218, 231-233, 244-246）
# ---------------------------------------------------------------------------

class TestDbBulkOps:
    def test_db_delete_video_not_found_returns_false(self):
        with _mock_run_raise(GoError("video not found")):
            assert db_delete_video("X-001") is False

    def test_db_delete_video_other_error_raises(self):
        with _mock_run_raise(GoError("delete failed")):
            with pytest.raises(GoError, match="delete failed"):
                db_delete_video("X-001")

    def test_db_get_all_videos_error_raises(self):
        with _mock_run_raise(GoError("list failed")):
            with pytest.raises(GoError, match="list failed"):
                db_get_all_videos()

    def test_db_get_all_videos_returns_list_directly(self):
        with _mock_run(["v1", "v2"]):
            result = db_get_all_videos()
        assert result == ["v1", "v2"]

    def test_db_compact_journal_error_returns_false(self):
        with _mock_run_raise(GoError("compact failed")):
            assert db_compact_journal() is False


# ---------------------------------------------------------------------------
# cache_set / cache_delete / cache_get_stats（lines 281-283, 291-293, 301-303）
# ---------------------------------------------------------------------------

class TestCacheFunctions:
    def test_cache_set_error_returns_false(self):
        with _mock_run_raise(GoError("cache error")):
            assert cache_set("key", b"value") is False

    def test_cache_delete_error_returns_false(self):
        with _mock_run_raise(GoError("delete error")):
            assert cache_delete("key") is False

    def test_cache_get_stats_error_returns_empty_dict(self):
        with _mock_run_raise(GoError("stats error")):
            assert cache_get_stats() == {}


# ---------------------------------------------------------------------------
# cache_prune / cache_clear（lines 314-328, 333-343）
# ---------------------------------------------------------------------------

class TestCachePruneClear:
    def test_cache_prune_dry_run_appends_flag(self):
        with _mock_run({"deleted": 5}):
            result = cache_prune(dry_run=True)
        assert result == {"deleted": 5}

    def test_cache_prune_error_returns_empty_dict(self):
        with _mock_run_raise(GoError("prune failed")):
            assert cache_prune() == {}

    def test_cache_clear_dry_run(self):
        with _mock_run({"deleted": 3}):
            result = cache_clear(dry_run=True)
        assert result == {"deleted": 3}

    def test_cache_clear_no_dry_run(self):
        with _mock_run({"deleted": 10}):
            result = cache_clear(dry_run=False)
        assert result == {"deleted": 10}

    def test_cache_clear_error_returns_empty_dict(self):
        with _mock_run_raise(GoError("clear failed")):
            assert cache_clear() == {}


# ---------------------------------------------------------------------------
# db_backup_create / db_backup_list / db_backup_restore / db_backup_cleanup
# （lines 353-355, 367-370, 379-381, 395-397）
# ---------------------------------------------------------------------------

class TestDbBackup:
    def test_db_backup_create_error_raises(self):
        with _mock_run_raise(GoError("backup failed")):
            with pytest.raises(GoError, match="backup failed"):
                db_backup_create()

    def test_db_backup_list_error_raises(self):
        with _mock_run_raise(GoError("list failed")):
            with pytest.raises(GoError, match="list failed"):
                db_backup_list()

    def test_db_backup_list_returns_backups_from_dict(self):
        with _mock_run({"backups": ["/path/a.json", "/path/b.json"]}):
            result = db_backup_list()
        assert result == ["/path/a.json", "/path/b.json"]

    def test_db_backup_list_returns_empty_when_backups_not_list(self):
        with _mock_run({"backups": None}):
            result = db_backup_list()
        assert result == []

    def test_db_backup_restore_error_returns_empty_dict(self):
        with _mock_run_raise(GoError("restore failed")):
            assert db_backup_restore("/path/backup.json") == {}

    def test_db_backup_cleanup_error_raises(self):
        with _mock_run_raise(GoError("cleanup failed")):
            with pytest.raises(GoError, match="cleanup failed"):
                db_backup_cleanup()


# ---------------------------------------------------------------------------
# db_get_actress / db_update_actress / db_delete_actress（lines 401-410, 414-432, 436-444）
# ---------------------------------------------------------------------------

class TestActressCRUD:
    def test_db_get_actress_success(self):
        with _mock_run({"id": "actress-1", "name": "Test"}):
            result = db_get_actress("actress-1")
        assert result["name"] == "Test"

    def test_db_get_actress_not_found_returns_none(self):
        with _mock_run_raise(GoError("not found")):
            result = db_get_actress("missing")
        assert result is None

    def test_db_get_actress_other_error_raises(self):
        with _mock_run_raise(GoError("connection error")):
            with pytest.raises(GoError, match="connection error"):
                db_get_actress("actress-1")

    def test_db_update_actress_success(self):
        with _mock_run({}):
            result = db_update_actress("actress-1", {"name": "Test"})
        assert result is True

    def test_db_update_actress_error_returns_false(self):
        with _mock_run_raise(GoError("update failed")):
            result = db_update_actress("actress-1", {"name": "Test"})
        assert result is False

    def test_db_delete_actress_success(self):
        with _mock_run({}):
            result = db_delete_actress("actress-1")
        assert result is True

    def test_db_delete_actress_not_found_returns_false(self):
        with _mock_run_raise(GoError("actress not found")):
            result = db_delete_actress("actress-1")
        assert result is False

    def test_db_delete_actress_other_error_raises(self):
        with _mock_run_raise(GoError("delete failed")):
            with pytest.raises(GoError, match="delete failed"):
                db_delete_actress("actress-1")


# ---------------------------------------------------------------------------
# move_file / move_dir（lines 464, 466-467, 477-486）
# ---------------------------------------------------------------------------

class TestMoveFunctions:
    def test_move_file_non_dict_result(self):
        """run() 回傳非 dict 時應回傳預設 dict（line 465）"""
        with _mock_run("ok"):
            result = move_file("/src/a.mp4", "/dst/a.mp4")
        assert result["success"] is True

    def test_move_file_error_returns_failure_dict(self):
        """GoError 應回傳帶 success=False 的 dict（lines 466-467）"""
        with _mock_run_raise(GoError("move failed")):
            result = move_file("/src/a.mp4", "/dst/a.mp4")
        assert result["success"] is False
        assert "move failed" in result["error"]

    def test_move_dir_success(self):
        with _mock_run({"success": True}):
            result = move_dir("/src", "/dst")
        assert result["success"] is True

    def test_move_dir_non_dict_result(self):
        with _mock_run("ok"):
            result = move_dir("/src", "/dst")
        assert result["success"] is True

    def test_move_dir_error_returns_failure(self):
        with _mock_run_raise(GoError("dir move failed")):
            result = move_dir("/src", "/dst")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# batch_move（lines 496-514）
# ---------------------------------------------------------------------------

class TestBatchMove:
    def test_batch_move_success(self):
        with _mock_run({"total": 2, "success": 2}):
            result = batch_move([
                {"source": "/s1.mp4", "destination": "/d1.mp4"},
                {"source": "/s2.mp4", "destination": "/d2.mp4"},
            ])
        assert result["success"] == 2

    def test_batch_move_non_dict_returns_default(self):
        with _mock_run("ok"):
            result = batch_move([{"source": "/s.mp4", "destination": "/d.mp4"}])
        assert result["failed"] == 1

    def test_batch_move_error(self):
        with _mock_run_raise(GoError("batch failed")):
            result = batch_move([{"source": "/s.mp4", "destination": "/d.mp4"}])
        assert result["success"] == 0
        assert "batch failed" in result["error"]


# ---------------------------------------------------------------------------
# rollback / rollback_last / list_operations（lines 521-528, 533-540, 547-555）
# ---------------------------------------------------------------------------

class TestHistoryFunctions:
    def test_rollback_success(self):
        with _mock_run({"success": True}):
            result = rollback("op-123")
        assert result["success"] is True

    def test_rollback_error_returns_failure(self):
        with _mock_run_raise(GoError("rollback failed")):
            result = rollback("op-123")
        assert result["success"] is False

    def test_rollback_last_success(self):
        with _mock_run({"success": True}):
            result = rollback_last()
        assert result["success"] is True

    def test_rollback_last_error_returns_failure(self):
        with _mock_run_raise(GoError("last rollback failed")):
            result = rollback_last()
        assert result["success"] is False

    def test_list_operations_success(self):
        with _mock_run([{"id": "op-1"}, {"id": "op-2"}]):
            result = list_operations()
        assert len(result) == 2

    def test_list_operations_error_returns_empty(self):
        with _mock_run_raise(GoError("list failed")):
            result = list_operations()
        assert result == []

    def test_list_operations_non_list_result(self):
        with _mock_run({"unexpected": "dict"}):
            result = list_operations()
        assert result == []


# ---------------------------------------------------------------------------
# 剩餘未覆蓋行：data_dir 參數 / move_file dict 回傳 / backup_list list 回傳
# ---------------------------------------------------------------------------

class TestRemainingLines:
    def test_db_backup_list_returns_list_directly(self):
        """run() 直接回傳 list 時應直接回傳（line 367）"""
        with _mock_run(["/path/a.json"]):
            result = db_backup_list()
        assert result == ["/path/a.json"]

    def test_db_backup_list_non_list_non_dict_returns_empty(self):
        """run() 回傳非 list 非 dict 時應回傳空 list"""
        with _mock_run("not_a_list"):
            result = db_backup_list()
        assert result == []

    def test_move_file_returns_dict_directly(self):
        """run() 回傳 dict 時直接回傳（line 464）"""
        expected = {"success": True, "source": "/s.mp4", "destination": "/d.mp4"}
        with _mock_run(expected):
            result = move_file("/s.mp4", "/d.mp4")
        assert result == expected

    def test_db_get_actress_with_custom_data_dir(self):
        """data_dir != 預設值時應加上 -data-dir 旗標（line 404）"""
        with _mock_run({"id": "a1"}) as mock:
            result = db_get_actress("a1", data_dir="custom/dir")
        assert result == {"id": "a1"}
        mock.assert_called_once_with(["db", "actress-get", "-data-dir", "custom/dir", "a1"])

    def test_db_update_actress_with_custom_data_dir(self):
        """data_dir != 預設值時應加上 -data-dir 旗標（line 424）"""
        with _mock_run({}) as mock:
            result = db_update_actress("a1", {"name": "Test"}, data_dir="custom/dir")
        assert result is True
        called_args = mock.call_args.args[0]
        assert called_args[:4] == ["db", "actress-update", "-data-dir", "custom/dir"]
        assert called_args[4] == "a1"
        assert called_args[5].endswith(".json")

    def test_db_delete_actress_with_custom_data_dir(self):
        """data_dir != 預設值時應加上 -data-dir 旗標（line 439）"""
        with _mock_run({}) as mock:
            result = db_delete_actress("a1", data_dir="custom/dir")
        assert result is True
        mock.assert_called_once_with(["db", "actress-delete", "-data-dir", "custom/dir", "a1"])
