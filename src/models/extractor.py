# -*- coding: utf-8 -*-
"""
番號提取器模組
"""
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class UnifiedCodeExtractor:
    """統一程式碼提取器"""
    
    def __init__(self):
        self.supported_formats = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts']
        # 需要跳過的檔案前綴模式（FC2、PPV 相關）
        self.skip_prefixes = [
            "FC2", "FC2PPV", "FC2-PPV", "FC2_PPV",
            "PPV-", "PPV_", "PPV", 
            "FC2-", "FC2_"
        ]
        # 增強的番號模式，按優先級排序
        self.code_patterns = [
            (r'([A-Z]{2,6}-\d{3,5})', '標準格式'),
            (r'([A-Z]{2,6}-\d{3,5})[A-Z]*', '標準格式帶後綴'),  # 處理 STARS-707CH → STARS-707
            (r'([A-Z]{2,6}\d{3,5})', '無橫槓格式'),
            (r'([A-Z]{2,6}[._]\d{3,5})', '特殊分隔符格式'),    # 處理 STARS_707, STARS.707            (r'(\d{6}[-_]\d{3})', '數字格式')
        ]
    
    def extract_code(self, filename: str) -> Optional[str]:
        """從檔案名稱提取番號"""
        base_name = Path(filename).stem  # 取得不含副檔名的檔案名稱
        
        # 增強的 FC2/PPV 過濾邏輯
        if self._should_skip_file(base_name):
            logger.debug(f"跳過 FC2/PPV 檔案: {filename}")
            return None
        
        # 增強的檔名清理邏輯
        cleaned_name = base_name
        
        # 移除括號內容 [H265], (1080p), {字幕組} 等
        cleaned_name = re.sub(r'\[.*?\]|\(.*?\)|\{.*?\}', '', cleaned_name)
        
        # 移除常見的品質和編碼標記
        cleaned_name = re.sub(r'[-_]?[CHch]\d*$', '', cleaned_name)  # 移除 -C, CH, -C1 等結尾
        cleaned_name = re.sub(r'\.H265$', '', cleaned_name, flags=re.IGNORECASE)  # 移除 .H265
        cleaned_name = re.sub(r'[-_]?(1080p|720p|4K|HDR|HEVC|AVC|X264|X265)', '', cleaned_name, flags=re.IGNORECASE)
        
        # 移除版本標記 -c, -C 等（但保留在番號中間的）
        cleaned_name = re.sub(r'[-_ ]?c\d*$', '', cleaned_name, flags=re.IGNORECASE)
        
        # 移除網站標記
        cleaned_name = re.sub(r'^(hhd800\.com@|xxx\.com-)', '', cleaned_name, flags=re.IGNORECASE)
        
        # 移除多餘的空白和連字符
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        cleaned_name = re.sub(r'-+', '-', cleaned_name)  # 將多個連字符合併為一個
        
        # 使用增強的模式進行匹配
        for pattern, format_name in self.code_patterns:
            match = re.search(pattern, cleaned_name, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                
                # 標準化分隔符（將 . _ 轉換為 -）
                code = re.sub(r'[._]', '-', code)
                
                # 如果沒有分隔符，添加標準的 - 分隔符
                if '-' not in code and re.match(r'^[A-Z]+[0-9]+', code):
                    letters = ''.join(filter(str.isalpha, code))  # 提取字母部分
                    numbers = ''.join(filter(str.isdigit, code))  # 提取數字部分
                    code = f"{letters}-{numbers}"
                
                # 驗證番號的合理性
                if self._validate_code(code):
                    return code
        
        return None
    
    def _validate_code(self, code: str) -> bool:
        """驗證番號格式是否合理"""
        if not code or len(code) < 4:
            return False
        
        # 檢查是否包含字母和數字
        has_letter = re.search(r'[A-Z]', code)
        has_number = re.search(r'\d', code)
        if not (has_letter and has_number):
            return False
        
        # 檢查長度是否合理（4-15字符）
        if len(code) > 15:
            return False
        
        # 檢查是否符合常見番號格式
        valid_patterns = [            r'^[A-Z]{2,6}-\d{3,5}$',     # STARS-707
            r'^[A-Z]{2,6}\d{3,5}$',      # STARS707
            r'^\d{6}-\d{3}$'             # 240101-001
        ]
        
        for pattern in valid_patterns:
            if re.match(pattern, code):
                return True
        
        return False

    def _should_skip_file(self, base_name: str) -> bool:
        """檢查是否應該跳過此檔案（FC2/PPV 相關）"""
        upper_name = base_name.upper()
        
        # 精確匹配 FC2/PPV 相關模式
        skip_patterns = [
            r'^FC2[-_]',           # FC2- 或 FC2_
            r'^FC2PPV[-_]',        # FC2PPV- 或 FC2PPV_  
            r'^FC2\d',             # FC2 後直接接數字
            r'^PPV[-_]\d',         # PPV-數字 或 PPV_數字
            r'^PPV\d',             # PPV 後直接接數字
        ]
        
        # 檢查是否符合任何需要跳過的模式
        for pattern in skip_patterns:
            if re.match(pattern, upper_name):
                return True
                
        # 額外檢查：檔名中包含明顯的 FC2/PPV 標識
        if any(marker in upper_name for marker in ['FC2PPV', 'FC2-PPV', 'FC2_PPV']):
            return True
            
        return False

    def _should_skip_file(self, base_name: str) -> bool:
        """檢查是否應該跳過此檔案（FC2/PPV 相關）"""
        upper_name = base_name.upper()
        
        # 精確匹配 FC2/PPV 相關模式
        skip_patterns = [
            r'^FC2[-_]',           # FC2- 或 FC2_
            r'^FC2PPV[-_]',        # FC2PPV- 或 FC2PPV_  
            r'^FC2\d',             # FC2 後直接接數字
            r'^PPV[-_]\d',         # PPV-數字 或 PPV_數字
            r'^PPV\d',             # PPV 後直接接數字
        ]
        
        # 檢查是否符合任何需要跳過的模式
        for pattern in skip_patterns:
            if re.match(pattern, upper_name):
                return True
                
        # 額外檢查：檔名中包含明顯的 FC2/PPV 標識
        if any(marker in upper_name for marker in ['FC2PPV', 'FC2-PPV', 'FC2_PPV']):
            return True
            
        return False
