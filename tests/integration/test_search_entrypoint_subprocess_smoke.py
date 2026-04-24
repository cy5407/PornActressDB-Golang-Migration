import json
import os
import subprocess
import sys
from pathlib import Path

from src.utils.stdio import DEFAULT_TEXT_ENCODING, PYTHON_UTF8_MODE

ROOT_DIR = Path(__file__).resolve().parents[2]
RUN_SEARCH = ROOT_DIR / "src" / "scrapers" / "run_search.py"
RUN_BATCH_SEARCH = ROOT_DIR / "src" / "scrapers" / "run_batch_search.py"


def _run_with_sitecustomize(tmp_path: Path, script: Path, args: list[str], stdin: str | None = None):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """
import sys
import types

models_config = types.ModuleType('models.config')
class ConfigManager:
    def __init__(self, *_args, **_kwargs):
        pass
models_config.ConfigManager = ConfigManager
sys.modules['models.config'] = models_config

models_json_types = types.ModuleType('models.json_types')
def get_empty_video():
    return {\n        'code': '', 'title': '', 'studio': '', 'release_date': '', 'url': '',\n        'actresses': [], 'search_method': '', 'error': '',\n        'avwiki_actress_status': '', 'avwiki_last_search_date': '',\n        'javdb_actress_status': '', 'javdb_last_search_date': '',\n        'created_at': '', 'updated_at': '',\n    }
models_json_types.get_empty_video = get_empty_video
sys.modules['models.json_types'] = models_json_types

models_incremental = types.ModuleType('models.incremental_json_database')
class IncrementalJSONDB:
    def __init__(self, *_args, **_kwargs):
        self.store = {}
    def get_video_info(self, code):
        return self.store.get(code)
    def add_or_update_video(self, code, info):
        self.store[code] = dict(info)
    def update_video(self, code, updates):
        self.store.setdefault(code, {}).update(updates)
models_incremental.IncrementalJSONDB = IncrementalJSONDB
sys.modules['models.incremental_json_database'] = models_incremental

services_web_searcher = types.ModuleType('services.web_searcher')
class WebSearcher:
    def __init__(self, *_args, **_kwargs):
        self.japanese_searcher = types.SimpleNamespace(config=types.SimpleNamespace(min_interval=0.0, max_interval=0.0))
        self.safe_searcher = types.SimpleNamespace(config=types.SimpleNamespace(min_interval=0.0, max_interval=0.0))
        self.search_info = lambda code, _stop_event: {
            'code': code,
            'title': 'Fake Title',
            'studio': 'S1',
            'release_date': '2026-04-11',
            'url': 'https://example.invalid/' + code,
            'actresses': ['Actor A'],
            'search_method': 'FAKE',
        }
        self.search_avwiki_only = self.search_info
        self.search_javdb_only = self.search_info
services_web_searcher.WebSearcher = WebSearcher
sys.modules['services.web_searcher'] = services_web_searcher
        """
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["PYTHONIOENCODING"] = DEFAULT_TEXT_ENCODING
    env["PYTHONUTF8"] = PYTHON_UTF8_MODE

    proc = subprocess.run(
        [sys.executable, str(script), *args],
        input=stdin,
        text=True,
        encoding=DEFAULT_TEXT_ENCODING,
        capture_output=True,
        env=env,
        check=False,
    )
    return proc


def test_run_search_subprocess_smoke_success(tmp_path):
    proc = _run_with_sitecustomize(tmp_path, RUN_SEARCH, ["ABC-123"], None)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["code"] == "ABC-123"
    assert payload["title"] == "Fake Title"
    assert payload["search_method"] == "FAKE"
    assert payload["error"] == ""


def test_run_search_subprocess_invalid_source_mode_returns_json_error(tmp_path):
    proc = _run_with_sitecustomize(tmp_path, RUN_SEARCH, ["ABC-123", "invalid"], None)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["code"] == "ABC-123"
    assert payload["error"] == "搜尋時發生例外: 不支援的搜尋來源模式: invalid"


def test_run_batch_search_subprocess_smoke_success(tmp_path):
    proc = _run_with_sitecustomize(
        tmp_path,
        RUN_BATCH_SEARCH,
        [],
        json.dumps({"codes": ["ABC-123", "DEF-456"], "workers": 2, "source_mode": "cascade"}),
    )

    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    assert {item["code"] for item in payloads} == {"ABC-123", "DEF-456"}
    assert all(item["title"] == "Fake Title" for item in payloads)
    assert all(item["error"] == "" for item in payloads)


def test_run_batch_search_subprocess_rejects_invalid_source_mode(tmp_path):
    proc = _run_with_sitecustomize(
        tmp_path,
        RUN_BATCH_SEARCH,
        [],
        json.dumps({"codes": ["ABC-123"], "workers": 1, "source_mode": "invalid"}),
    )

    assert proc.returncode == 1
    assert "不支援的搜尋來源模式: invalid" in proc.stderr
