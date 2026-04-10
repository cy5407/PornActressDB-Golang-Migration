"""補測 UnifiedFileScanner 覆蓋率。"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.utils.scanner import UnifiedFileScanner


def _scanner(**kwargs) -> UnifiedFileScanner:
    """建立不啟動 Go 的掃描器（預設 use_go=False）。"""
    return UnifiedFileScanner(**kwargs)


# ──────────────────────────────
# go_bridge property
# ──────────────────────────────


def test_go_bridge_returns_none_when_use_go_false():
    s = _scanner(use_go=False)
    assert s.go_bridge is None


def test_go_bridge_returns_self_when_go_available(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    s = _scanner(use_go=True)
    assert s.go_bridge is s


def test_go_bridge_returns_none_when_go_unavailable(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: False)
    s = _scanner(use_go=True)
    assert s.go_bridge is None


def test_go_bridge_caches_result(monkeypatch):
    calls = []

    def fake_is_available(exe_path=None):
        calls.append(1)
        return True

    monkeypatch.setattr("src.services.go_cli.is_available", fake_is_available)
    s = _scanner(use_go=True)
    _ = s.go_bridge
    _ = s.go_bridge  # 第二次不應再呼叫
    assert len(calls) == 1


def test_go_bridge_sets_use_go_false_on_unavailable(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: False)
    s = _scanner(use_go=True)
    _ = s.go_bridge
    assert s.use_go is False


# ──────────────────────────────
# is_available property
# ──────────────────────────────


def test_is_available_false_when_not_checked():
    s = _scanner(use_go=False)
    assert s.is_available is False


def test_is_available_true_after_go_bridge(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    s = _scanner(use_go=True)
    _ = s.go_bridge
    assert s.is_available is True


# ──────────────────────────────
# _check_go_available
# ──────────────────────────────


def test_check_go_available_returns_false_on_exception(monkeypatch):
    def raise_err(exe_path=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.services.go_cli.is_available", raise_err)
    s = _scanner(use_go=True)
    assert s._check_go_available() is False


# ──────────────────────────────
# scan_directory
# ──────────────────────────────


def test_scan_directory_raises_when_no_go():
    s = _scanner(use_go=False)
    with pytest.raises(RuntimeError, match="Go CLI 不可用"):
        s.scan_directory("/some/path")


def test_scan_directory_success_recursive(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr(
        "src.services.go_cli.run",
        lambda args, exe_path=None: [{"path": "/a/STARS-001.mp4"}, {"path": "/b/SONE-002.mp4"}],
    )
    s = _scanner(use_go=True)
    results = s.scan_directory("/videos", recursive=True)
    assert len(results) == 2
    assert all(isinstance(p, Path) for p in results)


def test_scan_directory_non_recursive(monkeypatch):
    captured = {}

    def fake_run(args, exe_path=None):
        captured["args"] = args
        return []

    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", fake_run)
    s = _scanner(use_go=True)
    s.scan_directory("/videos", recursive=False)
    assert "-recursive=false" in captured["args"]


def test_scan_directory_skips_items_without_path(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr(
        "src.services.go_cli.run",
        lambda args, exe_path=None: [{"path": "/a.mp4"}, {"no_path": True}],
    )
    s = _scanner(use_go=True)
    results = s.scan_directory("/videos")
    assert len(results) == 1


def test_scan_directory_returns_empty_when_not_list(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", lambda args, exe_path=None: {"error": "bad"})
    s = _scanner(use_go=True)
    results = s.scan_directory("/videos")
    assert results == []


def test_scan_directory_wraps_exception(monkeypatch):
    def raise_err(args, exe_path=None):
        raise OSError("network down")

    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", raise_err)
    s = _scanner(use_go=True)
    with pytest.raises(RuntimeError, match="Go 掃描失敗"):
        s.scan_directory("/videos")


# ──────────────────────────────
# scan_with_codes
# ──────────────────────────────


def test_scan_with_codes_raises_when_no_go():
    s = _scanner(use_go=False)
    with pytest.raises(RuntimeError, match="scan_with_codes 需要 Go CLI"):
        s.scan_with_codes("/some/path")


def test_scan_with_codes_success(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr(
        "src.services.go_cli.run",
        lambda args, exe_path=None: [
            {"path": "/a.mp4", "code": "STARS-001"},
            {"path": "/b.mp4"},  # no code
        ],
    )
    s = _scanner(use_go=True)
    results = s.scan_with_codes("/videos")
    assert len(results) == 2
    assert results[0]["code"] == "STARS-001"
    assert results[1]["code"] == ""


def test_scan_with_codes_non_recursive(monkeypatch):
    captured = {}

    def fake_run(args, exe_path=None):
        captured["args"] = args
        return []

    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", fake_run)
    s = _scanner(use_go=True)
    s.scan_with_codes("/videos", recursive=False)
    assert "-recursive=false" in captured["args"]


def test_scan_with_codes_returns_empty_when_not_list(monkeypatch):
    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", lambda args, exe_path=None: None)
    s = _scanner(use_go=True)
    assert s.scan_with_codes("/videos") == []


def test_scan_with_codes_wraps_exception(monkeypatch):
    def raise_err(args, exe_path=None):
        raise OSError("oops")

    monkeypatch.setattr("src.services.go_cli.is_available", lambda exe=None: True)
    monkeypatch.setattr("src.services.go_cli.run", raise_err)
    s = _scanner(use_go=True)
    with pytest.raises(RuntimeError, match="Go 掃描失敗"):
        s.scan_with_codes("/videos")


# ──────────────────────────────
# from_config
# ──────────────────────────────


def test_from_config_reads_settings():
    class MockConfig:
        def getboolean(self, section, key, fallback=None):
            if section == "go_integration" and key == "enabled":
                return True
            return fallback

        def getint(self, section, key, fallback=None):
            if section == "go_integration" and key == "scan_workers":
                return 5
            return fallback

        def get(self, section, key, fallback=None):
            if section == "go_integration" and key == "exe_path":
                return ""
            return fallback

    s = UnifiedFileScanner.from_config(MockConfig())
    assert s.use_go is True
    assert s.go_workers == 5
    assert s.go_exe_path is None


def test_from_config_fallbacks_when_empty_exe():
    class MockConfig:
        def getboolean(self, section, key, fallback=None):
            return fallback

        def getint(self, section, key, fallback=None):
            return fallback

        def get(self, section, key, fallback=None):
            return ""  # empty string → should become None

    s = UnifiedFileScanner.from_config(MockConfig())
    assert s.go_exe_path is None
