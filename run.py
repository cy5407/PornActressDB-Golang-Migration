# -*- coding: utf-8 -*-
"""
女優分類系統 - 主進入點
"""

import sys
from pathlib import Path

# 設定終端機編碼（Windows 相容性）
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except Exception:
        pass  # 如果設定失敗就忽略

# 將 src 資料夾加入 Python 路徑
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

# 確保當前目錄也在路徑中
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox
    import logging
    
    # 設定日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('unified_classifier.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("🚀 啟動女優分類系統 - 完整版 v5.4.3 (智慧分類強化版)...")
        
        # 初始化安全搜尋器設定
        logger.info("🛡️ 初始化安全搜尋功能...")
        
        # 建立必要的資料夾
        from pathlib import Path
        data_dir = Path('data')
        data_dir.mkdir(exist_ok=True)
        cache_dir = Path('cache')
        cache_dir.mkdir(exist_ok=True)
        
        logger.info("📁 已建立必要的資料夾")
        
        root = tk.Tk()
        
        # 嘗試使用 ttkbootstrap 美化主題
        try:
            import ttkbootstrap as tb
            style = tb.Style(theme='litera')
            root = style.master
            logger.info("✨ 已載入 ttkbootstrap 美化主題")
        except ImportError:
            logger.info("📋 使用預設 tkinter 主題")
          # 匯入並啟動主介面
        import ui.main_gui
        from ui.main_gui import UnifiedActressClassifierGUI
        app = UnifiedActressClassifierGUI(root)
        
        logger.info("🎬 GUI 介面已啟動")
        root.mainloop()
        logger.info("✅ 程式正常結束。")
        
    except Exception as e:
        logger.error(f"❌ 程式啟動失敗: {e}", exc_info=True)
        try:
            messagebox.showerror(
                "致命錯誤", 
                f"程式發生無法處理的錯誤，請查看日誌檔案 'unified_classifier.log'。\n\n錯誤: {e}"
            )
        except:
            print(f"致命錯誤: {e}")
