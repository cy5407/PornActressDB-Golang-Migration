import json
import sys
import threading
from types import ModuleType
from types import SimpleNamespace

import pytest

from src.models.json_types import get_empty_video
from src.scrapers import run_batch_search as run_batch_search_module
from src.scrapers import run_search as run_search_module
from src.services.web_searcher import WebSearcher


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


def test_run_search_updates_not_found_based_on_empty_actresses_only():
    captured = {}
    fake_db = SimpleNamespace(
        get_video_info=lambda _code: {"code": "ABC-123"},
        update_video=lambda _code, updates: captured.update(updates),
    )

    run_search_module._update_source_search_status(
        "ABC-123",
        {
            "title": "有標題",
            "studio": "有片商",
            "url": "https://example.com",
            "actresses": [],
        },
        "javdb",
        db=fake_db,
        now="2026-04-10T00:00:00Z",
    )

    assert captured["javdb_actress_status"] == "not_found"
    assert captured["javdb_last_search_date"] == "2026-04-10T00:00:00Z"


def test_run_search_creates_minimal_record_for_brand_new_code_before_status_update():
    created = {}
    updated = {}
    fake_db = SimpleNamespace(
        get_video_info=lambda _code: None,
        add_or_update_video=lambda _code, info: created.update(info),
        update_video=lambda _code, updates: updated.update(updates),
    )

    run_search_module._update_source_search_status(
        "ABC-123",
        {
            "actresses": [],
            "search_status": "search_error",
        },
        "avwiki",
        db=fake_db,
        now="2026-04-10T00:00:00Z",
    )

    empty_video = get_empty_video()
    assert created["code"] == "ABC-123"
    for key in empty_video:
        assert key in created
    assert updated["avwiki_actress_status"] == "error"
    assert updated["avwiki_last_search_date"] == "2026-04-10T00:00:00Z"


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
    assert result["method"] == ""


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
