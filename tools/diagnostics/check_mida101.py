#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查詢 MIDA-101 在 AV-WIKI 的原始資料
"""

import sys
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

def check_avwiki_mida101():
    """查詢 MIDA-101 在 AV-WIKI 的原始資料"""
    
    code = "MIDA-101"
    search_url = f"https://av-wiki.net/?s={quote(code)}&post_type=product"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
    }
    
    print(f"🔍 搜尋網址: {search_url}\n")
    
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(search_url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找搜尋結果
            results = soup.find_all('article', class_='product')
            print(f"📊 找到 {len(results)} 個搜尋結果\n")
            
            for i, article in enumerate(results, 1):
                print(f"{'='*60}")
                print(f"結果 #{i}")
                print(f"{'='*60}")
                
                # 番號
                title_elem = article.find('h2', class_='woocommerce-loop-product__title')
                if title_elem:
                    print(f"📌 標題: {title_elem.get_text(strip=True)}")
                
                # 鏈接
                link_elem = article.find('a', class_='woocommerce-LoopProduct-link')
                if link_elem:
                    product_url = link_elem.get('href')
                    print(f"🔗 連結: {product_url}")
                    
                    # 訪問詳細頁面
                    print(f"\n🔍 正在訪問詳細頁面...\n")
                    detail_response = client.get(product_url, headers=headers)
                    detail_response.raise_for_status()
                    detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                    
                    # 查找女優資訊
                    print("👩 女優資訊:")
                    
                    # 方法 1: 查找 product_meta
                    meta_div = detail_soup.find('div', class_='product_meta')
                    if meta_div:
                        actress_links = meta_div.find_all('a', rel='tag')
                        if actress_links:
                            actresses = [a.get_text(strip=True) for a in actress_links]
                            print(f"  方法1 (product_meta): {actresses}")
                    
                    # 方法 2: 查找所有 rel="tag" 的連結
                    all_tags = detail_soup.find_all('a', rel='tag')
                    if all_tags:
                        all_tag_texts = [a.get_text(strip=True) for a in all_tags]
                        print(f"  方法2 (所有 tag): {all_tag_texts}")
                    
                    # 方法 3: 查找包含「出演者」的區塊
                    for label in detail_soup.find_all(text=lambda t: t and '出演' in t):
                        parent = label.find_parent()
                        if parent:
                            siblings = parent.find_next_siblings()
                            if siblings:
                                print(f"  方法3 (出演者標籤): {[s.get_text(strip=True) for s in siblings[:3]]}")
                    
                    # 顯示 HTML 片段
                    print(f"\n📄 product_meta HTML:")
                    if meta_div:
                        print(meta_div.prettify()[:500])
                    
                print()
    
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_avwiki_mida101()
