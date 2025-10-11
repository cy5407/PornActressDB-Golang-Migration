# -*- coding: utf-8 -*-
"""
核心業務邏輯類別
"""
import shutil
import logging
import threading
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

import sys
from pathlib import Path

# 添加專案根目錄到系統路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.config import ConfigManager
from models.database import SQLiteDBManager
from models.extractor import UnifiedCodeExtractor
from models.studio import StudioIdentifier
from utils.scanner import UnifiedFileScanner
from services.web_searcher import WebSearcher
from services.studio_classifier import StudioClassificationCore
from services.interactive_classifier import InteractiveClassifier

logger = logging.getLogger(__name__)


class UnifiedClassifierCore:
    """核心業務邏輯類別 - 包含片商分類功能"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.db_manager = SQLiteDBManager(config.get('database', 'database_path'))
        self.code_extractor = UnifiedCodeExtractor()
        self.file_scanner = UnifiedFileScanner()
        self.studio_identifier = StudioIdentifier()
        self.web_searcher = WebSearcher(config)
        
        # 注意：preference_manager 需要從外部傳入或在初始化時建立
        self.preference_manager = None
        self.interactive_classifier = None
        
        # 片商分類功能
        self.studio_classifier = None
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def set_preference_manager(self, preference_manager):
        """設定偏好管理器"""
        self.preference_manager = preference_manager
        # 建立片商分類功能
        self.studio_classifier = StudioClassificationCore(
            self.db_manager,
            self.code_extractor,
            self.studio_identifier,
            self.preference_manager
        )

    def set_interactive_classifier(self, interactive_classifier: InteractiveClassifier):
        """設定互動式分類器"""
        self.interactive_classifier = interactive_classifier

    # 新增片商分類相關方法
    def classify_actresses_by_studio(self, folder_path: str, progress_callback=None):
        """按片商分類女優資料夾"""
        if not self.studio_classifier:
            return {'status': 'error', 'message': '片商分類器未初始化'}
        return self.studio_classifier.classify_actresses_by_studio(folder_path, progress_callback)

    def get_actress_studio_distribution(self, actress_name: str) -> Dict:
        """取得指定女優的片商分佈統計"""
        # 這裡可以根據需要實作具體的查詢邏輯
        pass

    def preview_studio_classification(self, folder_path: str) -> Dict:
        """預覽片商分類結果（不實際移動檔案）"""
        if not self.studio_classifier:
            return {'status': 'error', 'message': '片商分類器未初始化'}
            
        try:
            root_folder = Path(folder_path)
            
            # 掃描女優資料夾
            actress_folders = self.studio_classifier._scan_actress_folders(root_folder)
            
            # 更新統計（但不移動檔案）
            updated_stats = self.studio_classifier._update_actress_statistics(actress_folders)
            
            # 分析分類結果
            preview_result = {
                'total_actresses': len(actress_folders),
                'studio_distribution': defaultdict(list),
                'solo_artists': [],
                'unknown_actresses': []
            }
            
            solo_folder_name = self.preference_manager.get_solo_folder_name()
            confidence_threshold = self.preference_manager.get_confidence_threshold()
            
            for actress_name, stats in updated_stats.items():
                confidence = stats['confidence']
                main_studio = stats['main_studio']
                
                if confidence >= confidence_threshold and main_studio != 'UNKNOWN':
                    preview_result['studio_distribution'][main_studio].append(actress_name)
                else:
                    preview_result['solo_artists'].append(actress_name)
            
            return {
                'status': 'success',
                'preview': preview_result,
                'solo_folder_name': solo_folder_name,
                'confidence_threshold': confidence_threshold
            }
            
        except Exception as e:
            self.logger.error(f"預覽片商分類失敗: {e}")
            return {'status': 'error', 'message': str(e)}

    def process_and_search(self, folder_path: str, stop_event: threading.Event, progress_callback=None):
        try:
            if progress_callback: 
                progress_callback("🔍 開始掃描資料夾...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {'status': 'success', 'message': '未發現影片檔案'}
            if progress_callback: 
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")
            
            codes_in_db = {v['code'] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map: 
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n")
                progress_callback(f"🎯 需要搜尋 {len(new_code_file_map)} 個新番號。\n\n")
            if not new_code_file_map:
                if progress_callback: 
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {'status': 'success', 'message': '所有番號都已存在於資料庫中'}
            
            search_results = self.web_searcher.batch_search(
                list(new_code_file_map.keys()), 
                self.web_searcher.search_info, 
                stop_event, 
                progress_callback
            )
            success_count = 0
            for code, result in search_results.items():
                if result and result.get('actresses'):
                    success_count += 1
                    for file_path in new_code_file_map[code]:
                        # 優先使用搜尋結果中的片商資訊，只有當搜尋結果沒有片商資訊時才使用本地識別
                        studio = result.get('studio')
                        if not studio or studio == 'UNKNOWN':
                            studio = self.studio_identifier.identify_studio(code)
                        
                        info = {
                            'actresses': result['actresses'], 
                            'original_filename': file_path.name, 
                            'file_path': str(file_path), 
                            'studio': studio, 
                            'search_method': result.get('source', 'AV-WIKI')
                        }
                        self.db_manager.add_or_update_video(code, info)
            return {
                'status': 'success',                'total_files': len(video_files), 
                'new_codes': len(new_code_file_map), 
                'success': success_count
            }
        except Exception as e:
            self.logger.error(f"搜尋過程中發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    def process_and_search_japanese_sites(self, folder_path: str, stop_event: threading.Event, progress_callback=None):
        """僅使用日文網站搜尋 (AV-WIKI 和 chiba-f.net)"""
        try:
            if progress_callback: 
                progress_callback("🇯🇵 開始掃描資料夾 (日文網站搜尋模式)...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {'status': 'success', 'message': '未發現影片檔案'}
            if progress_callback: 
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")
            
            codes_in_db = {v['code'] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map: 
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n")
                progress_callback(f"🎯 需要透過日文網站搜尋 {len(new_code_file_map)} 個新番號。\n\n")
            if not new_code_file_map:
                if progress_callback: 
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {'status': 'success', 'message': '所有番號都已存在於資料庫中'}
            
            # 使用日文網站專用搜尋方法
            search_results = self.web_searcher.batch_search(
                list(new_code_file_map.keys()), 
                self.web_searcher.search_japanese_sites, 
                stop_event, 
                progress_callback
            )
            success_count = 0
            for code, result in search_results.items():
                if result and result.get('actresses'):
                    success_count += 1
                    for file_path in new_code_file_map[code]:
                        # 優先使用搜尋結果中的片商資訊，只有當搜尋結果沒有片商資訊時才使用本地識別
                        studio = result.get('studio')
                        if not studio or studio == 'UNKNOWN':
                            studio = self.studio_identifier.identify_studio(code)
                        
                        info = {
                            'actresses': result['actresses'], 
                            'original_filename': file_path.name, 
                            'file_path': str(file_path), 
                            'studio': studio, 
                            'search_method': result.get('source', '日文網站')
                        }
                        self.db_manager.add_or_update_video(code, info)
            return {
                'status': 'success', 
                'total_files': len(video_files), 
                'new_codes': len(new_code_file_map), 
                'success': success_count
            }
        except Exception as e:
            self.logger.error(f"日文網站搜尋過程中發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    def process_and_search_javdb(self, folder_path: str, stop_event: threading.Event, progress_callback=None):
        """僅使用 JAVDB 搜尋"""
        try:
            if progress_callback: 
                progress_callback("📊 開始掃描資料夾 (JAVDB 搜尋模式)...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {'status': 'success', 'message': '未發現影片檔案'}
            if progress_callback: 
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")
            
            codes_in_db = {v['code'] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map: 
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n")
                progress_callback(f"🎯 需要透過 JAVDB 搜尋 {len(new_code_file_map)} 個新番號。\n\n")
            if not new_code_file_map:
                if progress_callback: 
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {'status': 'success', 'message': '所有番號都已存在於資料庫中'}
            
            # 使用 JAVDB 專用搜尋方法
            search_results = self.web_searcher.batch_search(
                list(new_code_file_map.keys()), 
                self.web_searcher.search_javdb_only, 
                stop_event, 
                progress_callback
            )
            success_count = 0
            for code, result in search_results.items():
                if result and result.get('actresses'):
                    success_count += 1
                    for file_path in new_code_file_map[code]:
                        # 優先使用搜尋結果中的片商資訊，只有當搜尋結果沒有片商資訊時才使用本地識別
                        studio = result.get('studio')
                        if not studio or studio == 'UNKNOWN':
                            studio = self.studio_identifier.identify_studio(code)
                        
                        info = {
                            'actresses': result['actresses'], 
                            'original_filename': file_path.name, 
                            'file_path': str(file_path), 
                            'studio': studio, 
                            'search_method': result.get('source', 'JAVDB')
                        }
                        self.db_manager.add_or_update_video(code, info)
            return {
                'status': 'success', 
                'total_files': len(video_files), 
                'new_codes': len(new_code_file_map), 
                'success': success_count
            }
        except Exception as e:
            self.logger.error(f"JAVDB 搜尋過程中發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}
    
    def interactive_move_files(self, folder_path_str: str, progress_callback=None):
        """互動式檔案移動 - 支援多女優共演的偏好選擇"""
        try:
            folder_path = Path(folder_path_str)
            if progress_callback: 
                progress_callback(f"🔍 開始掃描 {folder_path} 並準備互動式移動...\n")
            video_files = self.file_scanner.scan_directory(folder_path_str, recursive=False)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 目標資料夾中沒有影片檔案可移動。\n")
                return {'status': 'success', 'message': '目標資料夾中沒有影片檔案可移動。'}
            
            move_stats = {'success': 0, 'exists': 0, 'no_data': 0, 'failed': 0, 'skipped': 0}
            skip_all = False
              # 分析需要互動選擇的檔案
            collaboration_files = []
            single_files = []
            
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code: 
                    continue
                info = self.db_manager.get_video_info(code)
                if not info or not info.get('actresses'):
                    continue
                
                actresses = info['actresses']
                # 使用正確的解析邏輯來判斷單人/多人共演
                parsed_actresses, is_collaboration = self._parse_actresses_list(actresses)
                
                if not is_collaboration:
                    # 單人作品
                    single_files.append((file_path, code, parsed_actresses, info))
                else:
                    # 多人共演作品
                    collaboration_files.append((file_path, code, parsed_actresses, info))
            
            if progress_callback:
                progress_callback(f"📊 分析結果: {len(single_files)} 個單人作品, {len(collaboration_files)} 個多人共演作品\n")
                if collaboration_files:
                    progress_callback("🤝 開始處理多人共演作品的分類選擇...\n\n")
              # 處理所有檔案
            all_files = single_files + collaboration_files
            
            for i, (file_path, code, actresses, info) in enumerate(all_files, 1):
                if skip_all:
                    move_stats['skipped'] += 1
                    continue
                
                try:
                    # 決定分類目標
                    if len(actresses) == 1:
                        target_actress = actresses[0]
                        remember = False
                    else:
                        if not self.interactive_classifier:
                            target_actress = actresses[0]
                            remember = False
                        else:
                            choice, remember = self.interactive_classifier.get_classification_choice(code, actresses)
                            
                            if choice == "SKIP_ALL":
                                skip_all = True
                                move_stats['skipped'] += 1
                                if progress_callback: 
                                    progress_callback(f"⏭️ 使用者選擇跳過所有後續檔案\n")
                                continue
                            elif choice == "SKIP":
                                move_stats['skipped'] += 1
                                if progress_callback: 
                                    progress_callback(f"⏭️ [{i}/{len(all_files)}] 跳過: {file_path.name}\n")
                                continue
                            
                            target_actress = choice
                    
                    # 記住偏好設定
                    if remember and len(actresses) > 1:
                        self.preference_manager.save_collaboration_preference(actresses, target_actress)
                        if progress_callback: 
                            progress_callback(f"🧠 已記住組合偏好: {', '.join(actresses)} → {target_actress}\n")
                    
                    # 建立目標資料夾
                    target_folder = folder_path / target_actress
                    target_folder.mkdir(exist_ok=True)
                    
                    # 決定檔案名稱
                    if len(actresses) > 1 and self.preference_manager.preferences.get('auto_tag_filenames', True):
                        actresses_tag = f" ({', '.join(actresses)})"
                        base_name = file_path.stem
                        new_filename = f"{base_name}{actresses_tag}{file_path.suffix}"
                    else:
                        new_filename = file_path.name
                    
                    target_path = target_folder / new_filename
                    
                    # 檢查檔案是否已存在
                    if target_path.exists():
                        move_stats['exists'] += 1
                        if progress_callback: 
                            progress_callback(f"⚠️ [{i}/{len(all_files)}] 已存在: {target_actress}/{new_filename}\n")
                        continue
                    
                    # 執行移動
                    shutil.move(str(file_path), str(target_path))
                    move_stats['success'] += 1
                    
                    if len(actresses) > 1:
                        actresses_display = f" (共演: {', '.join(actresses)})"
                    else:
                        actresses_display = ""
                    
                    if progress_callback: 
                        progress_callback(f"✅ [{i}/{len(all_files)}] {file_path.name} → {target_actress}/{new_filename}{actresses_display}\n")
                    
                except Exception as e:
                    move_stats['failed'] += 1
                    logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                    if progress_callback: 
                        progress_callback(f"❌ [{i}/{len(all_files)}] {file_path.name}: 移動失敗 - {str(e)}\n")
            
            return {'status': 'success', 'total_files': len(video_files), 'stats': move_stats}
            
        except Exception as e:
            self.logger.error(f"互動式檔案移動過程中發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    def move_files(self, folder_path_str: str, progress_callback=None):
        """智慧檔案移動 - 單人自動分類，多人共演啟動互動選擇"""
        try:
            folder_path = Path(folder_path_str)
            if progress_callback: 
                progress_callback(f"🔍 開始掃描 {folder_path} 並準備智慧移動...\n")
            video_files = self.file_scanner.scan_directory(folder_path_str, recursive=False)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 目標資料夾中沒有影片檔案可移動。\n")
                return {'status': 'success', 'message': '目標資料夾中沒有影片檔案可移動。'}
              # 分析檔案，區分單人和多人共演作品
            single_actress_files = []
            collaboration_files = []
            no_data_files = []
            
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code: 
                    continue 
                info = self.db_manager.get_video_info(code)
                if not info or not info.get('actresses'):
                    no_data_files.append(file_path)
                    continue
                
                actresses = info['actresses']
                # 使用新的解析邏輯來判斷單人/多人共演
                parsed_actresses, is_collaboration = self._parse_actresses_list(actresses)
                
                if not is_collaboration:
                    # 單人作品
                    single_actress_files.append((file_path, code, parsed_actresses[0], info))
                else:
                    # 多人共演作品
                    collaboration_files.append((file_path, code, parsed_actresses, info))
            
            if progress_callback:
                progress_callback(f"📊 分析結果: {len(single_actress_files)} 個單人作品, {len(collaboration_files)} 個多人共演作品, {len(no_data_files)} 個無資料檔案\n")
                
                if collaboration_files:
                    progress_callback(f"🤝 發現多人共演作品，將啟動互動式分類模式\n\n")
            
            move_stats = {'success': 0, 'exists': 0, 'no_data': 0, 'failed': 0, 'interactive': 0}
            total_files = len(video_files)
            processed = 0
            
            # 先處理單人作品（自動分類）
            if single_actress_files:
                if progress_callback: 
                    progress_callback(f"🏃 開始自動處理 {len(single_actress_files)} 個單人作品...\n")
                
                for file_path, code, main_actress, info in single_actress_files:
                    processed += 1
                    target_folder = folder_path / main_actress
                    target_folder.mkdir(exist_ok=True)
                    target_path = target_folder / file_path.name
                    
                    if target_path.exists():
                        move_stats['exists'] += 1
                        if progress_callback: 
                            progress_callback(f"⚠️ [{processed}/{total_files}] {file_path.name}: 檔案已存在於目標資料夾\n")
                        continue
                    
                    try:
                        shutil.move(str(file_path), str(target_path))
                        move_stats['success'] += 1
                        if progress_callback: 
                            progress_callback(f"✅ [{processed}/{total_files}] {file_path.name} → {main_actress}/\n")
                    except Exception as e:
                        move_stats['failed'] += 1
                        logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                        if progress_callback: 
                            progress_callback(f"❌ [{processed}/{total_files}] {file_path.name}: 移動失敗\n")
            
            # 處理無資料檔案
            for file_path in no_data_files:
                processed += 1
                move_stats['no_data'] += 1
                if progress_callback: 
                    progress_callback(f"❓ [{processed}/{total_files}] {file_path.name}: 資料庫中無資料\n")
            
            # 處理多人共演作品（互動式分類）
            if collaboration_files:
                if progress_callback: 
                    progress_callback(f"\n🎯 開始互動式處理 {len(collaboration_files)} 個多人共演作品...\n")
                
                skip_all = False
                
                for file_path, code, actresses, info in collaboration_files:
                    processed += 1
                    
                    if skip_all:
                        move_stats['interactive'] += 1
                        if progress_callback: 
                            progress_callback(f"⏭️ [{processed}/{total_files}] 跳過: {file_path.name}\n")
                        continue
                    
                    try:
                        # 決定分類目標
                        if not self.interactive_classifier:
                            # 沒有互動分類器時，使用第一位女優
                            target_actress = actresses[0]
                            remember = False
                            if progress_callback: 
                                progress_callback(f"🤖 [{processed}/{total_files}] 無互動分類器，使用第一位女優: {actresses[0]}\n")
                        else:
                            choice, remember = self.interactive_classifier.get_classification_choice(code, actresses)
                            
                            if choice == "SKIP_ALL":
                                skip_all = True
                                move_stats['interactive'] += 1
                                if progress_callback: 
                                    progress_callback(f"⏭️ [{processed}/{total_files}] 使用者選擇跳過所有後續多人共演檔案\n")
                                continue
                            elif choice == "SKIP":
                                move_stats['interactive'] += 1
                                if progress_callback: 
                                    progress_callback(f"⏭️ [{processed}/{total_files}] 跳過: {file_path.name}\n")
                                continue
                            
                            target_actress = choice
                        
                        # 記住偏好設定
                        if remember and len(actresses) > 1 and self.preference_manager:
                            self.preference_manager.save_collaboration_preference(actresses, target_actress)
                            if progress_callback: 
                                progress_callback(f"🧠 已記住組合偏好: {', '.join(actresses)} → {target_actress}\n")
                        
                        # 建立目標資料夾
                        target_folder = folder_path / target_actress
                        target_folder.mkdir(exist_ok=True)
                        
                        # 決定檔案名稱
                        if self.preference_manager and self.preference_manager.preferences.get('auto_tag_filenames', True):
                            actresses_tag = f" ({', '.join(actresses)})"
                            base_name = file_path.stem
                            new_filename = f"{base_name}{actresses_tag}{file_path.suffix}"
                        else:
                            new_filename = file_path.name
                        
                        target_path = target_folder / new_filename
                        
                        # 檢查檔案是否已存在
                        if target_path.exists():
                            move_stats['exists'] += 1
                            if progress_callback: 
                                progress_callback(f"⚠️ [{processed}/{total_files}] 已存在: {target_actress}/{new_filename}\n")
                            continue
                          # 執行移動
                        shutil.move(str(file_path), str(target_path))
                        move_stats['success'] += 1
                        move_stats['interactive'] += 1
                        
                        actresses_display = f" (共演: {', '.join(actresses)})"
                        if progress_callback: 
                            progress_callback(f"✅ [{processed}/{total_files}] {file_path.name} → {target_actress}/{new_filename}{actresses_display}\n")
                        
                    except Exception as e:
                        move_stats['failed'] += 1
                        logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                        if progress_callback: 
                            progress_callback(f"❌ [{processed}/{total_files}] {file_path.name}: 移動失敗 - {str(e)}\n")
            
            if progress_callback and collaboration_files:
                progress_callback(f"\n🎉 智慧分類完成！共處理 {move_stats['interactive']} 個多人共演作品\n")
            
            return {'status': 'success', 'total_files': len(video_files), 'stats': move_stats}
        except Exception as e:
            self.logger.error(f"檔案移動過程中發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}
    
    def process_and_search_javdb(self, folder_path: str, stop_event: threading.Event, progress_callback=None):
        """處理檔案並使用 JAVDB 搜尋"""
        try:
            if progress_callback: 
                progress_callback("📊 開始掃描資料夾 (JAVDB 搜尋)...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback: 
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {'status': 'success', 'message': '未發現影片檔案'}
            if progress_callback: 
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")
            
            codes_in_db = {v['code'] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map: 
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n")
                progress_callback(f"🎯 需要搜尋 {len(new_code_file_map)} 個新番號。\n\n")
            if not new_code_file_map:
                if progress_callback: 
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {'status': 'success', 'message': '所有番號都已存在於資料庫中'}
              # 使用 JAVDB 專用搜尋方法
            search_results = self.web_searcher.batch_search(
                list(new_code_file_map.keys()), 
                self.web_searcher.search_javdb_only, 
                stop_event, 
                progress_callback
            )
            success_count = 0
            for code, result in search_results.items():
                if result and result.get('actresses'):
                    success_count += 1
                    for file_path in new_code_file_map[code]:
                        # 優先使用搜尋結果中的片商資訊，只有當搜尋結果沒有片商資訊時才使用本地識別
                        studio = result.get('studio')
                        if not studio or studio == 'UNKNOWN':
                            studio = self.studio_identifier.identify_studio(code)
                        
                        info = {
                            'actresses': result['actresses'], 
                            'original_filename': file_path.name, 
                            'file_path': str(file_path), 
                            'studio': studio, 
                            'search_method': result.get('source', 'JAVDB')                        }
                        self.db_manager.add_or_update_video(code, info)
                    success_count += 1
                    if progress_callback: 
                        progress_callback(f"✓ {code}: {', '.join(result['actresses'])}\n")
                else:
                    if progress_callback: 
                        progress_callback(f"✗ {code}: 未找到女優資訊\n")
            
            if progress_callback:
                total_codes = len(new_code_file_map)
                progress_callback(f"\n📊 搜尋結果統計 (JAVDB):\n")
                progress_callback(f"成功找到: {success_count}/{total_codes} 個番號\n")
                progress_callback(f"成功率: {success_count/total_codes*100:.1f}%\n")
            
            return {'status': 'success', 'message': f'成功搜尋 {success_count} 個番號'}
        except Exception as e:
            logger.error(f"JAVDB 搜尋過程發生錯誤: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}
    
    def _parse_actresses_list(self, actresses):
        """
        解析女優名單，處理用 # 分隔的多人共演格式
        
        Args:
            actresses: 資料庫中的女優列表
            
        Returns:
            tuple: (parsed_actresses_list, is_collaboration)
        """
        if not actresses:
            return [], False
        
        # 如果有多個女優記錄，直接返回
        if len(actresses) > 1:
            return actresses, True
        
        # 檢查單一記錄是否包含 # 分隔的多個女優
        actress_str = actresses[0]
        if '#' in actress_str:
            # 解析 # 分隔的女優名單
            parsed_actresses = []
            for name in actress_str.split('#'):
                name = name.strip()
                if name:
                    parsed_actresses.append(name)
            
            return parsed_actresses, len(parsed_actresses) > 1
        
        # 單一女優
        return [actress_str], False
