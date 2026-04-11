import json
import subprocess
from pathlib import Path

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
    assert captured["args"] == ["db", "actress-get", "actress-1", "-data-dir", "custom_db"]


def test_db_update_actress_uses_actress_update_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_update_actress("actress-1", {"name": "測試女優"}, "custom_db")

    assert result is True
    assert captured["args"][0:3] == ["db", "actress-update", "actress-1"]
    assert captured["args"][4:] == ["-data-dir", "custom_db"]
    assert captured["args"][3].endswith(".json")


def test_db_delete_actress_uses_actress_delete_subcommand(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_delete_actress("actress-1", "custom_db")

    assert result is True
    assert captured["args"] == ["db", "actress-delete", "actress-1", "-data-dir", "custom_db"]


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


def test_extract_code_and_identify_studio_return_none_on_go_error(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failed")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.extract_code("bad-file.mp4") is None
    assert go_cli.identify_studio("BAD-001") is None
