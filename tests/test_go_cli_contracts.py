import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.services import go_cli


def _patch_exe(monkeypatch, exe_path="classifier.exe"):
    monkeypatch.setattr(go_cli, "_resolve_exe", lambda exe_path=None: exe_path or "classifier.exe")


def test_db_compact_journal_uses_compact_json_command(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        captured["timeout"] = timeout
        return {"success": True, "action": "compact"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_compact_journal("custom_db")

    assert result is True
    assert captured["args"] == ["db", "compact", "-json", "-data-dir", "custom_db"]


def test_db_backup_restore_uses_backup_restore_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_restore("backup.json", "custom_db")

    assert result == {"success": True}
    assert captured["args"] == [
        "db",
        "backup-restore",
        "-backup-path",
        "backup.json",
        "-data-dir",
        "custom_db",
    ]


def test_db_backup_create_uses_backup_create_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True, "path": "backup/demo.json"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_create("custom_db")

    assert result == {"success": True, "path": "backup/demo.json"}
    assert captured["args"] == ["db", "backup-create", "-data-dir", "custom_db"]


def test_db_get_actress_uses_actress_get_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"id": "actress-1", "name": "測試女優"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_get_actress("actress-1", "custom_db")

    assert result == {"id": "actress-1", "name": "測試女優"}
    assert captured["args"] == ["db", "actress-get", "-data-dir", "custom_db", "actress-1"]


def test_db_update_actress_uses_actress_update_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_update_actress("actress-1", {"name": "測試女優"}, "custom_db")

    assert result is True
    assert captured["args"][0:4] == ["db", "actress-update", "-data-dir", "custom_db"]
    assert captured["args"][4] == "actress-1"
    assert captured["args"][5].endswith(".json")


def test_db_delete_actress_uses_actress_delete_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_delete_actress("actress-1", "custom_db")

    assert result is True
    assert captured["args"] == ["db", "actress-delete", "-data-dir", "custom_db", "actress-1"]


def test_db_backup_list_unwraps_backups_array(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"backups": ["a.json", "b.json"], "count": 2}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_list("custom_db")

    assert result == ["a.json", "b.json"]
    assert captured["args"] == ["db", "backup-list", "-data-dir", "custom_db"]


def test_db_backup_cleanup_returns_deleted_count(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"deleted": 3, "success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_cleanup("custom_db", days=7, max_count=9)

    assert result == 3
    assert captured["args"] == [
        "db",
        "backup-cleanup",
        "-data-dir",
        "custom_db",
        "-days",
        "7",
        "-max-count",
        "9",
    ]


def test_run_uses_explicit_exe_path(monkeypatch):
    captured = {}
    explicit_exe_path = r"C:\custom\classifier.exe"

    monkeypatch.setattr(go_cli, "_EXE_PATH", None)
    monkeypatch.setattr(go_cli, "_EXE_SEARCH_DONE", False)
    monkeypatch.setattr(go_cli.os.path, "isfile", lambda path: path == explicit_exe_path)
    monkeypatch.setattr(go_cli.os, "access", lambda path, mode: path == explicit_exe_path)

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["help"], exe_path=explicit_exe_path)

    assert result == {"success": True}
    assert captured["cmd"][0] == explicit_exe_path


def test_run_raises_go_error_on_timeout(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    try:
        go_cli.run(["db", "list"], timeout=7)
        assert False, "expected GoError"
    except go_cli.GoError as exc:
        assert "執行逾時" in str(exc)
        assert "7" in str(exc)
        assert "db" in str(exc)


def test_run_raises_go_error_on_invalid_json(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not-json", stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    try:
        go_cli.run(["cache", "stats"])
        assert False, "expected GoError"
    except go_cli.GoError as exc:
        assert "JSON 解析失敗" in str(exc)
        assert "not-json" in str(exc)


def test_cache_get_decodes_base64_value(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"success": true, "value": "aGVsbG8="}',
            stderr="",
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.cache_get("demo-key") == b"hello"


def test_cache_get_returns_none_for_missing_or_invalid_value(monkeypatch):
    _patch_exe(monkeypatch)
    payloads = iter(
        [
            '{"success": false}',
            '{"success": true, "value": null}',
            '{"success": true, "value": "a"}',
        ]
    )

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=next(payloads), stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.cache_get("demo-key") is None
    assert go_cli.cache_get("demo-key") is None
    assert go_cli.cache_get("demo-key") is None


def test_db_update_video_writes_temp_json_and_cleans_up(monkeypatch):
    _patch_exe(monkeypatch)
    captured = {}

    def fake_subprocess_run(cmd, **kwargs):
        temp_path = Path(cmd[-1])
        captured["cmd"] = cmd
        captured["payload"] = json.loads(temp_path.read_text(encoding="utf-8"))
        captured["temp_path"] = temp_path
        assert temp_path.exists()
        return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr(go_cli, "_to_windows_cli_path", lambda path: path)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    video = {"code": "MIDV-567", "title": "作品標題"}
    result = go_cli.db_update_video("MIDV-567", video, data_dir="custom_db")

    assert result is True
    assert captured["payload"] == video
    assert captured["cmd"][:4] == ["classifier.exe", "db", "update", "-data-dir"]
    assert captured["cmd"][4] == "custom_db"
    assert captured["cmd"][5] == "MIDV-567"
    assert not captured["temp_path"].exists()


def test_db_update_video_still_cleans_temp_file_on_go_error(monkeypatch):
    _patch_exe(monkeypatch)
    captured = {}

    def fake_subprocess_run(cmd, **kwargs):
        temp_path = Path(cmd[-1])
        captured["temp_path"] = temp_path
        assert temp_path.exists()
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.db_update_video("MIDV-567", {"title": "失敗案例"})

    assert result is False
    assert not captured["temp_path"].exists()


@pytest.mark.skip(reason="WSL 專屬測試，純 Linux 環境不適用")
def test_db_update_video_uses_windows_accessible_temp_file_when_running_wsl(monkeypatch):
    _patch_exe(monkeypatch)
    captured = {}

    windows_temp_dir = Path("/mnt/c/Users/cy5407/AppData/Local/Temp")
    converted_temp_file = r"C:\Users\cy5407\AppData\Local\Temp\tmp-test.json"
    real_named_temporary_file = tempfile.NamedTemporaryFile

    def fake_named_temporary_file(*args, **kwargs):
        assert kwargs["dir"] == str(windows_temp_dir)
        return real_named_temporary_file(*args, **kwargs)

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr(go_cli, "_running_under_wsl", lambda: True)
    monkeypatch.setattr(go_cli, "_windows_temp_dir", lambda: str(windows_temp_dir))
    monkeypatch.setattr(go_cli, "_to_windows_cli_path", lambda _path: converted_temp_file)
    monkeypatch.setattr(go_cli.tempfile, "NamedTemporaryFile", fake_named_temporary_file)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.db_update_video("MIDV-567", {"title": "可寫入案例"})

    assert result is True
    assert captured["cmd"][-1] == converted_temp_file


def test_db_update_video_keeps_posix_temp_file_when_running_wsl_with_linux_classifier(monkeypatch):
    captured = {}
    real_named_temporary_file = tempfile.NamedTemporaryFile

    def fake_named_temporary_file(*args, **kwargs):
        captured["temp_dir"] = kwargs.get("dir")
        return real_named_temporary_file(*args, **kwargs)

    def fake_subprocess_run(cmd, **kwargs):
        if cmd[0] == "wslpath":
            raise AssertionError("linux classifier 不應觸發 wslpath 轉換")
        temp_path = Path(cmd[-1])
        captured["cmd"] = cmd
        captured["temp_path"] = temp_path
        assert temp_path.exists()
        return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr(go_cli, "_running_under_wsl", lambda: True)
    monkeypatch.setattr(go_cli, "_resolve_exe", lambda exe_path=None: exe_path or "classifier")
    monkeypatch.setattr(go_cli, "_windows_temp_dir", lambda: "/mnt/c/Users/cy5407/AppData/Local/Temp")
    monkeypatch.setattr(go_cli.tempfile, "NamedTemporaryFile", fake_named_temporary_file)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.db_update_video("MIDV-567", {"title": "WSL native Linux classifier"})

    assert result is True
    assert captured["temp_dir"] is None
    assert str(captured["temp_path"]).startswith("/")
    assert captured["cmd"][-1] == str(captured["temp_path"])
    assert not captured["temp_path"].exists()


@pytest.mark.skip(reason="WSL 專屬測試，純 Linux 環境不適用")
def test_windows_temp_dir_converts_windows_localappdata_under_wsl(monkeypatch):
    monkeypatch.setattr(go_cli, "_running_under_wsl", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\cy5407\AppData\Local")
    monkeypatch.setattr(go_cli, "_wsl_to_posix_path", lambda path: "/mnt/c/Users/cy5407/AppData/Local/Temp")

    assert go_cli._windows_temp_dir() == "/mnt/c/Users/cy5407/AppData/Local/Temp"


def test_db_get_all_videos_handles_list_and_missing_videos_key(monkeypatch):
    _patch_exe(monkeypatch)
    payloads = iter(
        [
            '[{"code": "A"}]',
            '{"status": "ok"}',
        ]
    )

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=next(payloads), stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_get_all_videos() == [{"code": "A"}]
    assert go_cli.db_get_all_videos() == []


def test_move_file_returns_default_result_when_cli_returns_non_dict(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout='"ok"', stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.move_file("source.mp4", "dest.mp4") == {
        "success": True,
        "source": "source.mp4",
        "destination": "dest.mp4",
        "error": None,
        "skipped": False,
        "renamed": None,
    }


def test_extract_code_and_identify_studio_raise_on_go_error(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failed")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    import pytest

    with pytest.raises(go_cli.GoError, match="failed"):
        go_cli.extract_code("bad-file.mp4")
    with pytest.raises(go_cli.GoError, match="failed"):
        go_cli.identify_studio("BAD-001")


def test_normalize_studio_name_uses_identify_normalize_contract(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30, exe_path=None):
        captured["args"] = args
        captured["timeout"] = timeout
        captured["exe_path"] = exe_path
        return {"studio": "MOODYZ"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.normalize_studio_name(
        "MOODYZ DIVA",
        video_code="SSIS-123",
        rules_file="custom.json",
    )

    assert result == "MOODYZ"
    assert captured["args"] == [
        "identify",
        "-normalize",
        "-studio",
        "MOODYZ DIVA",
        "-code",
        "SSIS-123",
        "-rules",
        "custom.json",
    ]


def test_normalize_studio_name_raises_on_go_error(monkeypatch):
    def fake_run(args, *, timeout=30, exe_path=None):
        raise go_cli.GoError("normalize failed")

    monkeypatch.setattr(go_cli, "run", fake_run)

    import pytest

    with pytest.raises(go_cli.GoError, match="normalize failed"):
        go_cli.normalize_studio_name("MOODYZ DIVA")
