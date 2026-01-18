"""
Scanner 整合測試

測試 UnifiedFileScanner 的以下功能：
1. Python 原生掃描模式
2. Go CLI 加速模式 (需要 classifier.exe)
3. Fallback 機制
4. scan_with_codes 功能
"""

import logging
import tempfile
import time
from pathlib import Path

from src.utils.scanner import UnifiedFileScanner

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_files(temp_dir: Path, count: int = 10) -> list[Path]:
    """建立測試用影片檔案 (空檔案)"""
    files = []
    test_codes = [
        "SONE-001", "SSIS-123", "MIDV-456", "IPX-789",
        "CAWD-100", "FSDSS-200", "MIDE-300", "SSNI-400",
        "PRED-500", "MEYD-600"
    ]

    for i in range(min(count, len(test_codes))):
        code = test_codes[i]
        file_path = temp_dir / f"{code}.mp4"
        file_path.touch()
        files.append(file_path)

    # 建立子目錄測試檔案
    sub_dir = temp_dir / "subdir"
    sub_dir.mkdir(exist_ok=True)
    sub_file = sub_dir / "STARS-700.mp4"
    sub_file.touch()
    files.append(sub_file)

    return files


def test_python_scanner():
    """測試 Python 原生掃描模式"""
    logger.info("=" * 60)
    logger.info("測試 1: Python 原生掃描")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_files = create_test_files(temp_path)

        scanner = UnifiedFileScanner(use_go=False)

        # 測試遞迴掃描
        start = time.perf_counter()
        results = scanner.scan_directory(temp_dir, recursive=True)
        elapsed = time.perf_counter() - start

        logger.info(f"✅ 遞迴掃描完成: {len(results)} 個檔案 ({elapsed * 1000:.2f}ms)")
        assert len(results) == len(test_files), f"預期 {len(test_files)} 個檔案，實際 {len(results)}"

        # 測試非遞迴掃描
        results_flat = scanner.scan_directory(temp_dir, recursive=False)
        logger.info(f"✅ 非遞迴掃描完成: {len(results_flat)} 個檔案")
        assert len(results_flat) == len(test_files) - 1, "非遞迴不應包含子目錄檔案"

    logger.info("✅ Python 原生掃描測試通過")


def test_go_scanner_availability():
    """測試 Go CLI 掃描器可用性檢查"""
    logger.info("=" * 60)
    logger.info("測試 2: Go CLI 可用性檢查")
    logger.info("=" * 60)

    scanner = UnifiedFileScanner(use_go=True)

    if scanner.go_bridge and scanner.go_bridge.is_available:
        logger.info("✅ Go CLI 可用")
    else:
        logger.info("⚠️ Go CLI 不可用（正常，WSL 環境或缺少 exe）")
        logger.info("   Fallback 機制: 自動切換到 Python 掃描")

    # 驗證 fallback 行為
    assert scanner.use_go == (scanner.go_bridge is not None and scanner.go_bridge.is_available)

    logger.info("✅ 可用性檢查測試通過")


def test_fallback_mechanism():
    """測試 Fallback 機制"""
    logger.info("=" * 60)
    logger.info("測試 3: Fallback 機制")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_files = create_test_files(temp_path)

        # 強制使用 Go 模式，但提供錯誤的 exe 路徑
        scanner = UnifiedFileScanner(
            use_go=True,
            go_exe_path="/nonexistent/path/classifier.exe"
        )

        # 由於 Go 不可用，應該自動切換到 Python
        results = scanner.scan_directory(temp_dir, recursive=True)

        logger.info(f"✅ Fallback 掃描完成: {len(results)} 個檔案")
        assert len(results) == len(test_files), "Fallback 應該能正常掃描"

        # 驗證已切換到 Python 模式
        assert scanner.use_go is False, "應該已切換到 Python 模式"

    logger.info("✅ Fallback 機制測試通過")


def test_scan_with_codes():
    """測試 scan_with_codes 功能"""
    logger.info("=" * 60)
    logger.info("測試 4: scan_with_codes 功能")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_files = create_test_files(temp_path)

        # Python 模式下的 scan_with_codes（不提取番號）
        scanner = UnifiedFileScanner(use_go=False)
        results = scanner.scan_with_codes(temp_dir)

        logger.info(f"✅ scan_with_codes 完成: {len(results)} 個檔案")

        # 驗證結果格式
        for result in results:
            assert "path" in result, "結果應包含 path"
            assert "code" in result, "結果應包含 code"

        # Python 模式下 code 為空（因為不提取）
        if not scanner.use_go:
            logger.info("   Python 模式: code 欄位為空（預期行為）")

    logger.info("✅ scan_with_codes 測試通過")


def test_from_config():
    """測試從設定檔建立掃描器"""
    logger.info("=" * 60)
    logger.info("測試 5: from_config 工廠方法")
    logger.info("=" * 60)

    # 建立模擬的 config 物件
    class MockConfig:
        def getboolean(self, section, key, fallback=None):
            if section == "go_integration" and key == "enabled":
                return False
            return fallback

        def getint(self, section, key, fallback=None):
            if section == "go_integration" and key == "scan_workers":
                return 8
            return fallback

        def get(self, section, key, fallback=None):
            return fallback

    config = MockConfig()
    scanner = UnifiedFileScanner.from_config(config)

    assert scanner.use_go is False, "應該根據設定禁用 Go"
    assert scanner.go_workers == 8, "應該使用設定的 workers 數"

    logger.info("✅ from_config 測試通過")


def test_performance_comparison():
    """效能對比測試（僅在檔案數量較大時有意義）"""
    logger.info("=" * 60)
    logger.info("測試 6: 掃描效能測試")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 建立較多測試檔案
        for i in range(100):
            (temp_path / f"TEST-{i:03d}.mp4").touch()

        # 建立多層子目錄
        for level in range(3):
            sub_dir = temp_path / f"level_{level}"
            sub_dir.mkdir(exist_ok=True)
            for i in range(20):
                (sub_dir / f"SUB-{level}-{i:02d}.mkv").touch()

        scanner = UnifiedFileScanner(use_go=False)

        # 多次測試取平均
        times = []
        for _ in range(3):
            start = time.perf_counter()
            results = scanner.scan_directory(temp_dir, recursive=True)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        total_files = len(results)

        logger.info(f"✅ 掃描 {total_files} 個檔案")
        logger.info(f"   平均時間: {avg_time * 1000:.2f}ms")
        logger.info(f"   每檔案: {avg_time / total_files * 1000:.3f}ms")

    logger.info("✅ 效能測試完成")


def run_all_tests():
    """執行所有測試"""
    logger.info("\n" + "=" * 60)
    logger.info("🚀 開始 Scanner 整合測試")
    logger.info("=" * 60 + "\n")

    tests = [
        ("Python 原生掃描", test_python_scanner),
        ("Go CLI 可用性", test_go_scanner_availability),
        ("Fallback 機制", test_fallback_mechanism),
        ("scan_with_codes", test_scan_with_codes),
        ("from_config", test_from_config),
        ("效能測試", test_performance_comparison),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ {name} 測試失敗: {e}")
            failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"📊 測試結果: {passed} 通過, {failed} 失敗")
    logger.info("=" * 60)

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
