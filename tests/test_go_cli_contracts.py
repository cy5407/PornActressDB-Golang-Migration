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
    assert captured["cmd"][-1] == str(captured["temp_path"])
    assert not captured["temp_path"].exists()


def test_run_prefers_classifier_env_var(monkeypatch):
    env_classifier = r"C:\env\classifier.exe"
    captured = {}

    monkeypatch.setattr(go_cli, "_EXE_PATH", None)
    monkeypatch.setattr(go_cli, "_EXE_SEARCH_DONE", False)
    monkeypatch.setenv("CLASSIFIER_EXE", env_classifier)
    monkeypatch.setattr(go_cli, "_normalize_explicit_exe_path", lambda path: path)
    monkeypatch.setattr(go_cli, "_is_executable_file", lambda path: path == env_classifier)

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["help"])

    assert result == {"success": True}
    assert captured["cmd"][0] == env_classifier


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


# ---------------------------------------------------------------------------
# Slice A0 — per-subcommand happy-path JSON contracts (spec § 7.1)
#
# Goal: pin the JSON shape that classifier.exe currently returns for every
# `db` subcommand the Python helper relies on, so any later slice that
# changes that shape lights up here first.
# ---------------------------------------------------------------------------


def test_db_get_video_returns_video_dict_for_existing_code(monkeypatch):
    captured = {}
    video_payload = {
        "code": "STARS-707",
        "title": "範例作品",
        "studio": "SOD Create",
        "actresses": ["田中美奈実"],
        "search_status": "success",
    }

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return video_payload

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_get_video("STARS-707", "custom_db")

    assert result == video_payload
    assert captured["args"] == ["db", "get", "-data-dir", "custom_db", "STARS-707"]


def test_db_get_video_omits_data_dir_when_default(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"code": "STARS-707"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.db_get_video("STARS-707")

    # spec § 7.1: default data/json_db must NOT add -data-dir to argv
    # (compatibility lookup is implicit when the flag is absent).
    assert captured["args"] == ["db", "get", "STARS-707"]
    assert "-data-dir" not in captured["args"]


def test_db_get_video_returns_none_when_not_found(monkeypatch):
    def fake_run(args, *, timeout=30):
        raise go_cli.GoError("classifier 回傳錯誤 (exit 1): video not found")

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_get_video("MISSING-001", "custom_db") is None


def test_db_delete_video_happy_path(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True, "action": "delete", "code": "STARS-707"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_delete_video("STARS-707", "custom_db") is True
    assert captured["args"] == ["db", "delete", "-data-dir", "custom_db", "STARS-707"]


def test_db_delete_video_returns_false_on_not_found(monkeypatch):
    def fake_run(args, *, timeout=30):
        raise go_cli.GoError("classifier 回傳錯誤 (exit 1): video not found")

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_delete_video("MISSING-001", "custom_db") is False


def test_db_get_all_videos_full_uses_full_flag(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return [{"code": "STARS-707"}, {"code": "MIDV-567"}]

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_get_all_videos("custom_db")

    assert result == [{"code": "STARS-707"}, {"code": "MIDV-567"}]
    assert captured["args"] == ["db", "list", "--full", "-data-dir", "custom_db"]


def test_db_compact_journal_pins_current_return_shape(monkeypatch):
    """Lock the *current* `db compact -json` return shape.

    Spec § 7.1 / plan A0 describe a richer no-op return for Phase C
    (`{"success":true,"noop":true,"journal_size":0,"needs_compact":false,
    "reason":"..."}`), but today the CLI only emits success/action/data_dir.
    This test pins reality so Slice C1 can detect the contract change.
    The Python helper only reads `success`, so the wrapper must keep
    working when extra fields are added later.
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {
            "success": True,
            "action": "compact",
            "data_dir": "custom_db",
        }

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_compact_journal("custom_db") is True
    assert captured["args"] == ["db", "compact", "-json", "-data-dir", "custom_db"]


def test_db_compact_journal_accepts_phase_c_noop_shape(monkeypatch):
    """Forward-compat: Python wrapper must not break when Phase C adds fields.

    spec § 7.1: Phase C no-op returns the keys
    `success / noop / journal_size / needs_compact / reason`. The wrapper
    today only reads `success`, so it must keep returning True for the
    richer shape too.
    """

    def fake_run(args, *, timeout=30):
        return {
            "success": True,
            "noop": True,
            "journal_size": 0,
            "needs_compact": False,
            "reason": "sqlite has no journal to compact",
        }

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_compact_journal() is True


def test_db_compact_journal_omits_data_dir_when_default(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.db_compact_journal()

    assert captured["args"] == ["db", "compact", "-json"]


def test_db_stats_subcommand_returns_full_stats_dict(monkeypatch):
    """`db stats` is invoked directly via go_cli.run (no helper today).

    Pins the full key set that pkg/database.GetStats() emits, so any
    Phase B/C change to those keys is caught here.
    """
    _patch_exe(monkeypatch)
    stats_payload = {
        "video_count": 3,
        "actress_count": 3,
        "link_count": 4,
        "schema_version": "1.0.0",
        "created_at": "2026-05-23T00:00:00Z",
        "updated_at": "2026-05-23T00:00:00Z",
        "journal_size": 0,
        "journal_age_seconds": 0.0,
        "dirty_videos": 0,
        "dirty_actresses": 0,
        "dirty_links": 0,
        "needs_compact": False,
        "total_videos": 3,
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(stats_payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "stats", "-data-dir", "custom_db"])

    # Spec § 7.1: these are the fields Python IncrementalJSONDB mirrors.
    for required in (
        "journal_size",
        "journal_age_seconds",
        "dirty_videos",
        "dirty_actresses",
        "dirty_links",
        "needs_compact",
        "total_videos",
    ):
        assert required in result, f"missing required stats key: {required}"
    assert result["total_videos"] == 3
    assert result["needs_compact"] is False


def test_db_list_codes_returns_string_array(monkeypatch):
    """`db list` (without --full) emits a JSON string array, not an object."""
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout='["STARS-707","MIDV-567","SSIS-001"]', stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "list", "-data-dir", "custom_db"])

    assert isinstance(result, list)
    assert result == ["STARS-707", "MIDV-567", "SSIS-001"]


def test_db_actress_get_returns_actress_dict(monkeypatch):
    captured = {}
    actress_payload = {
        "id": "tanaka-minami",
        "name": "田中美奈実",
        "aliases": ["田中みなみ"],
        "video_count": 2,
        "created_at": "2026-05-20T08:00:00Z",
        "updated_at": "2026-05-22T13:00:00Z",
    }

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return actress_payload

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_get_actress("tanaka-minami", "custom_db")

    assert result == actress_payload
    # spec § 7.1: actress dict must expose id/name/aliases/video_count.
    for required in ("id", "name", "aliases", "video_count"):
        assert required in result
    assert captured["args"] == [
        "db",
        "actress-get",
        "-data-dir",
        "custom_db",
        "tanaka-minami",
    ]


def test_db_actress_list_returns_id_array(monkeypatch):
    _patch_exe(monkeypatch)

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='["tanaka-minami","sato-ami","suzuki-hanako"]',
            stderr="",
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "actress-list", "-data-dir", "custom_db"])

    assert isinstance(result, list)
    assert "tanaka-minami" in result


def test_db_clean_actresses_returns_report_dict(monkeypatch):
    """`db clean-actresses` emits a dbCleanActressesResult JSON object."""
    _patch_exe(monkeypatch)
    payload = {
        "success": True,
        "dry_run": True,
        "scanned_videos": 3,
        "changed_videos": 0,
        "removed_actresses": 0,
        "changes": [],
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "clean-actresses", "-data-dir", "custom_db"])

    for required in (
        "success",
        "dry_run",
        "scanned_videos",
        "changed_videos",
        "removed_actresses",
        "changes",
    ):
        assert required in result, f"missing required key: {required}"
    assert result["changes"] == []


def test_db_backup_create_returns_path_field_today(monkeypatch):
    """Pin the *current* backup-create return shape.

    spec § 7.1 / plan C1 call the field `backup_path` (and add
    `json_export_path` in Phase C); today the CLI emits `path` alongside
    `success`. The Python helper passes the dict through untouched, so
    this test locks the shape until Slice C1 promotes the field name.
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True, "path": "data/backup/db_demo.json"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_create("custom_db")

    assert result["success"] is True
    assert "path" in result
    assert captured["args"] == ["db", "backup-create", "-data-dir", "custom_db"]


def test_db_backup_list_returns_count_and_backups(monkeypatch):
    """`db backup-list` happy path returns {"backups": [...], "count": N}."""
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"backups": ["a.json", "b.json", "c.json"], "count": 3}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_list("custom_db")

    assert result == ["a.json", "b.json", "c.json"]
    assert captured["args"] == ["db", "backup-list", "-data-dir", "custom_db"]


def test_db_backup_list_handles_empty_backups(monkeypatch):
    def fake_run(args, *, timeout=30):
        return {"backups": [], "count": 0}

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_backup_list("custom_db") == []


def test_db_backup_cleanup_default_args_omit_optional_flags(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"deleted": 0, "success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_cleanup("custom_db")

    assert result == 0
    assert captured["args"] == ["db", "backup-cleanup", "-data-dir", "custom_db"]


def test_db_get_video_default_data_dir_lookup_contract(monkeypatch):
    """spec § 7.1: default `data/json_db` must trigger compatibility lookup.

    Today that means "do not append -data-dir to argv"; future slices may
    extend the contract (e.g. point at data/db.sqlite), but the Python
    surface must keep dispatching the flag the same way.
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"code": "STARS-707"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.db_get_video("STARS-707")  # uses default data_dir
    assert "-data-dir" not in captured["args"]

    captured.clear()
    go_cli.db_get_video("STARS-707", "data/json_db")  # explicit default
    assert "-data-dir" not in captured["args"]

    captured.clear()
    go_cli.db_get_video("STARS-707", "custom_dir")
    assert "-data-dir" in captured["args"]
    assert "custom_dir" in captured["args"]
