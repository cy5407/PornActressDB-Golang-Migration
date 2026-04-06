import json

import pytest

from src.services.go_runner import GoBridgeError


class TestDbCLI:
    """db 子命令 e2e 測試。"""

    def test_db_update_and_get(self, runner, temp_data_dir):
        """update → get 應能取回相同資料。"""
        code = "TEST-001"
        payload_file = f"{temp_data_dir}/video.json"
        with open(payload_file, "w", encoding="utf-8") as f:
            json.dump({"title": "測試影片", "actresses": ["測試女優"]}, f, ensure_ascii=False)

        result = runner.run(
            ["db", "update", "-data-dir", temp_data_dir, code, payload_file]
        )
        assert result.returncode == 0

        video = runner.run_json(["db", "get", "-data-dir", temp_data_dir, code])
        assert video["code"] == code
        assert video["title"] == "測試影片"

    def test_db_delete(self, runner, temp_data_dir):
        """新增後 delete，再 get 應回傳 not_found。"""
        code = "TEST-DEL"
        payload_file = f"{temp_data_dir}/video-delete.json"
        with open(payload_file, "w", encoding="utf-8") as f:
            json.dump({"title": "待刪"}, f, ensure_ascii=False)

        assert runner.run(["db", "update", "-data-dir", temp_data_dir, code, payload_file]).returncode == 0

        assert runner.run(["db", "delete", "-data-dir", temp_data_dir, code]).returncode == 0

        with pytest.raises(GoBridgeError):
            runner.run_json(["db", "get", "-data-dir", temp_data_dir, code])

    def test_db_list(self, runner, temp_data_dir):
        """list 應回傳 array。"""
        result = runner.run_json(["db", "list", "-data-dir", temp_data_dir])
        assert isinstance(result, list)

    def test_db_stats(self, runner, temp_data_dir):
        """stats 應包含 total 欄位。"""
        result = runner.run_json(["db", "stats", "-data-dir", temp_data_dir, "-json"])
        assert "total_videos" in result

    def test_db_backup_create_and_list(self, runner, temp_data_dir):
        """backup-create 後，backup-list 應至少有 1 筆。"""
        runner.run_json(["db", "backup-create", "-data-dir", temp_data_dir, "-json"])
        backups = runner.run_json(["db", "backup-list", "-data-dir", temp_data_dir, "-json"])
        assert isinstance(backups, dict)
        assert backups["count"] >= 1


class TestCacheCLI:
    """cache 子命令 e2e 測試。"""

    def test_cache_stats(self, runner, tmp_path):
        cache_dir = str(tmp_path / "cache")
        result = runner.run_json(["cache", "stats", "-cache-dir", cache_dir])
        assert result["total_files"] == 0

    def test_cache_prune_dry_run(self, runner, tmp_path):
        cache_dir = str(tmp_path / "cache")
        result = runner.run(["cache", "prune", "-cache-dir", cache_dir, "-dry-run"])
        assert result.returncode == 0

    def test_cache_clear_dry_run(self, runner, tmp_path):
        cache_dir = str(tmp_path / "cache")
        result = runner.run(["cache", "clear", "-cache-dir", cache_dir, "-dry-run"])
        assert result.returncode == 0


class TestIdentifyCLI:
    """identify 子命令 e2e 測試。"""

    def test_identify_known_code(self, runner):
        result = runner.run_json(["identify", "-json", "STARS-001"])
        assert result["code"] == "STARS-001"
        assert result["studio"] == "SOD"

    def test_identify_list(self, runner):
        result = runner.run_json(["identify", "-list", "-json"])
        assert isinstance(result, list)
        assert len(result) > 0


class TestScanCLI:
    """scan 子命令 e2e 測試。"""

    def test_scan_empty_dir(self, runner, tmp_path):
        result = runner.run_json(["scan", "-dir", str(tmp_path)])
        assert isinstance(result, list)
        assert result == []

    def test_scan_with_files(self, runner, tmp_path):
        (tmp_path / "STARS-707.mp4").write_text("fake")
        (tmp_path / "FC2-PPV-123456.mp4").write_text("fake")

        result = runner.run_json(["scan", "-dir", str(tmp_path)])
        codes = [f.get("code", "") for f in result]
        assert "STARS-707" in codes


class TestPythonBridgeE2E:
    """確認 Python bridge 能正確呼叫 Go CLI 並取得預期回傳。"""

    def test_go_bridge_is_available(self, go_exe):
        from src.services.go_bridge import GoBridge

        bridge = GoBridge(exe_path=go_exe)
        assert bridge.is_available is True

    def test_db_get_video_not_found_returns_none(self, go_exe, temp_data_dir):
        from src.services.go_api.db import db_get_video
        from src.services.go_runner import GoCommandRunner

        runner = GoCommandRunner(go_exe)
        result = db_get_video("NOTEXIST-999", data_dir=temp_data_dir, runner=runner)
        assert result is None

    def test_db_update_and_get_via_bridge(self, go_exe, temp_data_dir):
        from src.services.go_api.db import db_get_video, db_update_video
        from src.services.go_runner import GoCommandRunner

        runner = GoCommandRunner(go_exe)

        ok = db_update_video(
            "BRIDGE-001",
            {"title": "Bridge Test", "actresses": []},
            data_dir=temp_data_dir,
            runner=runner,
        )
        assert ok is True

        video = db_get_video("BRIDGE-001", data_dir=temp_data_dir, runner=runner)
        assert video is not None
        assert video["title"] == "Bridge Test"
