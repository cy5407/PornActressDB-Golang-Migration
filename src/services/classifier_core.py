"""
核心業務邏輯類別
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from models.config import ConfigManager
from models.extractor import UnifiedCodeExtractor
from models.incremental_json_database import IncrementalJSONDB
from models.json_database import JSONDBManager
from models.studio import StudioIdentifier
from services.interactive_classifier import InteractiveClassifier
from services.studio_classifier import StudioClassificationCore
from services.web_searcher import WebSearcher
from utils.file_mover import FileMover
from utils.scanner import UnifiedFileScanner

logger = logging.getLogger(__name__)


def _should_research_stale_record(
    code: str,
    last_search_date: str | None,
    threshold_days: int = 7,
) -> bool:
    """判斷搜尋記錄是否過舊；日期無法解析時保守改為重新搜尋。"""
    if not last_search_date:
        return False

    try:
        normalized_date = last_search_date.replace("Z", "+00:00")
        last_search = datetime.fromisoformat(normalized_date)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(
            f"⚠️ 番號 {code} 的 last_search_date 無法解析 ({last_search_date!r})，"
            f"將改為重新搜尋: {e}"
        )
        return True

    from datetime import timedelta

    return datetime.now(last_search.tzinfo) - last_search > timedelta(
        days=threshold_days
    )


class UnifiedClassifierCore:
    """核心業務邏輯類別 - 包含片商分類功能"""

    def __init__(self, config: ConfigManager):
        self.config = config
        # 使用增量資料庫管理器替代標準管理器，從設定檔讀取資料庫目錄
        json_data_dir = config.get("database", "json_data_dir", fallback="data/json_db")  # 從設定檔讀取資料庫目錄，預設為 data/json_db
        try:
            self.db_manager = IncrementalJSONDB(json_data_dir)
            logger.info(f"✅ 使用 IncrementalJSONDB: {json_data_dir}")
        except Exception as e:
            logger.warning(
                f"⚠️ IncrementalJSONDB 初始化失敗，降級為 JSONDBManager: {e}"
            )
            self.db_manager = JSONDBManager(json_data_dir)
        self.code_extractor = UnifiedCodeExtractor()
        # 使用設定檔建立掃描器（支援 Go 加速）
        self.file_scanner = UnifiedFileScanner.from_config(config)
        # 使用設定檔建立檔案移動器（支援 Go 加速）
        self.file_mover = FileMover.from_config(config)
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
        # 建立片商分類功能（傳入 file_mover 支援 Go 加速）
        self.studio_classifier = StudioClassificationCore(
            self.db_manager,
            self.code_extractor,
            self.studio_identifier,
            self.preference_manager,
            self.file_mover,
        )

    def set_interactive_classifier(self, interactive_classifier: InteractiveClassifier):
        """設定互動式分類器"""
        self.interactive_classifier = interactive_classifier

    def _build_video_info(
        self,
        code: str,
        file_path: Path,
        result: dict | None,
        fallback_method: str,
        current_time: str,
    ) -> dict:
        """建立寫入資料庫的影片資訊"""
        actresses = result.get("actresses", []) if result else []
        source = result.get("source", fallback_method) if result else fallback_method

        studio = result.get("studio") if result else None
        if not studio or studio == "UNKNOWN":
            studio = self.studio_identifier.identify_studio(code)

        info = {
            "actresses": actresses,
            "original_filename": file_path.name,
            "file_path": str(file_path),
            "studio": studio,
            "search_method": source,
            "search_status": "searched_found" if actresses else "searched_not_found",
            "last_search_date": current_time,
        }

        # 補充可用的詳細欄位（JAVDB 等來源）
        if result:
            for field in [
                "studio_code",
                "release_date",
                "title",
                "duration",
                "director",
                "series",
                "rating",
                "categories",
            ]:
                value = result.get(field)
                if value is not None:
                    info[field] = value

        return info

    def _persist_code_result(
        self,
        code: str,
        file_paths: list[Path],
        result: dict | None,
        fallback_method: str,
        progress_callback=None,
        log_prefix: str = "",
    ) -> None:
        """將單一番號搜尋結果立即寫入資料庫，並輸出逐筆進度"""
        current_time = datetime.now().isoformat()
        actresses = result.get("actresses", []) if result else []
        stored_studio = "UNKNOWN"
        stored_source = fallback_method

        for file_path in file_paths:
            info = self._build_video_info(
                code, file_path, result, fallback_method, current_time
            )
            self.db_manager.add_or_update_video(code, info)
            stored_studio = info.get("studio", "UNKNOWN")
            stored_source = info.get("search_method", fallback_method)

        if not progress_callback:
            return

        if actresses:
            actress_preview = "、".join(actresses[:3])
            if len(actresses) > 3:
                actress_preview += f"...等{len(actresses)}位"
            progress_callback(
                f"💾 {log_prefix}已寫入 {code} | 女優: {actress_preview} | 片商: {stored_studio} | 來源: {stored_source}\n"
            )
        else:
            progress_callback(
                f"💾 {log_prefix}已寫入 {code} | 無女優資料 | 片商: {stored_studio} | 來源: {stored_source}\n"
            )

    # 新增片商分類相關方法
    def classify_actresses_by_studio(self, folder_path: str, progress_callback=None):
        """按片商分類女優資料夾"""
        if not self.studio_classifier:
            return {"status": "error", "message": "片商分類器未初始化"}

        # 建立一個同時輸出到終端機和原始 callback 的包裝函式
        def terminal_progress_callback(message: str):
            # 輸出到終端機
            print(message, end="", flush=True)
            # 如果有原始 callback，也呼叫它
            if progress_callback:
                progress_callback(message)

        return self.studio_classifier.classify_actresses_by_studio(
            folder_path, terminal_progress_callback
        )

    def get_actress_studio_distribution(self, actress_name: str) -> dict:
        """取得指定女優的片商分佈統計"""
        # 這裡可以根據需要實作具體的查詢邏輯
        pass

    def preview_studio_classification(self, folder_path: str) -> dict:
        """預覽片商分類結果（不實際移動檔案）"""
        if not self.studio_classifier:
            return {"status": "error", "message": "片商分類器未初始化"}

        try:
            root_folder = Path(folder_path)

            # 掃描女優資料夾
            actress_folders = self.studio_classifier._scan_actress_folders(root_folder)

            # 更新統計（但不移動檔案）
            updated_stats = self.studio_classifier._update_actress_statistics(
                actress_folders
            )

            # 分析分類結果
            preview_result = {
                "total_actresses": len(actress_folders),
                "studio_distribution": defaultdict(list),
                "solo_artists": [],
                "unknown_actresses": [],
            }

            solo_folder_name = self.preference_manager.get_solo_folder_name()
            confidence_threshold = self.preference_manager.get_confidence_threshold()

            for actress_name, stats in updated_stats.items():
                confidence = stats["confidence"]
                main_studio = stats["main_studio"]

                if confidence >= confidence_threshold and main_studio != "UNKNOWN":
                    preview_result["studio_distribution"][main_studio].append(
                        actress_name
                    )
                else:
                    preview_result["solo_artists"].append(actress_name)

            return {
                "status": "success",
                "preview": preview_result,
                "solo_folder_name": solo_folder_name,
                "confidence_threshold": confidence_threshold,
            }

        except Exception as e:
            self.logger.error(f"預覽片商分類失敗: {e}")
            return {"status": "error", "message": str(e)}

    def process_and_search(
        self, folder_path: str, stop_event: threading.Event, progress_callback=None
    ):
        try:
            if progress_callback:
                progress_callback("🔍 開始掃描資料夾...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {"status": "success", "message": "未發現影片檔案"}
            if progress_callback:
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")

            codes_in_db = {v["code"] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map:
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(
                    f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n"
                )
                progress_callback(
                    f"🎯 需要搜尋 {len(new_code_file_map)} 個新番號。\n\n"
                )
            if not new_code_file_map:
                if progress_callback:
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {"status": "success", "message": "所有番號都已存在於資料庫中"}

            success_count = 0
            failed_count = 0

            def on_result(code: str, result: dict | None, _error: Exception | None):
                nonlocal success_count, failed_count
                if result and result.get("actresses"):
                    success_count += 1
                else:
                    failed_count += 1

                self._persist_code_result(
                    code=code,
                    file_paths=new_code_file_map.get(code, []),
                    result=result,
                    fallback_method="AV-WIKI",
                    progress_callback=progress_callback,
                )

            self.web_searcher.batch_search(
                list(new_code_file_map.keys()),
                self.web_searcher.search_info,
                stop_event,
                progress_callback,
                result_callback=on_result,
            )
            return {
                "status": "success",
                "total_files": len(video_files),
                "new_codes": len(new_code_file_map),
                "success": success_count,
                "failed": failed_count,
            }
        except Exception as e:
            self.logger.error(f"搜尋過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def process_and_search_japanese_sites(
        self,
        folder_path: str,
        stop_event: threading.Event,
        progress_callback=None,
        use_avwiki_concurrent=True,
    ):
        """僅使用 AV-WIKI 搜尋

        Args:
            folder_path: 資料夾路徑
            stop_event: 停止事件
            progress_callback: 進度回調函式
            use_avwiki_concurrent: 是否使用 AV-WIKI 批次併發搜尋（預設 True）
        """
        try:
            if progress_callback:
                progress_callback("🇯🇵 開始掃描資料夾 (日文網站搜尋模式)...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {"status": "success", "message": "未發現影片檔案"}
            if progress_callback:
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")

            codes_in_db = {v["code"] for v in self.db_manager.get_all_videos()}
            new_code_file_map = {}
            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if code and code not in codes_in_db:
                    if code not in new_code_file_map:
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
            if progress_callback:
                progress_callback(
                    f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n"
                )
                progress_callback(
                    f"🎯 需要透過日文網站搜尋 {len(new_code_file_map)} 個新番號。\n\n"
                )
            if not new_code_file_map:
                if progress_callback:
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {"status": "success", "message": "所有番號都已存在於資料庫中"}

            # 使用 AV-WIKI 批次併發搜尋（如果啟用）
            if use_avwiki_concurrent and self.web_searcher.avwiki_concurrent_enabled:
                if progress_callback:
                    progress_callback(
                        f"🚀 使用 AV-WIKI 批次併發搜尋 (併發數: {self.web_searcher.avwiki_max_concurrent})...\n"
                    )
                search_results = self.web_searcher.batch_search_avwiki_concurrent(
                    list(new_code_file_map.keys()), stop_event, progress_callback
                )
            else:
                # 使用傳統日文網站專用搜尋方法
                search_results = self.web_searcher.batch_search(
                    list(new_code_file_map.keys()),
                    self.web_searcher.search_japanese_sites,
                    stop_event,
                    progress_callback,
                )
            success_count = 0
            failed_count = 0

            for code, result in search_results.items():
                if result and result.get("actresses"):
                    success_count += 1
                else:
                    failed_count += 1
                self._persist_code_result(
                    code=code,
                    file_paths=new_code_file_map.get(code, []),
                    result=result,
                    fallback_method="日文網站",
                    progress_callback=progress_callback,
                )
            return {
                "status": "success",
                "total_files": len(video_files),
                "new_codes": len(new_code_file_map),
                "success": success_count,
                "failed": failed_count,
            }
        except Exception as e:
            self.logger.error(f"日文網站搜尋過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def process_and_search_javdb(
        self, folder_path: str, stop_event: threading.Event, progress_callback=None
    ):
        """僅使用 JAVDB 搜尋 - 支援零女優番號的二次搜尋"""
        try:
            if progress_callback:
                progress_callback("📊 開始掃描資料夾 (JAVDB 搜尋模式)...\n")
            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {"status": "success", "message": "未發現影片檔案"}
            if progress_callback:
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")

            all_videos = self.db_manager.get_all_videos()
            codes_in_db = {v["code"]: v for v in all_videos}

            new_code_file_map = {}
            research_code_file_map = {}
            zero_actress_code_map = {}  # 專門追蹤零女優番號

            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code:
                    continue

                if code not in codes_in_db:
                    # 全新番號，需要搜尋
                    if code not in new_code_file_map:
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
                else:
                    # 番號已在資料庫中，檢查是否需要重新搜尋
                    video_record = codes_in_db[code]
                    search_status = video_record.get("search_status", "not_searched")
                    last_search_date = video_record.get("last_search_date")
                    actresses = video_record.get("actresses", [])

                    # 重新搜尋條件：
                    # 1. 搜尋過但無結果 (searched_not_found)
                    # 2. 搜尋失敗 (search_error)
                    # 3. 有 0 位女優的記錄（新增：零女優番號）
                    # 4. 超過 7 天未搜尋
                    should_research = False

                    if search_status in ["searched_not_found", "search_error", "failed"]:
                        should_research = True
                    elif not actresses or len(actresses) == 0:
                        # 特別處理零女優番號
                        if code not in zero_actress_code_map:
                            zero_actress_code_map[code] = []
                        zero_actress_code_map[code].append(file_path)
                        should_research = False  # 在第二輪單獨處理
                    elif _should_research_stale_record(code, last_search_date):
                        should_research = True

                    if should_research:
                        if code not in research_code_file_map:
                            research_code_file_map[code] = []
                        research_code_file_map[code].append(file_path)

            if progress_callback:
                progress_callback(
                    f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n"
                )
                progress_callback(f"🎯 需要搜尋 {len(new_code_file_map)} 個新番號。\n")
                if research_code_file_map:
                    progress_callback(
                        f"🔄 需要重新搜尋 {len(research_code_file_map)} 個之前無結果的番號。\n"
                    )
                if zero_actress_code_map:
                    progress_callback(
                        f"⚠️ 發現 {len(zero_actress_code_map)} 個零女優番號，將進行重新搜尋。\n"
                    )
                if research_code_file_map or zero_actress_code_map:
                    progress_callback("\n")

            # 合併新搜尋和重新搜尋的番號
            all_codes_to_search = dict(new_code_file_map)
            all_codes_to_search.update(research_code_file_map)

            # 添加零女優番號到搜尋清單
            for code in zero_actress_code_map:
                if code not in all_codes_to_search:
                    all_codes_to_search[code] = []
                all_codes_to_search[code].extend(zero_actress_code_map[code])

            if not all_codes_to_search:
                if progress_callback:
                    progress_callback("🎉 所有影片都已有最新搜尋結果！\n")
                return {"status": "success", "message": "所有番號都已存在於資料庫中"}

            # ===== 第一輪搜尋 =====
            if progress_callback:
                progress_callback(
                    f"🔍 開始第一輪搜尋 ({len(all_codes_to_search)} 個番號)...\n\n"
                )

            # 使用 JAVDB 專用搜尋方法
            success_count = 0
            failed_count = 0
            second_round_codes = {}  # 第二輪搜尋的番號

            def on_first_round_result(
                code: str, result: dict | None, _error: Exception | None
            ):
                nonlocal success_count, failed_count
                if result and result.get("actresses"):
                    success_count += 1
                    if progress_callback:
                        progress_callback(
                            f"✅ {code}: 找到 {len(result.get('actresses', []))} 位女優\n"
                        )
                    self._persist_code_result(
                        code=code,
                        file_paths=all_codes_to_search.get(code, []),
                        result=result,
                        fallback_method="JAVDB",
                        progress_callback=progress_callback,
                    )
                    return

                failed_count += 1

                # 零女優番號先不落盤失敗，交給第二輪複寫最終結果
                if code in zero_actress_code_map:
                    if progress_callback:
                        progress_callback(f"⚠️ {code}: 仍無女優資訊，標記為二次搜尋\n")
                    second_round_codes[code] = all_codes_to_search.get(code, [])
                    return

                if progress_callback:
                    progress_callback(f"❌ {code}: 搜尋無結果\n")
                self._persist_code_result(
                    code=code,
                    file_paths=all_codes_to_search.get(code, []),
                    result=None,
                    fallback_method="JAVDB",
                    progress_callback=progress_callback,
                )

            self.web_searcher.batch_search(
                list(all_codes_to_search.keys()),
                self.web_searcher.search_javdb_only,
                stop_event,
                progress_callback,
                result_callback=on_first_round_result,
            )

            # ===== 第二輪搜尋（清除快取重新搜尋零女優番號） =====
            second_round_success = 0
            if second_round_codes:
                if progress_callback:
                    progress_callback(
                        f"\n🔄 開始第二輪搜尋（清除快取，重新查詢 {len(second_round_codes)} 個零女優番號）...\n\n"
                    )

                # 清除這些番號的快取
                for code in second_round_codes:
                    if hasattr(self.web_searcher, "javdb_searcher"):
                        self.web_searcher.javdb_searcher.clear_cache_for_code(code)
                        if progress_callback:
                            progress_callback(f"🧹 已清除 {code} 的快取\n")

                if progress_callback:
                    progress_callback("\n🔍 重新查詢...\n\n")

                # 第二輪搜尋
                def on_second_round_result(
                    code: str, result: dict | None, _error: Exception | None
                ):
                    nonlocal second_round_success
                    if result and result.get("actresses"):
                        second_round_success += 1
                        if progress_callback:
                            progress_callback(
                                f"✅ 二次搜尋成功 {code}: 找到 {len(result.get('actresses', []))} 位女優\n"
                            )
                        self._persist_code_result(
                            code=code,
                            file_paths=second_round_codes.get(code, []),
                            result={
                                **result,
                                "source": f"{result.get('source', 'JAVDB')} (二次搜尋)",
                            },
                            fallback_method="JAVDB (二次搜尋)",
                            progress_callback=progress_callback,
                            log_prefix="二次搜尋 ",
                        )
                    else:
                        if progress_callback:
                            progress_callback(f"❌ 二次搜尋失敗 {code}: 仍無女優資訊\n")
                        self._persist_code_result(
                            code=code,
                            file_paths=second_round_codes.get(code, []),
                            result=None,
                            fallback_method="JAVDB (二次搜尋)",
                            progress_callback=progress_callback,
                            log_prefix="二次搜尋 ",
                        )

                self.web_searcher.batch_search(
                    list(second_round_codes.keys()),
                    self.web_searcher.search_javdb_only,
                    stop_event,
                    progress_callback,
                    result_callback=on_second_round_result,
                )

            return {
                "status": "success",
                "total_files": len(video_files),
                "new_codes": len(new_code_file_map),
                "research_codes": len(research_code_file_map),
                "zero_actress_codes": len(zero_actress_code_map),
                "first_round_success": success_count,
                "first_round_failed": failed_count,
                "second_round_success": second_round_success,
            }
        except Exception as e:
            self.logger.error(f"JAVDB 搜尋過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def process_and_search_cascade(
        self,
        folder_path: str,
        stop_event: threading.Event,
        progress_callback=None,
        enable_cascade: bool = False,
    ):
        """舊級聯搜尋 API 的相容入口，目前僅使用 AV-WIKI。

        Args:
            folder_path: 資料夾路徑
            stop_event: 停止事件
            progress_callback: 進度回調函式
            enable_cascade: 已停用，保留相容簽章

        Returns:
            dict: 包含搜尋統計的結果字典
        """
        try:
            if progress_callback:
                progress_callback("🔄 開始掃描資料夾 (AV-WIKI 搜尋模式)...\n")

            video_files = self.file_scanner.scan_directory(folder_path)
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 未發現任何影片檔案。\n")
                return {"status": "success", "message": "未發現影片檔案"}

            if progress_callback:
                progress_callback(f"📁 發現 {len(video_files)} 個影片檔案。\n")

            # 取得資料庫中已有的番號及其女優資訊
            all_videos = self.db_manager.get_all_videos()
            codes_in_db = {v["code"] for v in all_videos}

            # 🔧 識別零女優番號（已存在但沒有女優資料的番號）
            zero_actress_codes = set()
            for video in all_videos:
                actresses = video.get("actresses", [])
                if not actresses or len(actresses) == 0:
                    zero_actress_codes.add(video["code"])

            new_code_file_map = {}
            zero_actress_file_map = {}  # 零女優番號的檔案映射

            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code:
                    continue

                # 新番號
                if code not in codes_in_db:
                    if code not in new_code_file_map:
                        new_code_file_map[code] = []
                    new_code_file_map[code].append(file_path)
                # 零女優番號（需要重新搜尋）
                elif code in zero_actress_codes:
                    if code not in zero_actress_file_map:
                        zero_actress_file_map[code] = []
                    zero_actress_file_map[code].append(file_path)

            if progress_callback:
                progress_callback(
                    f"✅ 資料庫中已存在 {len(codes_in_db)} 個影片的番號記錄。\n"
                )
                if zero_actress_file_map:
                    progress_callback(
                        f"⚠️ 發現 {len(zero_actress_file_map)} 個零女優番號，將進行重新搜尋。\n"
                    )
                if new_code_file_map:
                    progress_callback(
                        f"🎯 需要搜尋 {len(new_code_file_map)} 個新番號。\n\n"
                    )

            # 合併新番號和零女優番號
            all_codes_to_search = dict(new_code_file_map)
            for code, files in zero_actress_file_map.items():
                if code not in all_codes_to_search:
                    all_codes_to_search[code] = []
                all_codes_to_search[code].extend(files)

            if not all_codes_to_search:
                if progress_callback:
                    progress_callback("🎉 所有影片都已在資料庫中！\n")
                return {"status": "success", "message": "所有番號都已存在於資料庫中"}

            # 處理搜尋結果（逐筆即時寫入）
            success_count = 0
            failed_codes = []
            source_stats = {}
            processed_codes = set()

            def on_cascade_result(
                code: str, result: dict | None, _error: Exception | None
            ):
                nonlocal success_count
                processed_codes.add(code)
                actresses = result.get("actresses", []) if result else []
                final_source = (
                    result.get("final_source")
                    if result
                    else ("cascade" if enable_cascade else "AV-WIKI")
                )
                source_name = (
                    result.get("source")
                    if result and result.get("source")
                    else final_source or ("cascade" if enable_cascade else "AV-WIKI")
                )

                if actresses:
                    success_count += 1
                    source_stats[source_name] = source_stats.get(source_name, 0) + 1
                    self._persist_code_result(
                        code=code,
                        file_paths=all_codes_to_search.get(code, []),
                        result={**(result or {}), "source": source_name},
                        fallback_method=source_name,
                        progress_callback=progress_callback,
                    )
                else:
                    failed_codes.append(code)
                    self._persist_code_result(
                        code=code,
                        file_paths=all_codes_to_search.get(code, []),
                        result=None,
                        fallback_method="AV-WIKI",
                        progress_callback=progress_callback,
                    )

            if progress_callback:
                progress_callback("🔍 使用 AV-WIKI 單一搜尋模式\n\n")

            search_results = self.web_searcher.batch_cascade_search(
                list(all_codes_to_search.keys()),
                stop_event,
                progress_callback,
                enable_javdb=False,
                result_callback=on_cascade_result,
            )

            # 確保中斷/例外情境下仍補齊尚未處理的結果
            for code, result in search_results.items():
                if code in processed_codes:
                    continue
                on_cascade_result(code, result, None)

            # 輸出統計摘要
            if progress_callback:
                progress_callback("\n" + "=" * 50 + "\n")
                progress_callback("📊 搜尋結果摘要\n")
                progress_callback("=" * 50 + "\n")
                progress_callback(
                    f"✅ 成功: {success_count}/{len(all_codes_to_search)}\n"
                )
                progress_callback(
                    f"❌ 失敗: {len(failed_codes)}/{len(all_codes_to_search)}\n"
                )
                if source_stats:
                    progress_callback("\n📈 各來源貢獻:\n")
                    for source, count in sorted(
                        source_stats.items(), key=lambda x: -x[1]
                    ):
                        progress_callback(f"  • {source}: {count} 個\n")
                if failed_codes and len(failed_codes) <= 10:
                    progress_callback(f"\n⚠️ 未找到的番號: {', '.join(failed_codes)}\n")
                elif failed_codes:
                    progress_callback(
                        f"\n⚠️ 未找到的番號: {', '.join(failed_codes[:10])}... 等 {len(failed_codes)} 個\n"
                    )

            return {
                "status": "success",
                "total_files": len(video_files),
                "new_codes": len(new_code_file_map),
                "success": success_count,
                "failed": len(failed_codes),
                "failed_codes": failed_codes,
                "source_stats": source_stats,
            }
        except Exception as e:
            self.logger.error(f"AV-WIKI 搜尋過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def interactive_move_files(self, folder_path_str: str, progress_callback=None):
        """互動式檔案移動 - 支援多女優共演的偏好選擇"""
        try:
            folder_path = Path(folder_path_str)
            if progress_callback:
                progress_callback(f"🔍 開始掃描 {folder_path} 並準備互動式移動...\n")
            video_files = self.file_scanner.scan_directory(
                folder_path_str, recursive=False
            )
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 目標資料夾中沒有影片檔案可移動。\n")
                return {
                    "status": "success",
                    "message": "目標資料夾中沒有影片檔案可移動。",
                }

            move_stats = {
                "success": 0,
                "exists": 0,
                "no_data": 0,
                "failed": 0,
                "skipped": 0,
            }
            skip_all = False

            # 分析需要互動選擇的檔案
            collaboration_files = []
            single_files = []
            no_data_files = []

            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code:
                    continue
                info = self.db_manager.get_video_info(code)
                if not info or not info.get("actresses"):
                    # 記錄沒有資料的檔案
                    no_data_files.append((file_path, code))
                    continue

                actresses = info["actresses"]
                # 使用正確的解析邏輯來判斷單人/多人共演
                parsed_actresses, is_collaboration = self._parse_actresses_list(
                    actresses
                )

                if not is_collaboration:
                    # 單人作品
                    single_files.append((file_path, code, parsed_actresses, info))
                else:
                    # 多人共演作品
                    collaboration_files.append(
                        (file_path, code, parsed_actresses, info)
                    )

            # 如果所有檔案都沒有資料,提示使用者先進行搜尋
            if no_data_files and not single_files and not collaboration_files:
                if progress_callback:
                    progress_callback(
                        f"\n⚠️ 發現 {len(no_data_files)} 個檔案沒有女優資料。\n"
                    )
                    progress_callback(
                        "💡 建議先使用「日文網站搜尋」或「JAVDB 搜尋」功能取得女優資訊。\n"
                    )
                return {
                    "status": "no_data",
                    "message": f"找到 {len(no_data_files)} 個檔案,但資料庫中沒有女優資訊。請先進行搜尋。",
                    "no_data_count": len(no_data_files),
                }

            if progress_callback:
                progress_callback(
                    f"📊 分析結果: {len(single_files)} 個單人作品, {len(collaboration_files)} 個多人共演作品"
                )
                if no_data_files:
                    progress_callback(f", {len(no_data_files)} 個無資料檔案\n")
                else:
                    progress_callback("\n")
                if collaboration_files:
                    progress_callback("🤝 開始處理多人共演作品的分類選擇...\n\n")
            # 處理所有檔案
            all_files = single_files + collaboration_files

            for i, (file_path, code, actresses, _) in enumerate(all_files, 1):
                if skip_all:
                    move_stats["skipped"] += 1
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
                            choice, remember = (
                                self.interactive_classifier.get_classification_choice(
                                    code, actresses
                                )
                            )

                            if choice == "SKIP_ALL":
                                skip_all = True
                                move_stats["skipped"] += 1
                                if progress_callback:
                                    progress_callback("⏭️ 使用者選擇跳過所有後續檔案\n")
                                continue
                            elif choice == "SKIP":
                                move_stats["skipped"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"⏭️ [{i}/{len(all_files)}] 跳過: {file_path.name}\n"
                                    )
                                continue

                            target_actress = choice

                    # 記住偏好設定
                    if remember and len(actresses) > 1:
                        self.preference_manager.save_collaboration_preference(
                            actresses, target_actress
                        )
                        if progress_callback:
                            progress_callback(
                                f"🧠 已記住組合偏好: {', '.join(actresses)} → {target_actress}\n"
                            )

                    # 建立目標資料夾
                    target_folder = folder_path / target_actress
                    target_folder.mkdir(exist_ok=True)

                    # 保持原始檔名不變
                    new_filename = file_path.name

                    target_path = target_folder / new_filename

                    # 檢查檔案是否已存在
                    if target_path.exists():
                        move_stats["exists"] += 1
                        if progress_callback:
                            progress_callback(
                                f"⚠️ [{i}/{len(all_files)}] 已存在: {target_actress}/{new_filename}\n"
                            )
                        continue

                    # 執行移動（使用 FileMover 支援 Go 加速）
                    move_result = self.file_mover.move_file(file_path, target_path)
                    if not move_result["success"]:
                        if move_result.get("skipped"):
                            move_stats["exists"] += 1
                            if progress_callback:
                                progress_callback(
                                    f"⚠️ [{i}/{len(all_files)}] 已存在: {target_actress}/{new_filename}\n"
                                )
                            continue
                        raise Exception(move_result.get("error", "移動失敗"))
                    move_stats["success"] += 1

                    if len(actresses) > 1:
                        actresses_display = f" (共演: {', '.join(actresses)})"
                    else:
                        actresses_display = ""

                    if progress_callback:
                        progress_callback(
                            f"✅ [{i}/{len(all_files)}] {file_path.name} → {target_actress}/{new_filename}{actresses_display}\n"
                        )

                except Exception as e:
                    move_stats["failed"] += 1
                    logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                    if progress_callback:
                        progress_callback(
                            f"❌ [{i}/{len(all_files)}] {file_path.name}: 移動失敗 - {str(e)}\n"
                        )

            return {
                "status": "success",
                "total_files": len(video_files),
                "stats": move_stats,
            }

        except Exception as e:
            self.logger.error(f"互動式檔案移動過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def smart_search_and_move(
        self,
        folder_path: str,
        stop_event: threading.Event,
        progress_callback=None,
        use_full_search=False,
    ):
        """智慧搜尋並分類：自動搜尋無資料番號，然後執行智慧分類

        Args:
            folder_path: 資料夾路徑
            stop_event: 停止事件
            progress_callback: 進度回調函式
            use_full_search: 是否使用完整搜尋（包含 JAVDB），預設 False（只用日文網站）
        """
        try:
            if progress_callback:
                progress_callback(
                    f"🔍📁 智慧搜尋並分類模式\n目標資料夾: {folder_path}\n{'=' * 60}\n"
                )

            # 步驟 1: 掃描檔案
            if progress_callback:
                progress_callback("📂 步驟 1/3: 掃描影片檔案...\n")

            Path(folder_path)
            video_files = self.file_scanner.scan_directory(folder_path, recursive=False)

            if not video_files:
                if progress_callback:
                    progress_callback("🤷 目標資料夾中沒有影片檔案。\n")
                return {"status": "success", "message": "目標資料夾中沒有影片檔案。"}

            if progress_callback:
                progress_callback(f"✅ 找到 {len(video_files)} 個影片檔案\n\n")

            # 步驟 2: 檢查哪些需要搜尋
            if progress_callback:
                progress_callback("🔍 步驟 2/3: 檢查並搜尋無資料番號...\n")

            codes_need_search = []
            code_file_map = {}

            for file_path in video_files:
                if stop_event.is_set():
                    if progress_callback:
                        progress_callback("\n🛑 任務已中止。\n")
                    return {"status": "cancelled", "message": "任務已中止"}

                code = self.code_extractor.extract_code(file_path.name)
                if not code:
                    continue

                info = self.db_manager.get_video_info(code)
                # 需要搜尋的條件：
                # 1. 資料庫中沒有此番號
                # 2. 有番號但女優列表為空
                # 3. 搜尋狀態為 search_error 或 no_actress_found
                if (
                    not info
                    or not info.get("actresses")
                    or info.get("search_status") in ["search_error", "no_actress_found"]
                ):
                    codes_need_search.append(code)
                    code_file_map[code] = file_path

            # 執行搜尋
            if codes_need_search:
                if progress_callback:
                    progress_callback(
                        f"📊 需要搜尋 {len(codes_need_search)} 個番號\n\n"
                    )

                if use_full_search and progress_callback:
                    progress_callback(
                        "ℹ️ 自動 JAVDB 備援已停用，改用 AV-WIKI 搜尋；JAVDB 保留為獨立按鈕。\n"
                    )
                elif progress_callback:
                    progress_callback("🇯🇵 使用 AV-WIKI 搜尋...\n")

                search_method = self.web_searcher.search_japanese_sites

                # 批次搜尋
                search_results = self.web_searcher.batch_search(
                    codes_need_search, search_method, stop_event, progress_callback
                )

                # 儲存搜尋結果
                from datetime import datetime

                current_time = datetime.now().isoformat()
                success_count = 0

                for code, result in search_results.items():
                    if stop_event.is_set():
                        break

                    if result and result.get("actresses"):
                        success_count += 1
                        file_path = code_file_map.get(code)
                        if file_path:
                            studio = result.get("studio")
                            if not studio or studio == "UNKNOWN":
                                studio = self.studio_identifier.identify_studio(code)

                            info = {
                                "actresses": result["actresses"],
                                "original_filename": file_path.name,
                                "file_path": str(file_path),
                                "studio": studio,
                                "search_method": result.get("source", "未知"),
                                "search_status": "searched_found",
                                "last_search_date": current_time,
                            }
                            self.db_manager.add_or_update_video(code, info)

                if progress_callback:
                    progress_callback(
                        f"\n✅ 搜尋完成: {success_count}/{len(codes_need_search)} 個番號找到資料\n\n"
                    )
            else:
                if progress_callback:
                    progress_callback("✅ 所有番號都已有資料，跳過搜尋步驟\n\n")

            # 步驟 3: 執行智慧分類
            if stop_event.is_set():
                if progress_callback:
                    progress_callback("\n🛑 任務已中止。\n")
                return {"status": "cancelled", "message": "任務已中止"}

            if progress_callback:
                progress_callback("📁 步驟 3/3: 執行智慧分類...\n\n")

            # 呼叫原有的智慧分類方法
            result = self.move_files(folder_path, progress_callback)

            return result

        except Exception as e:
            self.logger.error(f"智慧搜尋並分類過程中發生錯誤: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"❌ 發生錯誤: {e}\n")
            return {"status": "error", "message": str(e)}

    def move_files(self, folder_path_str: str, progress_callback=None):
        """智慧檔案移動 - 單人自動分類，多人共演啟動互動選擇"""
        try:
            folder_path = Path(folder_path_str)
            if progress_callback:
                progress_callback(f"🔍 開始掃描 {folder_path} 並準備智慧移動...\n")
            video_files = self.file_scanner.scan_directory(
                folder_path_str, recursive=False
            )
            if not video_files:
                if progress_callback:
                    progress_callback("🤷 目標資料夾中沒有影片檔案可移動。\n")
                return {
                    "status": "success",
                    "message": "目標資料夾中沒有影片檔案可移動。",
                }
            # 分析檔案，區分單人和多人共演作品
            single_actress_files = []
            collaboration_files = []
            no_data_files = []

            for file_path in video_files:
                code = self.code_extractor.extract_code(file_path.name)
                if not code:
                    continue
                info = self.db_manager.get_video_info(code)
                if not info or not info.get("actresses"):
                    no_data_files.append(file_path)
                    continue

                actresses = info["actresses"]
                # 使用新的解析邏輯來判斷單人/多人共演
                parsed_actresses, is_collaboration = self._parse_actresses_list(
                    actresses
                )

                if not is_collaboration:
                    # 單人作品
                    single_actress_files.append(
                        (file_path, code, parsed_actresses[0], info)
                    )
                else:
                    # 多人共演作品
                    collaboration_files.append(
                        (file_path, code, parsed_actresses, info)
                    )

            if progress_callback:
                progress_callback(
                    f"📊 分析結果: {len(single_actress_files)} 個單人作品, {len(collaboration_files)} 個多人共演作品, {len(no_data_files)} 個無資料檔案\n"
                )

                if collaboration_files:
                    progress_callback("🤝 發現多人共演作品，將啟動互動式分類模式\n\n")

            move_stats = {
                "success": 0,
                "exists": 0,
                "no_data": 0,
                "failed": 0,
                "interactive": 0,
            }
            total_files = len(video_files)
            processed = 0

            # 先處理單人作品（自動分類）
            if single_actress_files:
                if progress_callback:
                    progress_callback(
                        f"🏃 開始自動處理 {len(single_actress_files)} 個單人作品...\n"
                    )

                for file_path, _, main_actress, _ in single_actress_files:
                    processed += 1
                    target_folder = folder_path / main_actress
                    target_folder.mkdir(exist_ok=True)
                    target_path = target_folder / file_path.name

                    if target_path.exists():
                        move_stats["exists"] += 1
                        if progress_callback:
                            progress_callback(
                                f"⚠️ [{processed}/{total_files}] {file_path.name}: 檔案已存在於目標資料夾\n"
                            )
                        continue

                    try:
                        # 使用 FileMover 支援 Go 加速
                        move_result = self.file_mover.move_file(file_path, target_path)
                        if move_result["success"] and not move_result.get("skipped"):
                            move_stats["success"] += 1
                            if progress_callback:
                                progress_callback(
                                    f"✅ [{processed}/{total_files}] {file_path.name} → {main_actress}/\n"
                                )
                        elif move_result.get("skipped"):
                            move_stats["exists"] += 1
                            if progress_callback:
                                progress_callback(
                                    f"⚠️ [{processed}/{total_files}] {file_path.name}: 檔案已存在\n"
                                )
                        else:
                            raise Exception(move_result.get("error", "移動失敗"))
                    except Exception as e:
                        move_stats["failed"] += 1
                        logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                        if progress_callback:
                            progress_callback(
                                f"❌ [{processed}/{total_files}] {file_path.name}: 移動失敗\n"
                            )

            # 處理無資料檔案
            if no_data_files and progress_callback:
                progress_callback(f"\n{'=' * 60}\n")
                progress_callback(f"❓ 發現 {len(no_data_files)} 個無資料檔案:\n")
                for i, file_path in enumerate(no_data_files[:5], 1):
                    progress_callback(f"  {i}. {file_path.name}\n")
                if len(no_data_files) > 5:
                    progress_callback(f"  ... 還有 {len(no_data_files) - 5} 個檔案\n")

                progress_callback("\n💡 建議操作：\n")
                progress_callback(
                    "  1. 先對此資料夾執行「完整搜尋」或「日文網站搜尋」\n"
                )
                progress_callback("  2. 等待搜尋完成後，再執行「智慧分類」\n")
                progress_callback(
                    "  \n  或使用「🔍📁 智慧搜尋並分類」功能（一鍵完成）\n"
                )
                progress_callback(f"{'=' * 60}\n\n")

            for _ in no_data_files:
                processed += 1
                move_stats["no_data"] += 1

            # 處理多人共演作品（互動式分類）
            if collaboration_files:
                if progress_callback:
                    progress_callback(
                        f"\n🎯 開始互動式處理 {len(collaboration_files)} 個多人共演作品...\n"
                    )

                skip_all = False

                for file_path, code, actresses, _ in collaboration_files:
                    processed += 1

                    if skip_all:
                        move_stats["interactive"] += 1
                        if progress_callback:
                            progress_callback(
                                f"⏭️ [{processed}/{total_files}] 跳過: {file_path.name}\n"
                            )
                        continue

                    try:
                        # 決定分類目標
                        if not self.interactive_classifier:
                            # 沒有互動分類器時，使用第一位女優
                            target_actress = actresses[0]
                            remember = False
                            if progress_callback:
                                progress_callback(
                                    f"🤖 [{processed}/{total_files}] 無互動分類器，使用第一位女優: {actresses[0]}\n"
                                )
                        else:
                            choice, remember = (
                                self.interactive_classifier.get_classification_choice(
                                    code, actresses
                                )
                            )

                            if choice == "SKIP_ALL":
                                skip_all = True
                                move_stats["interactive"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"⏭️ [{processed}/{total_files}] 使用者選擇跳過所有後續多人共演檔案\n"
                                    )
                                continue
                            elif choice == "SKIP":
                                move_stats["interactive"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"⏭️ [{processed}/{total_files}] 跳過: {file_path.name}\n"
                                    )
                                continue

                            target_actress = choice

                        # 記住偏好設定
                        if remember and len(actresses) > 1 and self.preference_manager:
                            self.preference_manager.save_collaboration_preference(
                                actresses, target_actress
                            )
                            if progress_callback:
                                progress_callback(
                                    f"🧠 已記住組合偏好: {', '.join(actresses)} → {target_actress}\n"
                                )

                        # 建立目標資料夾
                        target_folder = folder_path / target_actress
                        target_folder.mkdir(exist_ok=True)

                        # 保持原始檔名不變
                        new_filename = file_path.name

                        target_path = target_folder / new_filename

                        # 檢查檔案是否已存在
                        if target_path.exists():
                            move_stats["exists"] += 1
                            if progress_callback:
                                progress_callback(
                                    f"⚠️ [{processed}/{total_files}] 已存在: {target_actress}/{new_filename}\n"
                                )
                            continue
                        # 執行移動（使用 FileMover 支援 Go 加速）
                        move_result = self.file_mover.move_file(file_path, target_path)
                        if not move_result["success"]:
                            if move_result.get("skipped"):
                                move_stats["exists"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"⚠️ [{processed}/{total_files}] 已存在: {target_actress}/{new_filename}\n"
                                    )
                                continue
                            raise Exception(move_result.get("error", "移動失敗"))
                        move_stats["success"] += 1
                        move_stats["interactive"] += 1

                        actresses_display = f" (共演: {', '.join(actresses)})"
                        if progress_callback:
                            progress_callback(
                                f"✅ [{processed}/{total_files}] {file_path.name} → {target_actress}/{new_filename}{actresses_display}\n"
                            )

                    except Exception as e:
                        move_stats["failed"] += 1
                        logger.error(f"移動檔案 {file_path.name} 失敗: {e}")
                        if progress_callback:
                            progress_callback(
                                f"❌ [{processed}/{total_files}] {file_path.name}: 移動失敗 - {str(e)}\n"
                            )

            if progress_callback and collaboration_files:
                progress_callback(
                    f"\n🎉 智慧分類完成！共處理 {move_stats['interactive']} 個多人共演作品\n"
                )

            return {
                "status": "success",
                "total_files": len(video_files),
                "stats": move_stats,
            }
        except Exception as e:
            self.logger.error(f"檔案移動過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

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
        if "#" in actress_str:
            # 解析 # 分隔的女優名單
            parsed_actresses = []
            for name in actress_str.split("#"):
                name = name.strip()
                if name:
                    parsed_actresses.append(name)

            return parsed_actresses, len(parsed_actresses) > 1

        # 單一女優
        return [actress_str], False
