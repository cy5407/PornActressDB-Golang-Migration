import json

import pytest

from src.services.go_runner import GoBridgeError


class TestDbCLI:
    """db 子命令 e2e 測試。"""

    def test_db_update_and_get(self, runner, temp_data_dir):
        """update → get 應能取回相同資料。"""
        code = "TEST-001"
        payload = json.dumps({"title": "測試影片", "actresses": ["測試女優"]})

        result = runner.run_json(
            [
                "db",
                "update",
                code,
                "-data",
                payload,
                "-data-dir",
                temp_data_dir,
            ]
        )
        assert result.get("success") is True, f"update 失敗: {result}"

        video = runner.run_json(["db", "get", code, "-data-dir", temp_data_dir])
        assert video["code"] == code
        assert video["title"] == "測試影片"

    def test_db_delete(self, runner, temp_data_dir):
        """新增後 delete，再 get 應回傳 not_found。"""
        code = "TEST-DEL"
        runner.run_json(
            [
                "db",
                "update",
                code,
                "-data",
                '{"title": "待刪"}',
                "-data-dir",
                temp_data_dir,
            ]
        )

        runner.run_json(["db", "delete", code, "-data-dir", temp_data_dir])

        with pytest.raises(GoBridgeError):
            runner.run_json(["db", "get", code, "-data-dir", temp_data_dir])

    def test_db_list(self, runner, temp_data_dir):
        """list 應回傳 array。"""
        result = runner.run_json(["db", "list", "-data-dir", temp_data_dir])
        assert isinstance(result, list)

    def test_db_stats(self, runner, temp_data_dir):
        """stats 應包含 total 欄位。"""
        result = runner.run_json(["db", "stats", "-data-dir", temp_data_dir])
        assert "total" in result

    def test_db_backup_create_and_list(self, runner, temp_data_dir):
        """backup-create 後，backup-list 應至少有 1 筆。"""
        runner.run_json(["db", "backup-create", "-data-dir", temp_data_dir])
        backups = runner.run_json(["db", "backup-list", "-data-dir", temp_data_dir])
        assert isinstance(backups, list)
        assert len(backups) >= 1
