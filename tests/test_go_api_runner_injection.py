"""
測試 go_api db.py 與 identify.py 的 runner 注入機制。

驗證：
1. 所有公開函式都接受 runner 關鍵字參數
2. 注入的 runner 取代全域橋接層的 runner
3. runner 被呼叫時傳入正確的 CLI 參數
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.go_api.db import (
    db_compact_journal,
    db_delete_video,
    db_get_stats,
    db_get_video,
    db_list_videos,
    db_update_video,
)
from src.services.go_api.identify import (
    get_studio_prefixes,
    identify_studio,
    identify_studios_batch,
    list_studios,
)


def _mock_runner(stdout: str) -> MagicMock:
    """建立回傳固定 JSON stdout 的假 runner。"""
    runner = MagicMock()
    runner.run.return_value = SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    runner.parse_json.side_effect = json.loads
    return runner


# ---------------------------------------------------------------------------
# db.py runner injection tests
# ---------------------------------------------------------------------------


class TestDbRunnerInjection:
    """驗證 db.py 各函式接受並使用注入的 runner。"""

    def test_db_get_video_uses_injected_runner(self):
        payload = json.dumps({"code": "SONE-001", "title": "Test"})
        runner = _mock_runner(payload)

        result = db_get_video("SONE-001", runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "get" in call_args
        assert "SONE-001" in call_args
        assert result == {"code": "SONE-001", "title": "Test"}

    def test_db_get_video_returns_none_for_empty_stdout(self):
        runner = _mock_runner("")

        result = db_get_video("MISSING", runner=runner)

        assert result is None

    def test_db_get_video_returns_none_for_null(self):
        runner = _mock_runner("null")

        result = db_get_video("MISSING", runner=runner)

        assert result is None

    def test_db_get_video_passes_custom_data_dir(self):
        runner = _mock_runner(json.dumps({"code": "SONE-001"}))

        db_get_video("SONE-001", data_dir="/custom/path", runner=runner)

        call_args = runner.run.call_args[0][0]
        assert "-data-dir" in call_args
        assert "/custom/path" in call_args

    def test_db_get_video_omits_data_dir_for_default(self):
        runner = _mock_runner(json.dumps({"code": "SONE-001"}))

        db_get_video("SONE-001", runner=runner)

        call_args = runner.run.call_args[0][0]
        assert "-data-dir" not in call_args

    def test_db_update_video_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"success": True}))

        result = db_update_video("SONE-001", {"title": "New Title"}, runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "update" in call_args
        assert result is True

    def test_db_update_video_returns_false_on_failure(self):
        runner = _mock_runner(json.dumps({"success": False}))

        result = db_update_video("SONE-001", {"title": "New Title"}, runner=runner)

        assert result is False

    def test_db_delete_video_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"success": True}))

        result = db_delete_video("SONE-001", runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "delete" in call_args
        assert result is True

    def test_db_list_videos_uses_injected_runner(self):
        runner = _mock_runner(json.dumps(["SONE-001", "SSIS-123"]))

        result = db_list_videos(runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "list" in call_args
        assert result == ["SONE-001", "SSIS-123"]

    def test_db_list_videos_returns_empty_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = db_list_videos(runner=runner)

        assert result == []

    def test_db_get_stats_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"total_videos": 5}))

        result = db_get_stats(runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "stats" in call_args
        assert result == {"total_videos": 5}

    def test_db_get_stats_returns_empty_dict_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = db_get_stats(runner=runner)

        assert result == {}

    def test_db_compact_journal_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"success": True}))

        result = db_compact_journal(runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "db" in call_args
        assert "compact" in call_args
        assert result is True

    def test_db_compact_journal_returns_false_on_failure(self):
        runner = _mock_runner(json.dumps({"success": False}))

        result = db_compact_journal(runner=runner)

        assert result is False


# ---------------------------------------------------------------------------
# identify.py runner injection tests
# ---------------------------------------------------------------------------


class TestIdentifyRunnerInjection:
    """驗證 identify.py 各函式接受並使用注入的 runner。"""

    def test_identify_studio_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"code": "SONE-001", "studio": "S1"}))

        result = identify_studio("SONE-001", runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "identify" in call_args
        assert "SONE-001" in call_args
        assert result == {"code": "SONE-001", "studio": "S1"}

    def test_identify_studio_with_check_major_flag(self):
        runner = _mock_runner(json.dumps({"code": "SONE-001", "studio": "S1", "is_major": True}))

        identify_studio("SONE-001", check_major=True, runner=runner)

        call_args = runner.run.call_args[0][0]
        assert "-major" in call_args

    def test_identify_studio_returns_unknown_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = identify_studio("SONE-001", runner=runner)

        assert result["studio"] == "UNKNOWN"
        assert result["code"] == "SONE-001"

    def test_identify_studios_batch_uses_injected_runner(self):
        payload = json.dumps([
            {"code": "SONE-001", "studio": "S1"},
            {"code": "SSIS-123", "studio": "S1"},
        ])
        runner = _mock_runner(payload)

        result = identify_studios_batch(["SONE-001", "SSIS-123"], runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "identify" in call_args
        assert "-batch" in call_args
        assert len(result) == 2

    def test_identify_studios_batch_returns_empty_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = identify_studios_batch(["SONE-001"], runner=runner)

        assert result == []

    def test_list_studios_uses_injected_runner(self):
        runner = _mock_runner(json.dumps([{"studio": "S1"}, {"studio": "MOODYZ"}]))

        result = list_studios(runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "identify" in call_args
        assert "-list" in call_args
        assert result == ["S1", "MOODYZ"]

    def test_list_studios_filters_non_string_studio_values(self):
        runner = _mock_runner(json.dumps([
            {"studio": "S1"},
            {"studio": 42},
            {"studio": None},
            {"other": "field"},
        ]))

        result = list_studios(runner=runner)

        assert result == ["S1"]

    def test_list_studios_returns_empty_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = list_studios(runner=runner)

        assert result == []

    def test_get_studio_prefixes_uses_injected_runner(self):
        runner = _mock_runner(json.dumps({"studio": "S1", "prefixes": ["SONE", "STARS", "SSIS"]}))

        result = get_studio_prefixes("S1", runner=runner)

        runner.run.assert_called_once()
        call_args = runner.run.call_args[0][0]
        assert "identify" in call_args
        assert "-prefixes" in call_args
        assert "S1" in call_args
        assert result == ["SONE", "STARS", "SSIS"]

    def test_get_studio_prefixes_returns_empty_on_error(self):
        runner = MagicMock()
        runner.run.side_effect = Exception("CLI failed")

        result = get_studio_prefixes("S1", runner=runner)

        assert result == []

    def test_get_studio_prefixes_returns_empty_for_non_dict(self):
        runner = _mock_runner(json.dumps(["S1", "MOODYZ"]))

        result = get_studio_prefixes("S1", runner=runner)

        assert result == []
