# -*- coding: utf-8 -*-
"""
診斷 SNIS-515 的問題
"""

import sys
from pathlib import Path
import asyncio
from bs4 import BeautifulSoup

src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

async def diagnose():
    from src.scrapers.sources.avwiki_scraper import AVWikiScraper
    
    scraper = AVWikiScraper()
    code = 'SNIS-515'
    
    print(f"\n=== 診斷 {code} ===\n")
    
    # 嘗試搜尋
    result = await scraper.search_video(code)
    actresses = result.get('actresses', [])
    
    print(f"搜尋結果: {len(actresses)} 位女優")
    if actresses:
        for actress in actresses:
            print(f"  - {actress}")
    
    # 檢查搜尋 URL
    from urllib.parse import quote
    search_url = f"https://av-wiki.com/?s={quote(code)}&post_type=product"
    print(f"\n搜尋 URL: {search_url}")
    
    # 嘗試直接取得頁面
    try:
        response = await scraper.safe_scrape(search_url)
        soup = BeautifulSoup(response['content'], 'html.parser')
        
        # 檢查頁面內容
        page_text = soup.get_text()
        print(f"\n頁面長度: {len(page_text)} 字符")
        
        # 檢查是否有搜尋結果
        if '見つかりませんでした' in page_text or 'No results' in page_text:
            print("✓ 確認為「無結果」頁面")
        
        # 尋找所有 tag 連結
        tag_links = soup.find_all("a", rel="tag")
        print(f"找到 tag 連結數: {len(tag_links)}")
        
        for link in tag_links[:5]:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            has_actress = '/av-actress/' in href
            print(f"  - {text} (女優={has_actress})")
    
    except Exception as e:
        print(f"取得頁面失敗: {e}")

asyncio.run(diagnose())
