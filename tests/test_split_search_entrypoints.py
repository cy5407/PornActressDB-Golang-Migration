import json
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.models.incremental_json_database import IncrementalJSONDB
from src.models.json_types import get_empty_video
from src.scrapers import run_batch_search as run_batch_search_module
from src.scrapers import run_search as run_search_module
from src.services.web_searcher import WebSearcher

REAL_DB_SAMPLE_VIDEO = {
    "code": "AARM-247",
    "title": "",
    "studio": "アロマ企画",
    "release_date": "",
    "url": "",
    "actresses": ["仲川そら"],
}


def _seed_incremental_db(tmp_path: Path, video: dict | None = None) -> IncrementalJSONDB:
    db = IncrementalJSONDB(str(tmp_path / "json_db"))
    if video is not None:
        base_video = get_empty_video()
        base_video.update(video)
        db.add_or_update_video(base_video["code"], base_video)
    return db


@pytest.mark.parametrize(
    "module",
    [run_search_module, run_batch_search_module],
)
def test_search_entrypoints_resolve_project_config_before_cwd(
    tmp_path, monkeypatch, module
):
    project_root = tmp_path / "project"
    cwd = tmp_path / "cwd"
    project_root.mkdir()
    cwd.mkdir()
    project_config = project_root / "config.ini"
    cwd_config = cwd / "config.ini"
    project_config.write_text("[settings]\n", encoding="utf-8")
    cwd_config.write_text("[settings]\n", encoding="utf-8")

    monkeypatch.setattr(module, "_PROJECT_ROOT", str(project_root))
    monkeypatch.chdir(cwd)

    assert Path(module._resolve_config_path()) == project_config


@pytest.mark.parametrize(
    "module",
    [run_search_module, run_batch_search_module],
)
def test_search_entrypoints_resolve_cwd_config_when_project_config_missing(
    tmp_path, monkeypatch, module
):
    project_root = tmp_path / "project"
    cwd = tmp_path / "cwd"
    project_root.mkdir()
    cwd.mkdir()
    cwd_config = cwd / "config.ini"
    cwd_config.write_text("[settings]\n", encoding="utf-8")

    monkeypatch.setattr(module, "_PROJECT_ROOT", str(project_root))
    monkeypatch.chdir(cwd)

    assert Path(module._resolve_config_path()) == cwd_config


def test_web_searcher_search_avwiki_only_returns_search_error_without_caching():
    searcher = object.__new__(WebSearcher)
    searcher.search_cache = {}
    searcher._build_code_candidates = lambda code: [code, "ABC-001"]
    searcher._search_av_wiki = lambda candidate, _stop_event: (
        {
            "source": "AV-WIKI (安全增強版)",
            "actresses": [],
            "search_status": "search_error",
            "search_error_reason": "暫時異常",
        }
        if candidate == "ABC-001"
        else None
    )

    result = searcher.search_avwiki_only("ABC-0001", threading.Event())

    assert result["source"] == "AV-WIKI (安全增強版)"
    assert result["search_status"] == "search_error"
    assert result["search_alias_used"] is True
    assert "ABC-0001" not in searcher.search_cache


def test_run_search_dispatches_to_avwiki_only():
    called = {}
    searcher = SimpleNamespace(
        search_info=lambda *_args: called.setdefault("method", "cascade"),
        search_avwiki_only=lambda *_args: {"source": "AV-WIKI"},
        search_javdb_only=lambda *_args: called.setdefault("method", "javdb"),
    )

    result = run_search_module._search_with_mode(
        searcher, "ABC-123", threading.Event(), "avwiki"
    )

    assert result == {"source": "AV-WIKI"}
    assert "method" not in called


def test_run_search_updates_existing_real_db_record_from_source_status(tmp_path):
    db = _seed_incremental_db(tmp_path, REAL_DB_SAMPLE_VIDEO)

    run_search_module._update_source_search_status(
        "AARM-247",
        {
            "title": "有標題",
            "studio": "有片商",
            "url": "https://example.com",
            "actresses": [],
        },
        "javdb",
        db=db,
        now="2026-04-10T00:00:00Z",
    )

    updated = db.get_video_info("AARM-247")
    assert updated["studio"] == "アロマ企画"
    assert updated["actresses"] == ["仲川そら"]
    assert updated["javdb_actress_status"] == "not_found"
    assert updated["javdb_last_search_date"] == "2026-04-10T00:00:00Z"


def test_run_search_creates_minimal_real_db_record_for_brand_new_code(tmp_path):
    db = _seed_incremental_db(tmp_path)

    run_search_module._update_source_search_status(
        "ABC-123",
        {
            "actresses": [],
            "search_status": "search_error",
        },
        "avwiki",
        db=db,
        now="2026-04-10T00:00:00Z",
    )

    created = db.get_video_info("ABC-123")
    assert created is not None
    for key in ("code", "title", "studio", "actresses", "search_status", "metadata"):
        assert key in created
    assert created["code"] == "ABC-123"
    assert created["avwiki_actress_status"] == "error"
    assert created["avwiki_last_search_date"] == "2026-04-10T00:00:00Z"


def test_run_batch_search_search_one_accepts_source_mode(monkeypatch):
    run_batch_search_module._thread_local = threading.local()
    called = {}

    monkeypatch.setattr(
        run_batch_search_module,
        "_get_searcher",
        lambda: SimpleNamespace(
            search_info=lambda *_args: called.setdefault("method", "cascade"),
            search_avwiki_only=lambda *_args: {"actresses": ["A"], "source": "AV-WIKI"},
            search_javdb_only=lambda *_args: called.setdefault("method", "javdb"),
        ),
    )
    monkeypatch.delattr(
        run_batch_search_module, "_update_source_search_status", raising=False
    )

    result = run_batch_search_module.search_one("ABC-123", source_mode="avwiki")

    assert result["actresses"] == ["A"]
    assert "method" not in called


def test_run_batch_search_get_searcher_reuses_real_thread_local_instance(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"""
[search]
enable_cache = false
cache_dir = {tmp_path.as_posix()}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_batch_search_module, "_thread_local", threading.local())
    monkeypatch.setattr(
        run_batch_search_module, "_resolve_config_path", lambda: str(config_path)
    )

    first = run_batch_search_module._get_searcher()
    second = run_batch_search_module._get_searcher()

    assert first is second
    assert first.__class__.__name__ == "WebSearcher"
    assert first.japanese_searcher.config.min_interval == 0.0
    assert first.japanese_searcher.config.max_interval == 0.0
    assert first.safe_searcher.config.min_interval == 0.0
    assert first.safe_searcher.config.max_interval == 0.0


def test_run_batch_search_normalize_accepts_legacy_field_names():
    result = run_batch_search_module._normalize(
        {
            "title": "Title",
            "studio": "Studio",
            "releaseDate": "2026-04-24",
            "url": "https://example.com",
            "actresses": " A, , B ",
            "method": "JAVDB",
            "error_kind": "not_found",
        },
        "ABC-123",
    )

    assert result == {
        "code": "ABC-123",
        "title": "Title",
        "studio": "Studio",
        "release_date": "2026-04-24",
        "url": "https://example.com",
        "actresses": ["A", "B"],
        "search_method": "JAVDB",
        "error": "",
        "error_kind": "not_found",
    }


def test_run_batch_search_build_error_result():
    result = run_batch_search_module._build_error_result(
        "ABC-123", "搜尋來源異常", "error"
    )

    assert result["code"] == "ABC-123"
    assert result["error"] == "搜尋來源異常"
    assert result["error_kind"] == "error"
    assert result["actresses"] == []


def test_run_batch_search_search_one_marks_not_found_with_error_kind(monkeypatch):
    run_batch_search_module._thread_local = threading.local()

    monkeypatch.setattr(
        run_batch_search_module,
        "_get_searcher",
        lambda: SimpleNamespace(
            search_info=lambda *_args: None,
            search_avwiki_only=lambda *_args: None,
            search_javdb_only=lambda *_args: None,
        ),
    )
    monkeypatch.delattr(
        run_batch_search_module, "_update_source_search_status", raising=False
    )

    result = run_batch_search_module.search_one("ABC-123", source_mode="avwiki")

    assert result["error"] == "未找到結果"
    assert result["error_kind"] == "not_found"


def test_run_batch_search_search_one_preserves_search_error_semantics(monkeypatch):
    run_batch_search_module._thread_local = threading.local()

    monkeypatch.setattr(run_batch_search_module, "_get_searcher", lambda: object())
    monkeypatch.setattr(
        run_batch_search_module,
        "_search_with_mode",
        lambda *_args: {
            "search_status": "search_error",
            "search_error_reason": "AV-WIKI 暫時異常",
        },
    )

    result = run_batch_search_module.search_one("ABC-123", source_mode="avwiki")

    assert result["code"] == "ABC-123"
    assert result["error"] == "AV-WIKI 暫時異常"
    assert result["error_kind"] == "error"
    assert result["title"] == ""
    assert result["actresses"] == []
    assert result["search_method"] == ""


def test_run_batch_search_search_one_marks_exception_with_error_kind(monkeypatch):
    run_batch_search_module._thread_local = threading.local()

    monkeypatch.setattr(
        run_batch_search_module,
        "_get_searcher",
        lambda: SimpleNamespace(
            search_info=lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")),
            search_avwiki_only=lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")),
            search_javdb_only=lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")),
        ),
    )
    monkeypatch.delattr(
        run_batch_search_module, "_update_source_search_status", raising=False
    )

    result = run_batch_search_module.search_one("ABC-123", source_mode="javdb")

    assert result["error"] == "boom"
    assert result["error_kind"] == "error"


def test_run_batch_search_main_reads_source_mode_from_stdin(monkeypatch, capsys):
    run_batch_search_module._thread_local = threading.local()
    monkeypatch.setattr(
        run_batch_search_module,
        "search_one",
        lambda code, source_mode="cascade": {
            "code": code,
            "title": "",
            "studio": "",
            "release_date": "",
            "url": "",
            "actresses": [source_mode],
            "method": source_mode,
            "error": "",
        },
    )
    monkeypatch.setattr(
        run_batch_search_module.sys,
        "stdin",
        SimpleNamespace(
            read=lambda: json.dumps(
                {"codes": ["ABC-123"], "workers": 1, "source_mode": "javdb"}
            )
        ),
    )

    run_batch_search_module.main()

    output = capsys.readouterr().out.strip()
    assert json.loads(output)["method"] == "javdb"


def test_run_batch_search_main_handles_invalid_source_mode(monkeypatch, capsys):
    monkeypatch.setattr(
        run_batch_search_module.sys,
        "stdin",
        SimpleNamespace(
            read=lambda: json.dumps(
                {"codes": ["ABC-123"], "workers": 1, "source_mode": "invalid"}
            )
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_batch_search_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "不支援的搜尋來源模式: invalid" in captured.err
    assert captured.out == ""


def test_run_batch_search_main_handles_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr(
        run_batch_search_module.sys,
        "stdin",
        SimpleNamespace(read=lambda: "{broken"),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_batch_search_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "JSON 輸入解析失敗:" in captured.err
    assert captured.out == ""


def test_run_batch_search_main_exits_cleanly_for_empty_codes(monkeypatch, capsys):
    monkeypatch.setattr(
        run_batch_search_module.sys,
        "stdin",
        SimpleNamespace(read=lambda: json.dumps({"codes": [], "workers": 5})),
    )

    with pytest.raises(SystemExit) as exc_info:
        run_batch_search_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_run_search_main_handles_invalid_source_mode_without_traceback(
    monkeypatch, capsys
):
    fake_config_module = ModuleType("models.config")
    fake_config_module.ConfigManager = lambda *_args, **_kwargs: object()
    fake_searcher_module = ModuleType("services.web_searcher")
    fake_searcher_module.WebSearcher = lambda _config: SimpleNamespace()

    monkeypatch.setitem(sys.modules, "models.config", fake_config_module)
    monkeypatch.setitem(sys.modules, "services.web_searcher", fake_searcher_module)
    monkeypatch.setattr(
        run_search_module.sys, "argv", ["run_search.py", "ABC-123", "invalid"]
    )

    with pytest.raises(SystemExit) as exc_info:
        run_search_module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert exc_info.value.code == 0
    assert payload["code"] == "ABC-123"
    assert payload["error"] == "搜尋時發生例外: 不支援的搜尋來源模式: invalid"
    assert captured.err == ""


def test_run_search_status_helpers_cover_modes_and_string_actresses():
    assert run_search_module._resolve_source_status_fields("avwiki") == (
        "avwiki_actress_status",
        "avwiki_last_search_date",
    )
    assert run_search_module._resolve_source_status_fields("javdb") == (
        "javdb_actress_status",
        "javdb_last_search_date",
    )
    assert run_search_module._resolve_source_status_fields("cascade") is None
    assert run_search_module._determine_source_status(
        {"actresses": " A, , B "}
    ) == "found"
    assert run_search_module._determine_source_status({"actresses": ""}) == "not_found"
    assert run_search_module._determine_source_status(
        {"search_status": "search_error", "actresses": ["A"]}
    ) == "error"


def test_run_search_update_status_ignores_cascade_mode():
    fake_db = SimpleNamespace(
        get_video_info=lambda _code: (_ for _ in ()).throw(
            AssertionError("cascade should not touch db")
        ),
    )

    run_search_module._update_source_search_status(
        "ABC-123", {"actresses": ["A"]}, "cascade", db=fake_db
    )


def test_run_search_update_status_swallows_database_errors():
    fake_db = SimpleNamespace(
        get_video_info=lambda _code: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    run_search_module._update_source_search_status(
        "ABC-123", {"actresses": ["A"]}, "avwiki", db=fake_db
    )


def test_run_search_main_reports_usage_for_missing_code(monkeypatch, capsys):
    monkeypatch.setattr(run_search_module.sys, "argv", ["run_search.py"])

    with pytest.raises(SystemExit) as exc_info:
        run_search_module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert exc_info.value.code == 1
    assert payload["code"] == ""
    assert payload["error"] == "Usage: run_search.py <video_code> [source_mode]"


def test_run_search_main_rejects_empty_code(monkeypatch, capsys):
    monkeypatch.setattr(run_search_module.sys, "argv", ["run_search.py", "  "])

    with pytest.raises(SystemExit) as exc_info:
        run_search_module.main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert exc_info.value.code == 0
    assert payload["code"] == ""
    assert payload["error"] == "番號不得為空"


def test_run_search_main_outputs_normalized_success(monkeypatch, capsys):
    fake_config_module = ModuleType("models.config")
    fake_searcher_module = ModuleType("services.web_searcher")
    fake_config_module.ConfigManager = lambda _path: object()
    fake_searcher_module.WebSearcher = lambda _config: SimpleNamespace(
        search_info=lambda *_args: {
            "title": "Title",
            "studio": "Studio",
            "releaseDate": "2026-04-24",
            "url": "https://example.com",
            "actresses": " A, , B ",
            "method": "Cascade",
        }
    )
    updated = {}

    monkeypatch.setitem(sys.modules, "models.config", fake_config_module)
    monkeypatch.setitem(sys.modules, "services.web_searcher", fake_searcher_module)
    monkeypatch.setattr(
        run_search_module, "_update_source_search_status", lambda *args: updated.setdefault("args", args)
    )
    monkeypatch.setattr(
        run_search_module, "_resolve_config_path", lambda: "config.ini"
    )
    monkeypatch.setattr(run_search_module.sys, "argv", ["run_search.py", "ABC-123"])

    run_search_module.main()

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == {
        "code": "ABC-123",
        "title": "Title",
        "studio": "Studio",
        "release_date": "2026-04-24",
        "url": "https://example.com",
        "actresses": ["A", "B"],
        "search_method": "Cascade",
        "error": "",
    }
    assert updated["args"][0] == "ABC-123"


def test_run_search_main_reports_not_found(monkeypatch, capsys):
    fake_config_module = ModuleType("models.config")
    fake_searcher_module = ModuleType("services.web_searcher")
    fake_config_module.ConfigManager = lambda _path: object()
    fake_searcher_module.WebSearcher = lambda _config: SimpleNamespace(
        search_info=lambda *_args: None
    )

    monkeypatch.setitem(sys.modules, "models.config", fake_config_module)
    monkeypatch.setitem(sys.modules, "services.web_searcher", fake_searcher_module)
    monkeypatch.setattr(run_search_module, "_update_source_search_status", lambda *_args: None)
    monkeypatch.setattr(run_search_module.sys, "argv", ["run_search.py", "ABC-123"])

    with pytest.raises(SystemExit) as exc_info:
        run_search_module.main()

    payload = json.loads(capsys.readouterr().out.strip())
    assert exc_info.value.code == 0
    assert payload["code"] == "ABC-123"
    assert payload["error"] == "未找到結果"


def test_web_searcher_search_javdb_only_uses_alias_candidates():
    searcher = object.__new__(WebSearcher)
    searcher.search_cache = {}
    search_calls = []
    searcher._build_code_candidates = lambda code: [code, "ABC-001"]
    searcher.javdb_searcher = SimpleNamespace(
        search_javdb=lambda candidate: (
            search_calls.append(candidate)
            or (
                {
                    "source": "JAVDB (安全增強版)",
                    "actresses": ["Alias Actress"],
                    "studio": "S1",
                    "title": "Alias Title",
                    "search_url": "https://example.com/ABC-001",
                }
                if candidate == "ABC-001"
                else None
            )
        )
    )
    searcher.studio_identifier = SimpleNamespace(
        normalize_studio_name=lambda studio, _candidate: studio
    )

    result = searcher.search_javdb_only("ABC-0001", threading.Event())

    assert search_calls == ["ABC-0001", "ABC-001"]
    assert result["actresses"] == ["Alias Actress"]
    assert result["title"] == "Alias Title"
    assert result["searched_code"] == "ABC-0001"
    assert result["matched_code"] == "ABC-001"
    assert result["search_alias_used"] is True
    assert searcher.search_cache["ABC-0001"] == result
