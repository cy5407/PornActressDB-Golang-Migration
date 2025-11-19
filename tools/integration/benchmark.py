# -*- coding: utf-8 -*-
"""
Python 效能測試腳本
"""
import os
import time
import shutil
from pathlib import Path
import threading

from src.services.classifier_core import UnifiedClassifierCore
from src.models.config import ConfigManager

def create_dummy_files(directory: Path, num_files: int):
    """建立測試用的虛擬影片檔案"""
    directory.mkdir(exist_ok=True)
    for i in range(num_files):
        # 使用常見的番號格式
        code = f"TEST-{i:03d}"
        file_path = directory / f"{code}.mp4"
        file_path.touch()

def main():
    """主函式"""
    num_files = 10  # 測試檔案數量
    temp_dir = Path("temp_benchmark")

    print("🐍 Python 效能測試")
    print("="*30)
    print(f"測試檔案數量: {num_files}")
    print(f"測試目錄: {temp_dir.resolve()}")
    print("-"*30)

    # 建立虛擬檔案
    print("1. 正在建立虛擬檔案...")
    create_dummy_files(temp_dir, num_files)
    print(f"✅ {num_files} 個虛擬檔案已建立")

    # 初始化核心元件
    print("\n2. 正在初始化核心元件...")
    config_manager = ConfigManager()
    core = UnifiedClassifierCore(config_manager)
    print("✅ 核心元件已初始化")

    # 執行智慧搜尋並分類
    print("\n3. 正在執行智慧搜尋並分類...")
    stop_event = threading.Event()
    start_time = time.time()
    core.smart_search_and_move(str(temp_dir), stop_event=stop_event, use_full_search=True)
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"✅ 智慧搜尋並分類完成")

    # 顯示結果
    print("\n📊 測試結果")
    print("-"*30)
    print(f"總執行時間: {execution_time:.2f} 秒")
    print(f"平均每個檔案處理時間: {execution_time / num_files:.4f} 秒")

    # 清理虛擬檔案
    print("\n4. 正在清理測試資料...")
    shutil.rmtree(temp_dir)
    print("✅ 清理完成")

if __name__ == "__main__":
    main()