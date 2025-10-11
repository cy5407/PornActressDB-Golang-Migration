# -*- coding: utf-8 -*-
"""
片商識別器模組
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class StudioIdentifier:
    """片商識別器"""
    
    def __init__(self, rules_file: str = "studios.json"):
        self.rules_file = Path(rules_file)
        self.studio_patterns = self._load_rules()
    
    def _load_rules(self) -> Dict:
        if not self.rules_file.exists():
            logger.warning(f"片商規則檔案 {self.rules_file} 不存在，將建立預設檔案。")
            default_rules = {
                'S1': ['SSIS', 'SSNI', 'STARS'], 
                'MOODYZ': ['MIRD', 'MIDD', 'MIDV'], 
                'PREMIUM': ['IPX', 'IPZ', 'IPZZ'], 
                'WANZ': ['WANZ'], 
                'FALENO': ['FSDSS']
            }
            try:
                with self.rules_file.open('w', encoding='utf-8') as f: 
                    json.dump(default_rules, f, ensure_ascii=False, indent=4)
                return default_rules
            except IOError as e: 
                logger.error(f"無法建立預設片商規則檔案: {e}")
                return {}
        try:
            with self.rules_file.open('r', encoding='utf-8') as f: 
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"讀取片商規則檔案失敗: {e}, 將使用空規則。")
            return {}
    
    def identify_studio(self, code: str) -> str:
        if not code: 
            return 'UNKNOWN'
        prefix_match = re.match(r'([A-Z]+)', code.upper())
        if prefix_match:
            prefix = prefix_match.group(1)
            for studio, prefixes in self.studio_patterns.items():
                if prefix in prefixes: 
                    return studio
        return 'UNKNOWN'
