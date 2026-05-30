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
    """Slice C1: `db backup-create` returns the dual-snapshot shape with
    both `backup_path` (SQLite) and `json_export_path` (JSON export).
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {
            "success": True,
            "backup_path": "data/backup/backup_2026-05-23.sqlite",
            "json_export_path": "data/backup/backup_2026-05-23.json",
        }

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_create("custom_db")

    assert result["success"] is True
    assert result["backup_path"].endswith(".sqlite")
    assert result["json_export_path"].endswith(".json")
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


def test_move_dir_uses_kind_dir_flag(monkeypatch):
    """move_dir 必須送 -kind dir（Go move 沒有 -dir flag）。"""
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return {"success": True, "source_dir": "A", "dest_dir": "B"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.move_dir("A", "B", "skip")

    assert result["success"] is True
    assert captured["args"] == [
        "move",
        "-src",
        "A",
        "-dst",
        "B",
        "-strategy",
        "skip",
        "-kind",
        "dir",
    ]


def test_move_dir_failure_shape_matches_success_keys(monkeypatch):
    """成功與失敗回傳的 key 集合一致（與 contracts.MergeResult 對齊）。"""

    def fake_run_raise(args, **kwargs):
        raise go_cli.GoError("dir move failed")

    monkeypatch.setattr(go_cli, "run", fake_run_raise)

    result = go_cli.move_dir("A", "B", "skip")

    assert result["success"] is False
    assert "dir move failed" in result["error"]
    for key in ("source_dir", "dest_dir", "files_moved", "files_skipped", "files_total"):
        assert key in result


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


# ---------------------------------------------------------------------------
# Slice B2 — structured not-found signal (exit 3 + stdout JSON envelope)
#
# Lock both the primary signal (exit 3 carried on GoError.returncode) and
# the auxiliary signal (stdout JSON with error_kind=not_found), plus the
# legacy stderr-substring fallback that lets Python wrappers stay
# backward-compatible during a one-version rollout where classifier.exe
# might still exit 1 with the old "video not found" stderr string.
# ---------------------------------------------------------------------------


def test_db_get_video_missing_returns_exit_3_and_structured_json(monkeypatch):
    """Slice B2 primary signal: exit 3 + stdout JSON envelope makes the
    wrapper return None without depending on stderr wording."""
    captured = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd,
            3,
            stdout=json.dumps(
                {
                    "success": False,
                    "error_kind": "not_found",
                    "kind": "video",
                    "code": "MISSING-001",
                    "message": "video not found",
                }
            ),
            stderr="",  # stderr empty — signal lives in exit code + stdout
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_get_video("MISSING-001", "custom_db") is None
    assert "db" in captured["cmd"] and "get" in captured["cmd"]


def test_db_delete_video_missing_returns_exit_3(monkeypatch):
    """Slice B2: db_delete_video must return False on exit 3 — the
    structured not-found signal, no stderr inspection."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            3,
            stdout=json.dumps(
                {
                    "success": False,
                    "error_kind": "not_found",
                    "kind": "video",
                    "code": "MISSING-001",
                    "message": "video not found",
                }
            ),
            stderr="",
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_delete_video("MISSING-001", "custom_db") is False


def test_db_actress_get_missing_returns_exit_3(monkeypatch):
    """Slice B2: db_get_actress must return None on exit 3 with
    kind=actress payload."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            3,
            stdout=json.dumps(
                {
                    "success": False,
                    "error_kind": "not_found",
                    "kind": "actress",
                    "id": "ghost-actress",
                    "message": "actress not found",
                }
            ),
            stderr="",
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_get_actress("ghost-actress", "custom_db") is None


def test_db_actress_delete_missing_returns_exit_3(monkeypatch):
    """Slice B2: db_delete_actress must return False on exit 3."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            3,
            stdout=json.dumps(
                {
                    "success": False,
                    "error_kind": "not_found",
                    "kind": "actress",
                    "id": "ghost-actress",
                    "message": "actress not found",
                }
            ),
            stderr="",
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_delete_actress("ghost-actress", "custom_db") is False


def test_is_not_found_error_works_when_stderr_is_chinese(monkeypatch):
    """Slice B2 core DoD: change the Go stderr wording (English → Chinese,
    or any other rewording / emoji / translation) and the wrapper MUST
    still return None. The structured signal (exit 3 + stdout JSON) is
    what carries the meaning — stderr is purely human-readable."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            3,
            stdout=json.dumps(
                {
                    "success": False,
                    "error_kind": "not_found",
                    "kind": "video",
                    "code": "MISSING-001",
                }
            ),
            # Chinese stderr — would defeat any "not found" substring match
            # but the wrapper now reads exit code + stdout JSON instead.
            stderr="取得影片失敗: 找不到資料",
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_get_video("MISSING-001", "custom_db") is None


def test_is_not_found_error_fallback_to_legacy_stderr_string(monkeypatch):
    """Slice B2 one-version rollout: if Python ships before the new Go CLI
    is deployed, the wrapper must still recognise the legacy `exit 1 +
    stderr "video not found"` shape and return None — otherwise a
    half-rolled-out deploy starts raising GoError everywhere."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,  # legacy exit code
            stdout="",
            stderr="video not found",  # legacy English stderr
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    assert go_cli.db_get_video("MISSING-001", "custom_db") is None


def test_is_not_found_error_does_not_swallow_real_errors(monkeypatch):
    """Negative case: exit 1 with a non-"not found" stderr must still
    raise GoError, even with the new dual-signal logic. Otherwise
    SQLite connection failures would silently look like missing rows."""

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="無法載入資料庫: SQLite is locked",
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    with pytest.raises(go_cli.GoError, match="SQLite is locked"):
        go_cli.db_get_video("STARS-707", "custom_db")


def test_go_error_carries_returncode_and_stdout(monkeypatch):
    """Slice B2 wiring sanity: go_cli.run must surface returncode and
    stdout on GoError so _is_not_found_error can dispatch on them."""

    not_found_stdout = json.dumps(
        {"success": False, "error_kind": "not_found", "kind": "video"}
    )

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 3, stdout=not_found_stdout, stderr=""
        )

    _patch_exe(monkeypatch)
    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    with pytest.raises(go_cli.GoError) as ei:
        go_cli.run(["db", "get", "MISSING-001"])
    assert ei.value.returncode == 3
    assert ei.value.stdout == not_found_stdout
    # And the legacy str(exc) view still works for callers that grep it.
    assert "exit 3" in str(ei.value)


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


def test_db_compact_journal_noop_payload_fields_complete(monkeypatch):
    """Slice C1: the Go-emitted no-op JSON must carry every key Python
    consumers may sample. IncrementalJSONDB.compact() only inspects
    `success` today, but spec § 7.1 promises the full set so future
    callers (and operators reading the CLI manually) can rely on it.
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {
            "success": True,
            "noop": True,
            "journal_size": 0,
            "needs_compact": False,
            "reason": "sqlite has no journal to compact",
            "action": "compact",
            "data_dir": "custom_db",
        }

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.db_compact_journal("custom_db") is True
    # The wrapper sends -json; pin that so Go-side flag plumbing changes
    # surface in this test.
    assert captured["args"] == ["db", "compact", "-json", "-data-dir", "custom_db"]


def test_db_compact_journal_noop_payload_round_trips_through_subprocess(monkeypatch):
    """Slice C1: the no-op payload — exactly as the Go CLI emits it —
    must round-trip through go_cli.run and reach Python wrapper code
    intact. Catches accidental field renames or json.dumps issues on
    the Go side at the contract boundary.
    """
    _patch_exe(monkeypatch)
    noop_payload = {
        "success": True,
        "noop": True,
        "journal_size": 0,
        "needs_compact": False,
        "reason": "sqlite has no journal to compact",
        "action": "compact",
        "data_dir": "custom_db",
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(noop_payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "compact", "-json", "-data-dir", "custom_db"])
    # All keys present (spec § 7.1 promises the full set).
    for key in ("success", "noop", "journal_size", "needs_compact", "reason"):
        assert key in result, f"compact no-op payload missing required key: {key}"
    assert result["success"] is True
    assert result["noop"] is True
    assert result["journal_size"] == 0
    assert result["needs_compact"] is False
    assert "sqlite" in result["reason"].lower()
    # Wrapper must still return True end-to-end.
    monkeypatch.setattr(go_cli, "run", lambda args, *, timeout=30: noop_payload)
    assert go_cli.db_compact_journal("custom_db") is True


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


def test_db_stats_with_phase_b1_fields_still_parses(monkeypatch):
    """Forward-compat: `db stats` under USE_SQLITE_READS=true emits the
    Phase A3 fields (`sync_degraded_total` / `sync_degraded_log_size`)
    plus the Phase B1 `sqlite_read_fallback_total` counter. Python only
    reads the A0 subset via go_cli.run, so the richer payload must round-
    trip untouched and the Python helper must keep returning a dict.
    """
    _patch_exe(monkeypatch)
    stats_payload = {
        # A0 keys.
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
        # A3 additions.
        "sync_degraded_total": 0,
        "sync_degraded_log_size": 0,
        # B1 addition.
        "sqlite_read_fallback_total": 0,
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(stats_payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "stats", "-data-dir", "custom_db"])

    assert result["sqlite_read_fallback_total"] == 0
    assert result["sync_degraded_total"] == 0
    assert result["sync_degraded_log_size"] == 0
    # A0 keys must still be intact alongside the new ones.
    for required in (
        "journal_size",
        "journal_age_seconds",
        "dirty_videos",
        "dirty_actresses",
        "dirty_links",
        "needs_compact",
        "total_videos",
    ):
        assert required in result


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


def test_db_backup_create_returns_dual_snapshot_paths(monkeypatch):
    """Slice C1: `db backup-create` must emit `backup_path` (SQLite) and
    `json_export_path` (JSON export of the SQLite store). The legacy
    `path` field is preserved as an alias of `json_export_path` so the
    existing JSONDBManager.create_backup() helper (which only reads
    `path`) keeps working without Python-side changes.
    """
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {
            "success": True,
            "backup_path": "data/backup/backup_2026-05-23_12-34-56.sqlite",
            "json_export_path": "data/backup/backup_2026-05-23_12-34-56.json",
            "path": "data/backup/backup_2026-05-23_12-34-56.json",
        }

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_create("custom_db")

    assert result["success"] is True
    assert "backup_path" in result
    assert "json_export_path" in result
    assert result["backup_path"].endswith(".sqlite")
    assert result["json_export_path"].endswith(".json")
    # Legacy alias: JSONDBManager.create_backup() reads result["path"] and
    # expects a JSON snapshot. It must equal json_export_path so the JSON
    # helper keeps producing the same artefact callers used pre-C1.
    assert "path" in result
    assert result["path"] == result["json_export_path"]
    # Both snapshots share a parent directory so backup-list discovers them
    # together (the json sibling is what backup-list returns).
    from pathlib import PurePosixPath
    assert PurePosixPath(result["backup_path"]).parent == PurePosixPath(result["json_export_path"]).parent
    assert captured["args"] == ["db", "backup-create", "-data-dir", "custom_db"]


def test_db_backup_restore_mutual_exclusion_exit_2(monkeypatch):
    """Slice C1: passing both -backup-path and -from-json is a config
    error. The CLI must exit 2 with the canonical message and Python
    must surface it through GoError (callers can grep the message).
    """
    _patch_exe(monkeypatch)
    canonical = "error: -backup-path and -from-json are mutually exclusive; pass exactly one"

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr=canonical)

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    with pytest.raises(go_cli.GoError) as ei:
        go_cli.run([
            "db", "backup-restore",
            "-backup-path", "data/backup/x.sqlite",
            "-from-json", "data/backup/y.json",
        ])
    msg = str(ei.value)
    assert "exit 2" in msg
    assert "mutually exclusive" in msg
    assert "-backup-path" in msg and "-from-json" in msg


def test_db_backup_restore_missing_inputs_exit_2(monkeypatch):
    """Slice C1: passing neither flag is also a config error with the
    other canonical message. Same exit code so callers can distinguish
    "bad CLI input" (exit 2) from "restore failed" (exit 1).
    """
    _patch_exe(monkeypatch)
    canonical = (
        "error: db backup-restore requires either -backup-path <sqlite> "
        "or -from-json <json>"
    )

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr=canonical)

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    with pytest.raises(go_cli.GoError) as ei:
        go_cli.run(["db", "backup-restore"])
    msg = str(ei.value)
    assert "exit 2" in msg
    assert "requires either -backup-path" in msg
    assert "-from-json" in msg


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


# ---------------------------------------------------------------------------
# Phase D — wrapper contract locks for SQLite-only `db` subcommands.
#
# The Python helper does not (yet) wrap migrate-from-json / verify-sync /
# resync-from-json / export-json. The tests below use monkeypatch to drive
# `go_cli.run` (or its underlying subprocess call) with the exact JSON
# shapes the Go CLI emits today, so any future runtime change to those
# payload keys / stderr wording lights up here first — independent of
# whether anyone has built a Python wrapper around them yet.
# ---------------------------------------------------------------------------


def test_db_migrate_from_json_strict_report_shape(monkeypatch):
    """`db migrate-from-json` (strict mode, happy path) emits the full
    MigrationReport JSON. Pin every key the report struct in
    `pkg/database/migrate_from_json.go::MigrationReport` declares — when
    the struct changes, this test is the canary for the Python side.
    """
    _patch_exe(monkeypatch)
    report_payload = {
        "success": True,
        "source_path": "data/json_db/data.json",
        "sqlite_path": "data/db.sqlite",
        "videos_imported": 3,
        "actresses_imported": 3,
        "links_imported": 4,
        "elapsed_ms": 17,
    }

    captured = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(report_payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(
        ["db", "migrate-from-json", "-data-dir", "data/json_db"]
    )

    # Every required key in the MigrationReport struct must round-trip
    # through the Python boundary intact. omitempty fields (auto_created,
    # unresolved, duplicates) are intentionally absent on the happy path.
    for required in (
        "success",
        "source_path",
        "sqlite_path",
        "videos_imported",
        "actresses_imported",
        "links_imported",
        "elapsed_ms",
    ):
        assert required in result, f"migrate report missing {required}: {result!r}"
    assert result["success"] is True
    assert result["videos_imported"] == 3
    assert captured["cmd"][1:] == [
        "db",
        "migrate-from-json",
        "-data-dir",
        "data/json_db",
    ]


def test_db_migrate_from_json_auto_create_flag_present(monkeypatch):
    """Lock two shapes that recovery tooling depends on:

    1. Strict-mode failure surfaces the canonical "unresolved actress
       references" stderr string via GoError, so callers can grep it and
       recommend the recovery command.
    2. The `-auto-create-missing-actresses` flag survives the wrapper
       argv intact and the resulting MigrationReport carries auto_created
       entries (per `MigrationAutoCreated`).
    """
    _patch_exe(monkeypatch)

    # Part 1: strict-mode failure stderr.
    strict_stderr = (
        "migrate-from-json failed: migrate-from-json: "
        "unresolved actress references (1 entries)"
    )

    def fake_strict_failure(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="{}", stderr=strict_stderr)

    monkeypatch.setattr(go_cli.subprocess, "run", fake_strict_failure)

    with pytest.raises(go_cli.GoError) as ei:
        go_cli.run(["db", "migrate-from-json", "-data-dir", "data/json_db"])
    msg = str(ei.value)
    assert "exit 1" in msg
    assert "unresolved actress references" in msg, (
        "strict-mode stderr must keep the canonical 'unresolved actress "
        "references' phrase so callers can hint at -auto-create-missing-actresses"
    )

    # Part 2: -auto-create-missing-actresses round-trips through the CLI
    # boundary and is reflected in the success report.
    captured = {}
    auto_payload = {
        "success": True,
        "source_path": "data/json_db/data.json",
        "sqlite_path": "data/db.sqlite",
        "videos_imported": 3,
        "actresses_imported": 4,
        "links_imported": 4,
        "auto_created": [
            {
                "name": "新女優",
                "actress_id": "auto_abcdef0123456789",
                "video_code": "TEST-001",
            }
        ],
        "elapsed_ms": 12,
    }

    def fake_auto_create(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(auto_payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_auto_create)

    result = go_cli.run(
        [
            "db",
            "migrate-from-json",
            "-data-dir",
            "data/json_db",
            "-auto-create-missing-actresses",
        ]
    )
    assert "-auto-create-missing-actresses" in captured["cmd"], (
        "wrapper must forward the recovery flag verbatim"
    )
    assert isinstance(result.get("auto_created"), list)
    assert result["auto_created"][0]["actress_id"].startswith("auto_")


def test_db_verify_sync_happy_payload_keys(monkeypatch):
    """`db verify-sync` happy path: consistent=true, count fields present,
    diffs omitted (omitempty in `VerifyReport`).
    """
    _patch_exe(monkeypatch)
    payload = {
        "consistent": True,
        "video_count": 3,
        "actress_count": 3,
        "link_count": 4,
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "verify-sync", "-data-dir", "data/json_db"])

    for required in ("consistent", "video_count", "actress_count", "link_count"):
        assert required in result, f"verify-sync missing {required}: {result!r}"
    assert result["consistent"] is True
    # diffs is omitempty — happy path must NOT emit it. Catches a runtime
    # regression that would always emit an empty list (harmless to read
    # but a contract change worth noticing).
    assert "diffs" not in result


def test_db_resync_from_json_payload_keys(monkeypatch):
    """`db resync-from-json` reuses the MigrationReport shape (it shares
    `runImport` with migrate-from-json), so the same required keys apply.
    """
    _patch_exe(monkeypatch)
    payload = {
        "success": True,
        "source_path": "data/json_db/data.json",
        "sqlite_path": "data/db.sqlite",
        "videos_imported": 3,
        "actresses_imported": 3,
        "links_imported": 4,
        "elapsed_ms": 19,
    }

    def fake_subprocess_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(["db", "resync-from-json", "-data-dir", "data/json_db"])

    for required in (
        "success",
        "source_path",
        "sqlite_path",
        "videos_imported",
        "actresses_imported",
        "links_imported",
        "elapsed_ms",
    ):
        assert required in result, f"resync report missing {required}: {result!r}"
    assert result["success"] is True


def test_db_export_json_payload_keys(monkeypatch):
    """`db export-json -output <path>` emits the small wrapper payload
    `{success, output, sqlite_path}` to stdout (the JSON DB itself is
    written to the output file, not stdout, when -output is used).
    """
    _patch_exe(monkeypatch)
    payload = {
        "success": True,
        "output": "data/json_db/data.json",
        "sqlite_path": "data/db.sqlite",
    }

    captured = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(go_cli.subprocess, "run", fake_subprocess_run)

    result = go_cli.run(
        [
            "db",
            "export-json",
            "-data-dir",
            "data/json_db",
            "-output",
            "data/json_db/data.json",
        ]
    )

    for required in ("success", "output", "sqlite_path"):
        assert required in result, f"export-json missing {required}: {result!r}"
    assert result["success"] is True
    # Reflect the -output we passed, so the wrapper can show users where
    # the snapshot landed without re-parsing argv.
    assert result["output"] == "data/json_db/data.json"
    assert "-output" in captured["cmd"]


def test_db_backup_create_dual_snapshot_legacy_path_alias(monkeypatch):
    """Phase D §8.1 dedicated contract: the legacy `path` alias on
    `db backup-create` must equal `json_export_path`. JSONDBManager.
    create_backup() only reads `path`, so any drift here silently breaks
    the Wails GUI's "備份" button.
    """
    captured = {}
    payload = {
        "success": True,
        "backup_path": "data/backup/backup_2026-05-24_10-11-12.sqlite",
        "json_export_path": "data/backup/backup_2026-05-24_10-11-12.json",
        "path": "data/backup/backup_2026-05-24_10-11-12.json",
    }

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return payload

    monkeypatch.setattr(go_cli, "run", fake_run)

    result = go_cli.db_backup_create("custom_db")

    assert result["success"] is True
    # The three keys must all be present; path is the legacy alias kept
    # alive for src/models/json_database.py.create_backup().
    assert "backup_path" in result
    assert "json_export_path" in result
    assert "path" in result
    # Alias equality is the load-bearing contract.
    assert result["path"] == result["json_export_path"], (
        "legacy `path` alias must mirror json_export_path so the existing "
        "JSONDBManager.create_backup() helper keeps producing the same JSON file"
    )
    # Sanity: aliased file is JSON, primary backup is SQLite.
    assert result["path"].endswith(".json")
    assert result["backup_path"].endswith(".sqlite")
    assert captured["args"] == ["db", "backup-create", "-data-dir", "custom_db"]


# ---------------------------------------------------------------------------
# T15 — argv locks for cache_* / history / move wrappers.
#
# These wrappers translate Python kwargs into classifier.exe argv. Pin the
# exact argv list each one builds so any flag rename / reorder / drop on the
# Go side surfaces here. cache_* wrappers call go_cli.run WITHOUT exe_path
# (fake signature: def fake_run(args, *, timeout=30)); move_*/history wrappers
# pass exe_path through (fake signature: def fake_run(args, **kwargs)).
# ---------------------------------------------------------------------------


def test_cache_get_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        # aGVsbG8= == base64("hello"); cache_get base64-decodes value.
        return {"success": True, "value": "aGVsbG8="}

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.cache_get("demo-key", cache_dir="mycache") == b"hello"
    assert captured["args"] == ["cache", "get", "-cache-dir", "mycache", "demo-key"]


def test_cache_set_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.cache_set("demo-key", b"hello", ttl_hours=48, cache_dir="mycache") is True
    # value is base64("hello") == "aGVsbG8=" and rides last in argv.
    assert captured["args"] == [
        "cache",
        "set",
        "-cache-dir",
        "mycache",
        "-ttl-hours",
        "48",
        "demo-key",
        "aGVsbG8=",
    ]


def test_cache_delete_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    assert go_cli.cache_delete("demo-key", cache_dir="mycache") is True
    assert captured["args"] == ["cache", "delete", "-cache-dir", "mycache", "demo-key"]


def test_cache_get_stats_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"total_files": 0}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.cache_get_stats(cache_dir="mycache")
    assert captured["args"] == ["cache", "stats", "-cache-dir", "mycache"]


def test_cache_prune_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"deleted_files": 0}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.cache_prune(
        cache_dir="mycache",
        ttl_days=14,
        max_size_mb=250,
        min_keep=50,
        dry_run=True,
    )
    assert captured["args"] == [
        "cache",
        "prune",
        "-cache-dir",
        "mycache",
        "-ttl-days",
        "14",
        "-max-size",
        "250",
        "-min-keep",
        "50",
        "-dry-run",
    ]


def test_cache_clear_argv(monkeypatch):
    captured = {}

    def fake_run(args, *, timeout=30):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    # Non-dry-run appends -confirm.
    go_cli.cache_clear(cache_dir="mycache", dry_run=False)
    assert captured["args"] == ["cache", "clear", "-cache-dir", "mycache", "-confirm"]

    # dry-run appends -dry-run instead of -confirm.
    go_cli.cache_clear(cache_dir="mycache", dry_run=True)
    assert captured["args"] == ["cache", "clear", "-cache-dir", "mycache", "-dry-run"]


def test_rollback_argv(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.rollback("op-123", log_dir="mylogs")
    assert captured["args"] == ["history", "rollback", "op-123", "-log-dir", "mylogs"]


def test_rollback_last_argv(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return {"success": True}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.rollback_last(log_dir="mylogs")
    assert captured["args"] == ["history", "rollback", "--last", "-log-dir", "mylogs"]


def test_list_operations_argv(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return []

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.list_operations(limit=25, log_dir="mylogs")
    assert captured["args"] == ["history", "list", "-log-dir", "mylogs", "-limit", "25"]


def test_move_file_argv(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return {"success": True, "source": "a.mp4", "destination": "b.mp4"}

    monkeypatch.setattr(go_cli, "run", fake_run)

    go_cli.move_file("a.mp4", "b.mp4", "overwrite")
    assert captured["args"] == [
        "move",
        "-src",
        "a.mp4",
        "-dst",
        "b.mp4",
        "-strategy",
        "overwrite",
    ]


def test_batch_move_argv(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return {"total": 1, "success": 1, "failed": 0, "skipped": 0, "results": []}

    monkeypatch.setattr(go_cli, "run", fake_run)
    # Don't depend on WSL path conversion for the temp file path assertion.
    monkeypatch.setattr(go_cli, "_to_windows_cli_path", lambda path: path)

    go_cli.batch_move(
        [{"source": "a.mp4", "destination": "b.mp4"}],
        strategy="rename",
        log_dir="mylogs",
    )
    args = captured["args"]
    # batch_move writes a temp JSON whose path rides at index 2; assert the
    # subcommand + flags around it rather than the volatile temp path.
    assert args[0] == "move"
    assert args[1] == "-batch"
    assert args[2].endswith(".json")
    assert args[3:] == ["-strategy", "rename", "-log-dir", "mylogs"]
