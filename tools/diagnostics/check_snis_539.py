#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
檢查特定番號的搜尋結果頁面結構
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup

async def check_snis_539():
    """檢查 SNIS-539"""
    
    search_url = "https://av-wiki.net/?s=SNIS-539&post_type=product"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url, headers=headers) as response:
            html = await response.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # 檢查搜尋結果
    print(f"頁面標題: {soup.title.string if soup.title else '無'}")
    print()
    
    # 檢查是否為「沒有結果」頁面
    page_text = soup.get_text()
    if "何も見つかりませんでした" in page_text or "找不到" in page_text or "沒有找到" in page_text:
        print("這是一個『沒有搜尋結果』頁面")
    else:
        print("頁面有內容")
    
    # 檢查 tag 連結
    tag_links = soup.find_all("a", rel="tag")
    print(f"\n找到 {len(tag_links)} 個 tag 連結:")
    for i, link in enumerate(tag_links[:10], 1):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        has_actress = '/av-actress/' in href
        print(f"  {i}. {text} - {'[女優]' if has_actress else '[其他]'}")
    
    # 找出所有 tag 連結中是女優的
    actress_tags = [link for link in tag_links if '/av-actress/' in link.get('href', '')]
    print(f"\n女優 tag 連結: {len(actress_tags)} 個")
    for i, link in enumerate(actress_tags[:5], 1):
        print(f"  {i}. {link.get_text(strip=True)}")

if __name__ == '__main__':
    asyncio.run(check_snis_539())
