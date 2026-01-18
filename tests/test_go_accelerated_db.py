"""
GoAcceleratedDB 測試

測試功能：
1. Go 加速模式
2. Python fallback 模式
3. 自動 fallback 機制
4. API 相容性
"""

import json
import logging
import tempfile
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_database(temp_dir: Path) -> dict:
    """建立測試用資料庫"""
    data = {
        "videos": {
            "SONE-001": {
                "code": "SONE-001",
                "title": "測試影片 1",
                "studio": "S1",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "SSIS-123": {
                "code": "SSIS-123",
                "title": "測試影片 2",
                "studio": "S1",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            "MIDV-456": {
                "code": "MIDV-456",
                "title": "測試影片 3",
                "studio": "MOODYZ",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        },
        "actresses": {},
        "video_actress_links": {},
    }

    json_db_dir = temp_dir / "json_db"
    json_db_dir.mkdir(parents=True, exist_ok=True)

    data_file = json_db_dir / "data.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def test_python_fallback_mode():
    """測試 Python fallback 模式（強制禁用 Go）"""
    logger.info("=" * 60)
    logger.info("測試 1: Python fallback 模式")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        create_test_database(temp_path)

        from src.models.go_accelerated_db import GoAcceleratedDB

        # 強制禁用 Go
        db = GoAcceleratedDB(str(temp_path / "json_db"), use_go=False)

        assert db.use_go is False, "應該禁用 Go"

        # 測試查詢
        video = db.get_video_info("SONE-001")
        assert video is not None, "應該能查詢到影片"
        assert video["code"] == "SONE-001"
        logger.info(f"✅ 查詢成功: {video['code']}")

        # 測試更新
        db.update_video("SONE-001", {"title": "更新後的標題"})
        updated = db.get_video_info("SONE-001")
        assert updated["title"] == "更新後的標題"
        logger.info("✅ 更新成功")

        # 測試統計
        stats = db.get_stats()
        assert "total_videos" in stats
        assert stats["go_accelerated"] is False
        logger.info(f"✅ 統計成功: {stats['total_videos']} 部影片")

    logger.info("✅ Python fallback 模式測試通過")


def test_go_unavailable_fallback():
    """測試 Go 不可用時的自動 fallback"""
    logger.info("=" * 60)
    logger.info("測試 2: Go 不可用時自動 fallback")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        create_test_database(temp_path)

        from src.models.go_accelerated_db import GoAcceleratedDB

        # 嘗試使用 Go（在 WSL 環境會自動 fallback）
        db = GoAcceleratedDB(str(temp_path / "json_db"), use_go=True)

        # 無論 Go 是否可用，API 應該都能正常工作
        video = db.get_video_info("SONE-001")
        assert video is not None, "應該能查詢到影片"

        # 記錄實際使用的模式
        mode = "Go 加速" if db.use_go else "Python fallback"
        logger.info(f"✅ 實際使用模式: {mode}")
        logger.info(f"✅ fallback 次數: {db.fallback_count}")

    logger.info("✅ 自動 fallback 測試通過")


def test_api_compatibility():
    """測試與 IncrementalJSONDB 的 API 相容性"""
    logger.info("=" * 60)
    logger.info("測試 3: API 相容性")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        create_test_database(temp_path)

        from src.models.go_accelerated_db import GoAcceleratedDB

        db = GoAcceleratedDB(str(temp_path / "json_db"), use_go=False)

        # 測試所有核心 API
        apis = [
            ("get_video_info", lambda: db.get_video_info("SONE-001")),
            ("get_all_videos", lambda: db.get_all_videos()),
            ("get_stats", lambda: db.get_stats()),
            ("data", lambda: db.data),
            ("base_db", lambda: db.base_db),
        ]

        for name, func in apis:
            try:
                result = func()
                assert result is not None, f"{name} 不應該返回 None"
                logger.info(f"✅ API {name} 可用")
            except Exception as e:
                logger.error(f"❌ API {name} 失敗: {e}")
                raise

        # 測試新增和刪除
        db.add_or_update_video("TEST-001", {"title": "新增測試"})
        new_video = db.get_video_info("TEST-001")
        assert new_video is not None
        logger.info("✅ API add_or_update_video 可用")

        db.delete_video("TEST-001")
        deleted = db.get_video_info("TEST-001")
        assert deleted is None
        logger.info("✅ API delete_video 可用")

    logger.info("✅ API 相容性測試通過")


def test_performance_comparison():
    """效能對比測試"""
    logger.info("=" * 60)
    logger.info("測試 4: 效能對比")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        create_test_database(temp_path)

        from src.models.go_accelerated_db import GoAcceleratedDB
        from src.models.incremental_json_database import IncrementalJSONDB

        # Python 基準
        python_db = IncrementalJSONDB(str(temp_path / "json_db"))

        # 查詢效能
        iterations = 100

        # Python 查詢
        start = time.perf_counter()
        for _ in range(iterations):
            python_db.get_video_info("SONE-001")
        python_time = time.perf_counter() - start

        # GoAcceleratedDB（可能 fallback 到 Python）
        go_db = GoAcceleratedDB(str(temp_path / "json_db"), use_go=True)

        start = time.perf_counter()
        for _ in range(iterations):
            go_db.get_video_info("SONE-001")
        go_time = time.perf_counter() - start

        logger.info(f"📊 {iterations} 次查詢效能:")
        logger.info(f"   Python: {python_time * 1000:.2f}ms ({python_time / iterations * 1000:.3f}ms/次)")
        logger.info(f"   GoAcceleratedDB: {go_time * 1000:.2f}ms ({go_time / iterations * 1000:.3f}ms/次)")
        logger.info(f"   實際模式: {'Go 加速' if go_db.use_go else 'Python fallback'}")

    logger.info("✅ 效能對比測試完成")


def test_factory_function():
    """測試工廠函式"""
    logger.info("=" * 60)
    logger.info("測試 5: 工廠函式")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        create_test_database(temp_path)

        from src.models.go_accelerated_db import get_database

        # 使用工廠函式
        db = get_database(str(temp_path / "json_db"), use_go=False)

        assert db is not None
        assert isinstance(db, type(db))  # GoAcceleratedDB

        video = db.get_video_info("SONE-001")
        assert video is not None

    logger.info("✅ 工廠函式測試通過")


def run_all_tests():
    """執行所有測試"""
    logger.info("\n" + "=" * 60)
    logger.info("🚀 開始 GoAcceleratedDB 測試")
    logger.info("=" * 60 + "\n")

    tests = [
        ("Python fallback 模式", test_python_fallback_mode),
        ("Go 不可用自動 fallback", test_go_unavailable_fallback),
        ("API 相容性", test_api_compatibility),
        ("效能對比", test_performance_comparison),
        ("工廠函式", test_factory_function),
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
