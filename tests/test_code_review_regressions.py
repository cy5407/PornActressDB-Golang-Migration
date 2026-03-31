import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.services import classifier_core as classifier_core_module
from src.services.web_searcher import WebSearcher


class _DummyConfig:
    def get(self, _section, _option, fallback=None):
        return fallback


class _DummyFactory:
    @staticmethod
    def from_config(_config):
        return object()


def test_classifier_core_falls_back_to_json_db(monkeypatch):
    class DummyJSONDBManager:
        def __init__(self, data_dir):
            self.data_dir = data_dir

    def raise_incremental_error(_data_dir):
        raise RuntimeError("journal init failed")

    monkeypatch.setattr(
        classifier_core_module, "IncrementalJSONDB", raise_incremental_error
    )
    monkeypatch.setattr(
        classifier_core_module, "JSONDBManager", DummyJSONDBManager
    )
    monkeypatch.setattr(classifier_core_module, "UnifiedCodeExtractor", lambda: object())
    monkeypatch.setattr(classifier_core_module, "UnifiedFileScanner", _DummyFactory)
    monkeypatch.setattr(classifier_core_module, "FileMover", _DummyFactory)
    monkeypatch.setattr(classifier_core_module, "StudioIdentifier", lambda: object())
    monkeypatch.setattr(
        classifier_core_module, "WebSearcher", lambda _config: object()
    )

    core = classifier_core_module.UnifiedClassifierCore(_DummyConfig())

    assert isinstance(core.db_manager, DummyJSONDBManager)
    assert core.db_manager.data_dir == "data/json_db"


def test_search_japanese_sites_only_delegates_to_unified_method():
    searcher = WebSearcher.__new__(WebSearcher)
    captured = {}

    def fake_search(code, stop_event):
        captured["args"] = (code, stop_event)
        return {"actresses": ["Aoi"]}

    searcher.search_japanese_sites = fake_search
    stop_event = object()

    result = searcher.search_japanese_sites_only("ABCD-123", stop_event)

    assert result == {"actresses": ["Aoi"]}
    assert captured["args"] == ("ABCD-123", stop_event)
