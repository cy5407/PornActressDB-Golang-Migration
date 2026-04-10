"""
補測 SearchProgressInfo 覆蓋率。
測試目標：找出真正的行為問題，不只是覆蓋行數。
"""
import threading
import time
import pytest
from src.utils.progress_tracker import SearchProgressInfo


def _prog(**kwargs) -> SearchProgressInfo:
    p = SearchProgressInfo(**kwargs)
    p.reset(total=kwargs.get("total", 10))
    return p


# ──────────────────────────────
# reset()
# ──────────────────────────────


def test_reset_clears_all_fields():
    p = SearchProgressInfo()
    p.current = 5
    p.success = 3
    p.failed = 2
    p.current_code = "STARS-001"
    p.source_stats = {"AV-WIKI": 3}
    p.reset(total=20)
    assert p.current == 0
    assert p.total == 20
    assert p.current_code == ""
    assert p.success == 0
    assert p.failed == 0
    assert p.source_stats == {}
    assert p.current_source == "AV-WIKI"
    assert p.current_phase == 1


def test_reset_resets_start_time():
    p = SearchProgressInfo()
    old_start = p.start_time - 100
    p.start_time = old_start
    p.reset(10)
    assert p.start_time >= old_start + 100


# ──────────────────────────────
# update() 行為驗證
# ──────────────────────────────


def test_update_increments_current_by_default():
    p = _prog()
    p.update(code="STARS-001", is_success=True)
    assert p.current == 1


def test_update_with_increment_false_does_not_increment():
    p = _prog()
    p.update(code="STARS-001", is_success=True, increment=False)
    assert p.current == 0  # 關鍵：increment=False 不應增加計數


def test_update_source_stat_uses_passed_source():
    """成功時應以傳入的 source 為 key，不是 current_source。"""
    p = _prog()
    p.update(is_success=True, source="JAVDB")
    assert p.source_stats.get("JAVDB") == 1
    assert "AV-WIKI" not in p.source_stats


def test_update_source_stat_falls_back_to_current_source():
    """source=None 時應 fallback 使用 current_source 作為 key。"""
    p = _prog()
    p.current_source = "AV-WIKI"
    p.update(is_success=True, source=None)
    assert p.source_stats.get("AV-WIKI") == 1


def test_update_failure_increments_failed():
    p = _prog()
    p.update(is_success=False)
    assert p.failed == 1
    assert p.success == 0
    assert p.source_stats == {}  # 失敗不應記錄來源統計


def test_update_source_does_not_update_stats_when_failure():
    """失敗時即使有 source 也不記錄來源統計。"""
    p = _prog()
    p.update(is_success=False, source="JAVDB")
    assert p.source_stats == {}


def test_update_multiple_sources_accumulate():
    p = _prog()
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="JAVDB")
    assert p.source_stats["AV-WIKI"] == 2
    assert p.source_stats["JAVDB"] == 1


def test_update_is_success_none_does_nothing_to_counts():
    p = _prog()
    p.update(code="STARS-001", is_success=None)
    assert p.success == 0
    assert p.failed == 0


# ──────────────────────────────
# Thread safety - 並發更新不應遺失計數
# ──────────────────────────────


def test_concurrent_update_is_thread_safe():
    """並發更新：所有 increment 都應被記錄，不能有 race condition。"""
    p = SearchProgressInfo()
    p.reset(total=200)
    threads = [
        threading.Thread(target=lambda: p.update(is_success=True, source="AV-WIKI"))
        for _ in range(100)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 100 個 update 每個都應被記錄
    assert p.current == 100
    assert p.success == 100
    assert p.source_stats.get("AV-WIKI") == 100


# ──────────────────────────────
# set_phase()
# ──────────────────────────────


def test_set_phase_updates_fields():
    p = _prog()
    p.set_phase(2, "JAVDB", total_phases=3)
    assert p.current_phase == 2
    assert p.phase_name == "JAVDB"
    assert p.total_phases == 3


def test_set_phase_without_total_phases_keeps_existing():
    p = _prog()
    p.total_phases = 5
    p.set_phase(2, "JAVDB")  # total_phases=None
    assert p.total_phases == 5  # 不應被覆蓋


# ──────────────────────────────
# Properties
# ──────────────────────────────


def test_elapsed_seconds_is_positive():
    p = _prog()
    time.sleep(0.01)
    assert p.elapsed_seconds > 0


def test_items_per_second_zero_when_no_items():
    p = _prog()
    assert p.items_per_second == 0.0


def test_items_per_second_zero_when_current_is_zero():
    """current=0 時應回 0.0，不論 elapsed 為何。"""
    p = _prog()
    p.current = 0
    assert p.items_per_second == 0.0


def test_estimated_remaining_seconds_zero_when_speed_zero():
    p = _prog()
    assert p.estimated_remaining_seconds == 0.0


def test_estimated_remaining_seconds_reasonable():
    p = _prog()
    p.start_time = time.time() - 10  # 已過 10 秒
    p.current = 5
    p.total = 10
    remaining = p.estimated_remaining_seconds
    # 速度 0.5/s，還有 5 個 → 約 10 秒
    assert 8 < remaining < 12


def test_success_rate_zero_when_no_processed():
    p = _prog()
    assert p.success_rate == 0.0


def test_success_rate_calculation():
    p = _prog()
    p.update(is_success=True)
    p.update(is_success=True)
    p.update(is_success=False)
    assert abs(p.success_rate - 66.67) < 0.1


def test_completion_rate_zero_when_total_zero():
    p = SearchProgressInfo()
    p.reset(total=0)
    assert p.completion_rate == 0.0


def test_completion_rate_calculation():
    p = _prog(total=10)
    p.update()
    p.update()
    assert p.completion_rate == 20.0


# ──────────────────────────────
# format_time()
# ──────────────────────────────


def test_format_time_negative():
    p = _prog()
    assert p.format_time(-1) == "--"


def test_format_time_zero():
    p = _prog()
    assert p.format_time(0) == "--"


def test_format_time_seconds():
    p = _prog()
    assert p.format_time(45) == "45s"


def test_format_time_minutes():
    p = _prog()
    result = p.format_time(150)  # 2:30
    assert result == "2:30"


def test_format_time_minutes_zero_seconds():
    p = _prog()
    result = p.format_time(120)  # 2:00
    assert result == "2:00"


def test_format_time_hours():
    p = _prog()
    result = p.format_time(3900)  # 1:05:00
    assert result == "1:05:00"


def test_format_time_exactly_one_hour():
    p = _prog()
    result = p.format_time(3600)
    assert result == "1:00:00"


# ──────────────────────────────
# format_progress()
# ──────────────────────────────


def test_format_progress_basic_structure():
    p = _prog(total=10)
    p.current_code = "STARS-001"
    result = p.format_progress()
    assert "[0/10]" in result
    assert "STARS-001" in result


def test_format_progress_hides_stats_when_current_zero():
    p = _prog(total=10)
    result = p.format_progress()
    assert "✅" not in result  # 尚未開始，不顯示成功計數


def test_format_progress_shows_stats_when_current_nonzero():
    p = _prog(total=10)
    p.update(is_success=True, source="AV-WIKI")
    result = p.format_progress()
    assert "✅" in result
    assert "❌" in result


def test_format_progress_hides_speed_when_zero():
    """速度=0 時不顯示速度（避免顯示 0.0/s）。"""
    p = _prog(total=10)
    p.start_time = time.time() + 9999  # 強制 elapsed=0
    result = p.format_progress()
    assert "🚀" not in result


def test_format_progress_shows_source():
    p = _prog()
    p.current_source = "JAVDB"
    result = p.format_progress()
    assert "JAVDB" in result


# ──────────────────────────────
# format_summary()
# ──────────────────────────────


def test_format_summary_shows_total():
    p = _prog(total=51)
    result = p.format_summary()
    assert "51" in result


def test_format_summary_shows_success_fail_percentages():
    p = _prog(total=4)
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="JAVDB")
    p.update(is_success=False)
    result = p.format_summary()
    assert "75.0%" in result  # 成功率
    assert "25.0%" in result  # 失敗率


def test_format_summary_shows_source_stats():
    p = _prog(total=3)
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="AV-WIKI")
    p.update(is_success=True, source="JAVDB")
    result = p.format_summary()
    assert "AV-WIKI" in result
    assert "JAVDB" in result


def test_format_summary_no_source_stats_skips_section():
    p = _prog(total=2)
    p.update(is_success=False)
    p.update(is_success=False)
    result = p.format_summary()
    assert "📡 各來源貢獻" not in result


def test_format_summary_no_processed_skips_success_fail():
    """沒有任何處理紀錄時不應出現 ✅ ❌。"""
    p = _prog(total=10)
    result = p.format_summary()
    # total_processed = 0，不應顯示成功/失敗區塊
    assert "✅" not in result
    assert "❌" not in result


# ──────────────────────────────
# to_dict()
# ──────────────────────────────


def test_to_dict_has_required_keys():
    p = _prog(total=5)
    d = p.to_dict()
    for key in ("current", "total", "success", "failed", "elapsed_seconds",
                "items_per_second", "success_rate", "current_source", "source_stats"):
        assert key in d, f"缺少 key: {key}"


def test_to_dict_source_stats_is_copy():
    """to_dict 回傳的 source_stats 應是副本，修改不應影響原始資料。"""
    p = _prog()
    p.update(is_success=True, source="AV-WIKI")
    d = p.to_dict()
    d["source_stats"]["AV-WIKI"] = 999
    assert p.source_stats["AV-WIKI"] == 1  # 原始資料不應被修改
