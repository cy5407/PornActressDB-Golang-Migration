"""
片商識別器整合測試

測試功能：
1. Python 原生模式
2. Go 加速模式（如可用）
3. 自動 fallback 機制
4. 批次識別
5. 別名標準化
6. API 相容性
"""

import logging
import time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_python_fallback_mode():
    """測試 Python fallback 模式（強制禁用 Go）"""
    logger.info("=" * 60)
    logger.info("測試 1: Python fallback 模式")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    # 強制禁用 Go
    identifier = GoAcceleratedStudioIdentifier(use_go=False)

    assert identifier.use_go is False, "應該禁用 Go"

    # 測試識別
    test_cases = [
        ("SONE-001", "S1"),
        ("SSIS-123", "S1"),
        ("MIDV-456", "MOODYZ"),
        ("IPX-789", "PREMIUM"),
        ("FSDSS-100", "FALENO"),
        ("UNKNOWN-999", "UNKNOWN"),
    ]

    for code, expected in test_cases:
        result = identifier.identify_studio(code)
        assert result == expected, f"{code} 應該是 {expected}，但得到 {result}"
        logger.info(f"✅ {code} -> {result}")

    logger.info("✅ Python fallback 模式測試通過")


def test_go_availability():
    """測試 Go CLI 可用性檢查"""
    logger.info("=" * 60)
    logger.info("測試 2: Go CLI 可用性檢查")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    # 嘗試使用 Go
    identifier = GoAcceleratedStudioIdentifier(use_go=True)

    if identifier.use_go:
        logger.info("✅ Go CLI 可用，使用加速模式")
    else:
        logger.info("⚠️ Go CLI 不可用（正常，WSL 環境或缺少 exe）")
        logger.info("   Fallback 機制: 自動切換到 Python")

    # 無論 Go 是否可用，API 都應該正常工作
    result = identifier.identify_studio("SONE-001")
    assert result == "S1", f"應該識別為 S1，但得到 {result}"

    logger.info("✅ 可用性檢查測試通過")


def test_batch_identification():
    """測試批次識別功能"""
    logger.info("=" * 60)
    logger.info("測試 3: 批次識別功能")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    identifier = GoAcceleratedStudioIdentifier(use_go=True)

    codes = ["SONE-001", "SSIS-123", "MIDV-456", "IPX-789", "FSDSS-100"]
    expected = {
        "SONE-001": "S1",
        "SSIS-123": "S1",
        "MIDV-456": "MOODYZ",
        "IPX-789": "PREMIUM",
        "FSDSS-100": "FALENO",
    }

    results = identifier.identify_studios_batch(codes)

    for code, studio in expected.items():
        assert results.get(code) == studio, f"{code} 應該是 {studio}，但得到 {results.get(code)}"
        logger.info(f"✅ {code} -> {results.get(code)}")

    logger.info("✅ 批次識別測試通過")


def test_normalize_studio_name():
    """測試片商名稱標準化"""
    logger.info("=" * 60)
    logger.info("測試 4: 片商名稱標準化")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    identifier = GoAcceleratedStudioIdentifier(use_go=True)

    # 測試別名解析
    test_cases = [
        ("S1 NO.1 STYLE", None, "S1"),
        ("MOODYZ DIVA", None, "MOODYZ"),
        ("Premium", None, "PREMIUM"),
        ("エスワン", None, "S1"),  # 日文名稱
        # 使用番號優先判斷
        ("Random Studio", "SONE-001", "S1"),
        ("Random Studio", "MIDV-456", "MOODYZ"),
    ]

    for studio_name, video_code, expected in test_cases:
        result = identifier.normalize_studio_name(studio_name, video_code)
        assert result == expected, f"({studio_name}, {video_code}) 應該是 {expected}，但得到 {result}"
        logger.info(f"✅ ({studio_name}, {video_code}) -> {result}")

    logger.info("✅ 名稱標準化測試通過")


def test_api_compatibility():
    """測試與 StudioIdentifier 的 API 相容性"""
    logger.info("=" * 60)
    logger.info("測試 5: API 相容性")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier
    from src.models.studio import StudioIdentifier

    go_identifier = GoAcceleratedStudioIdentifier(use_go=False)
    py_identifier = StudioIdentifier()

    # 比較所有核心 API
    test_codes = ["SONE-001", "SSIS-123", "MIDV-456", "UNKNOWN-999"]

    for code in test_codes:
        go_result = go_identifier.identify_studio(code)
        py_result = py_identifier.identify_studio(code)
        assert go_result == py_result, f"{code}: Go={go_result}, Python={py_result}"
        logger.info(f"✅ {code}: Go={go_result}, Python={py_result}")

    # 比較屬性
    assert len(go_identifier.studio_patterns) == len(py_identifier.studio_patterns)
    assert len(go_identifier.code_to_studio) == len(py_identifier.code_to_studio)
    logger.info(f"✅ studio_patterns: {len(go_identifier.studio_patterns)} 個片商")
    logger.info(f"✅ code_to_studio: {len(go_identifier.code_to_studio)} 個前綴")

    logger.info("✅ API 相容性測試通過")


def test_performance_comparison():
    """效能對比測試"""
    logger.info("=" * 60)
    logger.info("測試 6: 效能對比")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier
    from src.models.studio import StudioIdentifier

    # Python 基準
    py_identifier = StudioIdentifier()

    # 測試資料
    test_codes = [f"SONE-{i:03d}" for i in range(100)]
    iterations = 100

    # Python 效能
    start = time.perf_counter()
    for _ in range(iterations):
        for code in test_codes:
            py_identifier.identify_studio(code)
    python_time = time.perf_counter() - start

    # GoAccelerated 效能（可能 fallback 到 Python）
    go_identifier = GoAcceleratedStudioIdentifier(use_go=True)

    start = time.perf_counter()
    for _ in range(iterations):
        for code in test_codes:
            go_identifier.identify_studio(code)
    go_time = time.perf_counter() - start

    total_ops = iterations * len(test_codes)

    logger.info(f"📊 {total_ops} 次識別效能:")
    logger.info(f"   Python: {python_time * 1000:.2f}ms ({python_time / total_ops * 1000000:.2f}μs/次)")
    logger.info(f"   GoAccelerated: {go_time * 1000:.2f}ms ({go_time / total_ops * 1000000:.2f}μs/次)")
    logger.info(f"   實際模式: {'Go 加速' if go_identifier.use_go else 'Python fallback'}")

    if go_identifier.use_go:
        speedup = python_time / go_time
        logger.info(f"   效能提升: {speedup:.1f}x")

    logger.info("✅ 效能對比測試完成")


def test_get_stats():
    """測試統計資訊"""
    logger.info("=" * 60)
    logger.info("測試 7: 統計資訊")
    logger.info("=" * 60)

    from src.models.go_accelerated_studio import GoAcceleratedStudioIdentifier

    identifier = GoAcceleratedStudioIdentifier(use_go=False)

    # 執行一些操作
    identifier.identify_studio("SONE-001")
    identifier.identify_studio("SSIS-123")

    stats = identifier.get_stats()

    assert "use_go" in stats
    assert "fallback_count" in stats
    assert "studio_count" in stats
    assert "prefix_count" in stats

    logger.info(f"✅ 統計資訊: {stats}")

    logger.info("✅ 統計資訊測試通過")


def run_all_tests():
    """執行所有測試"""
    logger.info("\n" + "=" * 60)
    logger.info("🚀 開始片商識別器整合測試")
    logger.info("=" * 60 + "\n")

    tests = [
        ("Python fallback 模式", test_python_fallback_mode),
        ("Go CLI 可用性", test_go_availability),
        ("批次識別", test_batch_identification),
        ("名稱標準化", test_normalize_studio_name),
        ("API 相容性", test_api_compatibility),
        ("效能對比", test_performance_comparison),
        ("統計資訊", test_get_stats),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ {name} 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"📊 測試結果: {passed} 通過, {failed} 失敗")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
