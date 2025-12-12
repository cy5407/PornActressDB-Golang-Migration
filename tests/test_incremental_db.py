"""
測試 IncrementalJSONDB 增量儲存機制
"""

import logging
import time

from src.models.incremental_json_database import IncrementalJSONDB
from src.models.json_database import JSONDBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_incremental_db():
    """測試增量資料庫的基本功能"""

    logger.info("=" * 60)
    logger.info("測試增量 JSON 資料庫")
    logger.info("=" * 60)

    # 初始化增量資料庫
    db = IncrementalJSONDB("data/json_db")

    # 顯示初始統計
    stats = db.get_stats()
    logger.info("\n📊 初始統計:")
    logger.info(f"  - 總影片數: {stats['total_videos']}")
    logger.info(f"  - Journal 記錄數: {stats['journal_size']}")
    logger.info(f"  - Dirty 影片: {stats['dirty_videos']}")
    logger.info(f"  - 需要合併: {stats['needs_compact']}")

    # 取得一部測試影片
    test_video = None
    all_videos = db.base_db.get_all_videos()
    if all_videos:
        test_video = all_videos[0]
        test_code = test_video.get("code", test_video.get("id", "UNKNOWN"))

    if not test_video:
        logger.error("❌ 找不到測試影片")
        return

    logger.info(f"\n🎬 測試影片: {test_code}")
    logger.info(f"  原始標題: {test_video.get('title', 'N/A')}")

    # 測試 1: 快速更新（寫入 journal）
    logger.info("\n" + "=" * 60)
    logger.info("測試 1: 快速更新（寫入 journal）")
    logger.info("=" * 60)

    start = time.perf_counter()
    for i in range(10):
        db.update_video(
            test_code, {"title": f"測試標題 {i + 1}", "test_field": f"測試值 {i + 1}"}
        )
    elapsed = time.perf_counter() - start

    logger.info(
        f"✅ 完成 10 次快速更新: {elapsed * 1000:.2f}ms ({elapsed / 10 * 1000:.2f}ms/次)"
    )

    # 顯示更新後統計
    stats = db.get_stats()
    logger.info("\n📊 更新後統計:")
    logger.info(f"  - Journal 記錄數: {stats['journal_size']}")
    logger.info(f"  - Dirty 影片: {stats['dirty_videos']}")

    # 測試 2: 合併 journal
    logger.info("\n" + "=" * 60)
    logger.info("測試 2: 合併 journal 到主檔案")
    logger.info("=" * 60)

    start = time.perf_counter()
    db.compact()
    elapsed = time.perf_counter() - start

    logger.info(f"✅ Journal 合併完成: {elapsed * 1000:.2f}ms")

    # 顯示合併後統計
    stats = db.get_stats()
    logger.info("\n📊 合併後統計:")
    logger.info(f"  - Journal 記錄數: {stats['journal_size']}")
    logger.info(f"  - Dirty 影片: {stats['dirty_videos']}")

    # 測試 3: 效能比較
    logger.info("\n" + "=" * 60)
    logger.info("測試 3: 效能比較（增量 vs 標準）")
    logger.info("=" * 60)

    # 標準方式（完整重寫）
    standard_db = JSONDBManager("data/json_db")

    logger.info("\n標準方式（完整 JSON 重寫）:")
    start = time.perf_counter()
    for i in range(10):
        video = standard_db.get_video_info(test_code)
        if video:
            video["title"] = f"標準測試 {i + 1}"
            standard_db.data["videos"][test_code] = video
            standard_db._save_all_data(standard_db.data)
    standard_elapsed = time.perf_counter() - start

    logger.info(
        f"  完成 10 次更新: {standard_elapsed * 1000:.2f}ms ({standard_elapsed / 10 * 1000:.2f}ms/次)"
    )

    # 增量方式（journal append）
    logger.info("\n增量方式（journal append）:")
    start = time.perf_counter()
    for i in range(10):
        db.update_video(test_code, {"title": f"增量測試 {i + 1}"})
    incremental_elapsed = time.perf_counter() - start

    logger.info(
        f"  完成 10 次更新: {incremental_elapsed * 1000:.2f}ms ({incremental_elapsed / 10 * 1000:.2f}ms/次)"
    )

    # 計算加速比
    speedup = standard_elapsed / incremental_elapsed
    logger.info(f"\n🚀 效能提升: {speedup:.1f}x 加速")

    # 清理：合併最後的 journal
    db.compact()

    logger.info("\n" + "=" * 60)
    logger.info("✅ 測試完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_incremental_db()
