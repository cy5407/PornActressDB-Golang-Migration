"""
測試 Go 資料庫橋接層
"""

import sys
import codecs
from pathlib import Path

# Windows 編碼修正
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# 新增專案路徑
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.go_bridge import (
    db_get_video,
    db_get_stats,
    db_list_videos,
    get_bridge,
)

def main():
    print("🔍 測試 Go 資料庫橋接層\n")

    # 檢查 bridge 是否可用
    bridge = get_bridge()
    if not bridge.is_available:
        print("❌ Go CLI 不可用")
        return

    print(f"✅ Go CLI 可用: {bridge.exe_path}\n")

    # 測試 1: 取得統計
    print("=" * 50)
    print("測試 1: db_get_stats()")
    print("=" * 50)
    stats = db_get_stats()
    if stats:
        print(f"✅ 成功取得統計:")
        print(f"   - 影片數: {stats.get('video_count')}")
        print(f"   - 女優數: {stats.get('actress_count')}")
        print(f"   - 關聯數: {stats.get('link_count')}")
        print(f"   - Schema 版本: {stats.get('schema_version')}")
    else:
        print("❌ 無法取得統計")

    print()

    # 測試 2: 取得影片
    print("=" * 50)
    print("測試 2: db_get_video('STARS-707')")
    print("=" * 50)
    video = db_get_video("STARS-707")
    if video:
        print(f"✅ 成功取得影片:")
        print(f"   - 番號: {video.get('code')}")
        print(f"   - 片商: {video.get('studio')}")
        print(f"   - 女優: {video.get('actresses')}")
        print(f"   - 狀態: {video.get('search_status')}")
    else:
        print("❌ 無法取得影片")

    print()

    # 測試 3: 列出影片 (前 10 筆)
    print("=" * 50)
    print("測試 3: db_list_videos() (前 10 筆)")
    print("=" * 50)
    codes = db_list_videos()
    if codes:
        print(f"✅ 成功列出 {len(codes)} 部影片")
        print(f"   前 10 筆: {codes[:10]}")
    else:
        print("❌ 無法列出影片")

    print()

    # 測試 4: 效能測試
    print("=" * 50)
    print("測試 4: 效能測試 (取得 100 部影片)")
    print("=" * 50)
    import time

    test_codes = codes[:100] if len(codes) >= 100 else codes
    start_time = time.time()

    success_count = 0
    for code in test_codes:
        video = db_get_video(code)
        if video:
            success_count += 1

    elapsed = time.time() - start_time
    avg_time = elapsed / len(test_codes) * 1000  # ms

    print(f"✅ 完成:")
    print(f"   - 測試數量: {len(test_codes)} 部")
    print(f"   - 成功: {success_count} 部")
    print(f"   - 總耗時: {elapsed:.3f} 秒")
    print(f"   - 平均耗時: {avg_time:.2f} ms/部")

    print()
    print("=" * 50)
    print("✅ 所有測試完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
