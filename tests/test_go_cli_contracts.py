import json
import subprocess
from pathlib import Path

from src.services import go_cli


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
