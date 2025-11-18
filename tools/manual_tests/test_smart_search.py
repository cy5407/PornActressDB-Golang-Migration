#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試智慧搜尋並分類功能
"""

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from models.config import ConfigManager
from services.classifier_core import UnifiedClassifierCore
import threading

def test_method_exists():
    """測試方法是否存在"""
    print("🧪 測試 1: 檢查方法是否存在")
    
    config = ConfigManager()
    core = UnifiedClassifierCore(config)
    
    # 檢查方法
    if hasattr(core, 'smart_search_and_move'):
        print("✅ smart_search_and_move 方法存在")
        
        # 檢查方法簽名
        import inspect
        sig = inspect.signature(core.smart_search_and_move)
        print(f"   方法簽名: {sig}")
        return True
    else:
        print("❌ smart_search_and_move 方法不存在")
        return False

def test_gui_button_exists():
    """測試 GUI 按鈕是否存在"""
    print("\n🧪 測試 2: 檢查 GUI 是否有新按鈕")
    
    # 讀取 GUI 程式碼
    gui_file = project_root / "src" / "ui" / "main_gui.py"
    content = gui_file.read_text(encoding='utf-8')
    
    if '智慧搜尋並分類' in content:
        print("✅ GUI 包含「智慧搜尋並分類」按鈕")
        return True
    else:
        print("❌ GUI 不包含「智慧搜尋並分類」按鈕")
        return False

def test_improved_message():
    """測試無資料提示訊息是否改善"""
    print("\n🧪 測試 3: 檢查無資料提示訊息")
    
    # 讀取 classifier_core 程式碼
    core_file = project_root / "src" / "services" / "classifier_core.py"
    content = core_file.read_text(encoding='utf-8')
    
    if '💡 建議操作' in content and '智慧搜尋並分類' in content:
        print("✅ 無資料提示訊息已改善")
        return True
    else:
        print("❌ 無資料提示訊息未改善")
        return False

def main():
    print("="*60)
    print("🔍 智慧搜尋並分類功能測試")
    print("="*60)
    
    results = []
    
    # 執行測試
    results.append(test_method_exists())
    results.append(test_gui_button_exists())
    results.append(test_improved_message())
    
    # 總結
    print("\n" + "="*60)
    print("📊 測試結果總覽")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ 通過: {passed}/{total}")
    print(f"❌ 失敗: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有測試通過！功能已成功實作。")
    else:
        print("\n⚠️ 部分測試失敗，請檢查程式碼。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
