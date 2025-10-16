#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""測試真實搜尋邏輯 - 檢查是否正確識別新影片和應重新搜尋的舊影片"""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from src.services.classifier_core import UnifiedClassifierCore
from src.models.database import SQLiteDBManager
from src.models.config import ConfigManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_search_identification():
    """測試搜尋邏輯是否正確識別新影片和應重新搜尋的影片"""
    
    logger.info("\n" + "=" * 70)
    logger.info("🧪 測試搜尋識別邏輯")
    logger.info("=" * 70)
    
    # 初始化核心和資料庫
    config = ConfigManager()
    db = SQLiteDBManager('data/actress_classifier.db')
    
    # 先清空資料庫
    logger.info("\n🔄 清空舊資料...")
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM video_actress_link")
    cursor.execute("DELETE FROM actresses")
    cursor.execute("DELETE FROM videos")
    conn.commit()
    conn.close()
    logger.info("✓ 資料庫已清空")
    
    # 建立測試場景
    logger.info("\n📝 建立測試場景...")
    
    # 情景1: 已成功搜尋的影片（應該跳過）
    db.add_or_update_video('SONE-909', {
        'original_filename': 'SONE-909.mp4',
        'file_path': '/videos/SONE-909.mp4',
        'studio': 'S1',
        'actresses': ['白上咲花'],
        'search_method': 'JAVDB',
        'search_status': 'searched_found',
        'last_search_date': datetime.now().isoformat()
    })
    logger.info("  ✓ SONE-909: 已找到女優 (searched_found) - 應跳過")
    
    # 情景2: 最近搜尋未找到（未過期，應跳過）
    db.add_or_update_video('FNS-109', {
        'original_filename': 'FNS-109.mp4',
        'file_path': '/videos/FNS-109.mp4',
        'studio': 'FALENO',
        'actresses': [],
        'search_method': 'JAVDB',
        'search_status': 'searched_not_found',
        'last_search_date': (datetime.now() - timedelta(days=3)).isoformat()
    })
    logger.info("  ✓ FNS-109: 3天前搜尋未找到 (未過期) - 應跳過")
    
    # 情景3: 很久前搜尋未找到（已過期，應重新搜尋）
    db.add_or_update_video('SONE-972', {
        'original_filename': 'SONE-972.mp4',
        'file_path': '/videos/SONE-972.mp4',
        'studio': 'S1',
        'actresses': [],
        'search_method': 'JAVDB',
        'search_status': 'searched_not_found',
        'last_search_date': (datetime.now() - timedelta(days=15)).isoformat()
    })
    logger.info("  ✓ SONE-972: 15天前搜尋未找到 (已過期) - 應重新搜尋")
    
    # 情景4: 失敗的搜尋（應總是重新搜尋）
    db.add_or_update_video('SONE-913', {
        'original_filename': 'SONE-913.mp4',
        'file_path': '/videos/SONE-913.mp4',
        'studio': 'S1',
        'actresses': [],
        'search_method': 'JAVDB',
        'search_status': 'failed',
        'last_search_date': (datetime.now() - timedelta(days=2)).isoformat()
    })
    logger.info("  ✓ SONE-913: 搜尋失敗狀態 - 應重新搜尋")
    
    logger.info("\n📊 資料庫當前狀態:")
    for video in db.get_all_videos():
        code = video.get('code')
        status = video.get('search_status')
        last_search = video.get('last_search_date')
        if isinstance(last_search, str):
            dt = datetime.fromisoformat(last_search)
            days_ago = (datetime.now() - dt).days
        else:
            days_ago = "N/A"
        logger.info(f"  {code:12s} | 狀態: {status:20s} | {days_ago}天前")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ 測試場景已設置")
    logger.info("=" * 70)
    logger.info("\n💡 預期結果 (在搜尋邏輯中):")
    logger.info("  ✓ SONE-909: 不會被搜尋 (已找到)")
    logger.info("  ✓ FNS-109:  不會被搜尋 (最近搜尋過)")
    logger.info("  ⚠️  SONE-972: 會被重新搜尋 (結果已過期)")
    logger.info("  ⚠️  SONE-913: 會被重新搜尋 (搜尋失敗)")

if __name__ == '__main__':
    test_search_identification()
