# -*- coding: utf-8 -*-
"""
AV-WIKI 專用爬蟲
針對 av-wiki.net 優化的爬蟲實作
"""

import aiohttp
import logging
import re
from typing import Dict, List, Optional, Any
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper, ScrapingException, ErrorType
from ..encoding_utils import create_safe_soup, validate_japanese_content

logger = logging.getLogger(__name__)


class AVWikiScraper(BaseScraper):
    """AV-WIKI 專用爬蟲類"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://av-wiki.net"
        
        # AV-WIKI 專用配置
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8,zh;q=0.7',  # 日語優先
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': self.base_url,
            'Cache-Control': 'no-cache'
        }
        
        logger.info("📚 AV-WIKI 爬蟲已初始化")
    
    async def scrape_url(self, url: str) -> Dict[str, Any]:
        """爬取 AV-WIKI URL"""
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(
                headers=self.headers, 
                timeout=timeout
            ) as session:
                async with session.get(url) as response:
                    
                    if response.status == 404:
                        raise ScrapingException(f"頁面不存在", ErrorType.CLIENT_ERROR, url, 404)
                    elif response.status >= 500:
                        raise ScrapingException(f"伺服器錯誤", ErrorType.SERVER_ERROR, url, response.status)
                    elif response.status == 429:
                        raise ScrapingException(f"請求過於頻繁", ErrorType.RATE_LIMIT_ERROR, url, 429)
                    
                    response.raise_for_status()
                    
                    # 讀取內容並進行編碼檢測
                    content_bytes = await response.read()
                    soup, encoding = create_safe_soup(content_bytes)
                    
                    logger.debug(f"✅ AV-WIKI 頁面載入成功，編碼: {encoding}")
                    
                    # 解析內容
                    parsed_data = self.parse_content(str(soup), url)
                    parsed_data['source'] = 'AV-WIKI'
                    parsed_data['encoding'] = encoding
                    
                    return parsed_data
                    
        except aiohttp.ClientError as e:
            raise ScrapingException(f"網路連線錯誤: {e}", ErrorType.NETWORK_ERROR, url)
        except Exception as e:
            if isinstance(e, ScrapingException):
                raise
            raise ScrapingException(f"未知錯誤: {e}", ErrorType.UNKNOWN_ERROR, url)
    
    def parse_content(self, content: str, url: str) -> Dict[str, Any]:
        """解析 AV-WIKI 頁面內容"""
        soup = BeautifulSoup(content, 'html.parser')
        result = {
            'actresses': [],
            'studio': None,
            'studio_code': None,
            'title': None,
            'release_date': None,
            'series': None,
            'categories': []
        }
        
        try:
            # 檢查是否為搜尋結果頁面
            if '?s=' in url:
                return self._parse_search_results(soup)
            else:
                return self._parse_detail_page(soup)
                
        except Exception as e:
            logger.error(f"解析 AV-WIKI 內容失敗: {e}")
            raise ScrapingException(f"內容解析錯誤: {e}", ErrorType.PARSING_ERROR, url)
    
    def _parse_search_results(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """解析搜尋結果頁面"""
        results = []
        
        # 方法1: 尋找專用的女優名稱元素
        actress_elements = soup.find_all(class_="actress-name")
        if actress_elements:
            for element in actress_elements:
                actress_name = element.text.strip()
                if self._is_valid_actress_name(actress_name):
                    results.append({
                        'actresses': [actress_name],
                        'source_element': 'actress-name'
                    })
        
        # 方法2: 搜尋產品文章
        articles = soup.find_all('article') or soup.find_all('div', class_='post')
        
        for article in articles:
            try:
                # 提取標題
                title_element = (article.find('h1') or 
                               article.find('h2') or 
                               article.find('h3') or
                               article.find(class_='entry-title'))
                
                title = title_element.text.strip() if title_element else ''
                
                # 從內容中提取女優名稱
                actresses = self._extract_actresses_from_text(article.get_text())
                
                # 提取連結（如果有的話）
                link_element = article.find('a')
                detail_url = link_element.get('href') if link_element else None
                if detail_url and not detail_url.startswith('http'):
                    detail_url = urljoin(self.base_url, detail_url)
                
                if actresses:
                    results.append({
                        'title': title,
                        'actresses': actresses,
                        'detail_url': detail_url,
                        'source_element': 'article'
                    })
                    
            except Exception as e:
                logger.warning(f"解析 AV-WIKI 文章失敗: {e}")
                continue
        
        # 方法3: 通用文本掃描
        if not results:
            page_text = soup.get_text()
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            
            for i, line in enumerate(lines):
                if any(keyword in line for keyword in ['出演', '女優', '演員']):
                    # 檢查前後幾行是否有女優名稱
                    for j in range(max(0, i-2), min(len(lines), i+3)):
                        potential_names = self._extract_actresses_from_text(lines[j])
                        if potential_names:
                            results.append({
                                'actresses': potential_names,
                                'source_element': 'text_scan',
                                'context_line': line
                            })
        
        # 去重並返回
        unique_actresses = set()
        filtered_results = []
        
        for result in results:
            for actress in result['actresses']:
                if actress not in unique_actresses:
                    unique_actresses.add(actress)
                    filtered_results.append({
                        'actresses': [actress],
                        'source': result.get('source_element', 'unknown')
                    })
        
        return {
            'search_results': filtered_results,
            'total_results': len(filtered_results),
            'unique_actresses': list(unique_actresses)
        }
    
    def _parse_detail_page(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """解析詳情頁面"""
        result = {
            'actresses': [],
            'studio': None,
            'studio_code': None,
            'title': None,
            'release_date': None,
            'series': None,
            'categories': []
        }
        
        # 提取標題
        title_element = (soup.find('h1') or 
                        soup.find('h2', class_='entry-title') or
                        soup.find('title'))
        if title_element:
            result['title'] = title_element.text.strip()
        
        # 從頁面內容中提取資訊
        page_text = soup.get_text()
        
        # 提取女優名稱
        result['actresses'] = self._extract_actresses_from_text(page_text)
        
        # 提取片商資訊
        studio_info = self._extract_studio_info(page_text, result.get('title', ''))
        result.update(studio_info)
        
        # 提取發行日期
        date_match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', page_text)
        if date_match:
            result['release_date'] = date_match.group(1)
        
        return result
    
    def _extract_actresses_from_text(self, text: str) -> List[str]:
        """從文本中提取女優名稱"""
        actresses = []
        
        # 分割成行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        for line in lines:
            # 尋找可能的女優名稱
            potential_names = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,20}', line)
            
            for name in potential_names:
                if self._is_valid_actress_name(name) and name not in actresses:
                    actresses.append(name)
        
        return actresses
    
    def _extract_studio_info(self, text: str, title: str = '') -> Dict[str, Any]:
        """提取片商資訊"""
        studio_info = {
            'studio': None,
            'studio_code': None
        }
        
        # 從標題中提取片商代碼
        if title:
            code_match = re.search(r'^([A-Z]+)-?\d+', title)
            if code_match:
                studio_info['studio_code'] = code_match.group(1)
        
        # 從文本中提取片商名稱
        studio_patterns = [
            r'片商[：:]\s*([^\n\r]+)',
            r'製作[：:]\s*([^\n\r]+)', 
            r'メーカー[：:]\s*([^\n\r]+)',
            r'(S1|SOD|MOODYZ|PREMIUM|WANZ|FALENO|ATTACKERS|E-BODY|KAWAII|FITCH|MADONNA)',
        ]
        
        for pattern in studio_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                studio_name = match.group(1).strip()
                if len(studio_name) < 50:  # 合理長度限制
                    studio_info['studio'] = studio_name
                    break
        
        return studio_info
    
    def _is_valid_actress_name(self, name: str) -> bool:
        """驗證是否為有效的女優名稱"""
        if not name or len(name) < 2 or len(name) > 20:
            return False
        
        # 排除常見的非女優關鍵詞
        exclude_keywords = [
            'SOD', 'STARS', 'FANZA', 'MGS', 'MIDV', 'SSIS', 'IPX', 'IPZZ',
            '続きを読む', '検索', '件', '特典', '映像', '付き', 'star', 'SOKMIL',
            'Menu', 'セール', '限定', '最大', '出演者', '女優', '演員', 'actress',
            '動画', 'サンプル', 'レビュー', 'ダウンロード'
        ]
        
        if any(keyword in name for keyword in exclude_keywords):
            return False
        
        # 檢查是否包含數字過多（可能是編號）
        if re.match(r'^\d+$', name) or len(re.findall(r'\d', name)) > len(name) // 2:
            return False
        
        # 必須包含日文字符
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', name):
            return True
        
        return False
    
    async def search_video(self, video_code: str) -> Dict[str, Any]:
        """搜尋指定番號的影片"""
        search_url = f"{self.base_url}/?s={quote(video_code)}&post_type=product"
        
        try:
            # 執行安全爬取
            result = await self.safe_scrape(search_url)
            
            # 處理搜尋結果
            if 'unique_actresses' in result and result['unique_actresses']:
                actresses = result['unique_actresses']
                
                # 驗證內容品質
                content_quality = {}
                for actress in actresses:
                    quality = validate_japanese_content(actress)
                    content_quality[actress] = quality
                
                return {
                    'video_code': video_code,
                    'search_url': search_url,
                    'actresses': actresses,
                    'content_quality': content_quality,
                    'search_results': result.get('search_results', [])
                }
            
            # 沒有找到結果
            return {
                'video_code': video_code,
                'search_url': search_url,
                'actresses': [],
                'message': f'未找到番號 {video_code} 的資訊'
            }
            
        except Exception as e:
            logger.error(f"搜尋 AV-WIKI 影片 {video_code} 失敗: {e}")
            raise ScrapingException(f"搜尋失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url)
    
    async def get_actress_info(self, actress_name: str) -> Dict[str, Any]:
        """獲取女優資訊"""
        search_url = f"{self.base_url}/?s={quote(actress_name)}"
        
        try:
            result = await self.safe_scrape(search_url)
            
            # 處理女優資訊
            works = []
            if 'search_results' in result:
                works = result['search_results']
            
            return {
                'actress_name': actress_name,
                'total_works': len(works),
                'works': works,
                'search_url': search_url
            }
            
        except Exception as e:
            logger.error(f"獲取 AV-WIKI 女優資訊 {actress_name} 失敗: {e}")
            raise ScrapingException(f"獲取女優資訊失敗: {e}", ErrorType.UNKNOWN_ERROR, search_url)