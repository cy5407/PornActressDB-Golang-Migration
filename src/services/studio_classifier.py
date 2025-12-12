"""
片商分類核心功能模組
"""

import logging
import shutil
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class StudioClassificationCore:
    """片商分類核心類別"""

    def __init__(
        self, db_manager, code_extractor, studio_identifier, preference_manager
    ):
        self.db_manager = db_manager
        self.code_extractor = code_extractor
        self.studio_identifier = studio_identifier
        self.preference_manager = preference_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.supported_formats = [
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".ts",
            ".m2ts",
        ]
        self._major_studios = self._identify_major_studios()  # 初始化時建立大片商集合

    def classify_actresses_by_studio(
        self, root_path: str, progress_callback=None
    ) -> dict:
        """按片商分類女優資料夾的主要功能"""
        try:
            root_folder = Path(root_path)

            if progress_callback:
                progress_callback(f"🏢 開始片商分類：{root_path}\n")
                progress_callback("=" * 60 + "\n")
            # 第一步：掃描所有女優資料夾
            actress_folders = self._scan_actress_folders(root_folder, progress_callback)
            if not actress_folders:
                if progress_callback:
                    progress_callback("🤷 未找到任何女優資料夾\n")
                # 返回空的移動統計，避免 GUI 錯誤
                empty_move_stats = {
                    "moved": 0,
                    "solo_artist": 0,
                    "failed": 0,
                    "skipped": 0,
                }
                return {
                    "status": "success",
                    "message": "未找到女優資料夾",
                    "total_actresses": 0,
                    "updated_count": 0,
                    "move_stats": empty_move_stats,
                }

            if progress_callback:
                progress_callback(f"📁 發現 {len(actress_folders)} 個女優資料夾\n\n")

            # 第二步：重新掃描並更新統計資料
            updated_stats = self._update_actress_statistics(
                actress_folders, progress_callback
            )

            # 第三步：按片商分類移動
            move_stats = self._move_actresses_by_studio(
                root_folder, updated_stats, progress_callback
            )

            return {
                "status": "success",
                "total_actresses": len(actress_folders),
                "updated_count": len(updated_stats),
                "move_stats": move_stats,
            }

        except Exception as e:
            self.logger.error(f"片商分類過程中發生錯誤: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _scan_actress_folders(
        self, root_folder: Path, progress_callback=None
    ) -> list[Path]:
        """只掃描根目錄第一層的女優資料夾（避免遞迴問題）"""
        actress_folders = []
        skipped_by_parent = []  # 記錄因父資料夾而被跳過的資料夾

        if progress_callback:
            progress_callback("🔍 正在掃描根目錄的女優資料夾（僅第一層）...\n")

        try:
            # 只掃描第一層子目錄，避免遞迴掃描已分類的片商資料夾
            all_dirs = list(root_folder.iterdir())
            dir_count = sum(1 for item in all_dirs if item.is_dir())

            if progress_callback:
                progress_callback(f"📊 發現 {dir_count} 個子資料夾，正在檢查...\n")

            for item in all_dirs:
                if item.is_dir():
                    # 檢查是否已在片商資料夾內
                    parent_name = item.parent.name
                    studio_folders = {
                        "E-BODY",
                        "FALENO",
                        "S1",
                        "SOD",
                        "PRESTIGE",
                        "MOODYZ",
                        "MADONNA",
                        "IdeaPocket",
                        "KAWAII",
                        "單體企劃女優",
                        "SOLO_ACTRESS",
                        "INDEPENDENT",
                        "OPPAI",
                        "FITCH",
                        "ATTACKERS",
                        "PREMIUM",
                        "DAS",
                        "WANZ FACTORY",
                        "kira☆kira",
                        "Moody's",
                        "kawaii*",
                        "S1 NO.1 STYLE",
                        "IDEAPOCKET",
                    }

                    if parent_name.upper() in studio_folders:
                        skipped_by_parent.append(item.name)
                        continue

                    is_actress = self._is_actress_folder(item, progress_callback)
                    if is_actress:
                        actress_folders.append(item)

            # 如果有資料夾因為已在片商資料夾內而被跳過，顯示提示
            if skipped_by_parent and progress_callback:
                progress_callback(
                    f"\n⚠️ 發現 {len(skipped_by_parent)} 個女優資料夾已在片商資料夾「{parent_name}」內\n"
                )
                progress_callback(
                    "💡 若需重新分類這些女優，請先將她們的資料夾移出片商資料夾\n"
                )
                if len(skipped_by_parent) <= 10:
                    progress_callback(f"   已跳過: {', '.join(skipped_by_parent)}\n")
                else:
                    progress_callback(
                        f"   已跳過: {', '.join(skipped_by_parent[:10])}... 等 {len(skipped_by_parent)} 個\n"
                    )
                progress_callback("\n")

            return actress_folders

        except Exception as e:
            self.logger.error(f"掃描女優資料夾失敗: {e}")
            if progress_callback:
                progress_callback(f"❌ 掃描失敗: {e}\n")
            return []

    def _is_actress_folder(self, folder_path: Path, progress_callback=None) -> bool:
        """
        判斷是否為女優資料夾
        策略：優先檢查資料庫，資料夾名稱在資料庫中 = 女優資料夾
        """
        folder_name = folder_path.name
        folder_name_upper = folder_name.upper()
        # 排除明顯的片商資料夾名稱（使用統一的大片商名單）
        studio_folders = {
            "E-BODY",
            "FALENO",
            "S1",
            "SOD",
            "PRESTIGE",
            "MOODYZ",
            "MADONNA",
            "IdeaPocket",
            "KAWAII",
            "單體企劃女優",
            "SOLO_ACTRESS",
            "INDEPENDENT",
            "OPPAI",
            "FITCH",
            "ATTACKERS",
            "PREMIUM",
            "DAS",
            "WANZ FACTORY",
            "kira☆kira",
            "Moody's",
            "kawaii*",
            "S1 NO.1 STYLE",
            "IDEAPOCKET",
        }

        # 排除通用/系統資料夾名稱
        excluded_folders = {
            "AV",
            "VIDEO",
            "VIDEOS",
            "MOVIE",
            "MOVIES",
            "FILM",
            "FILMS",
            "DOWNLOAD",
            "DOWNLOADS",
            "TEMP",
            "TMP",
            "CACHE",
            "BACKUP",
            "OLD",
            "NEW",
            "ARCHIVE",
            "ARCHIVED",
            "UNSORTED",
            "未分類",
            "OTHER",
            "OTHERS",
            "MISC",
            "MISCELLANEOUS",
            "其他",
            "雜項",
            "COLLECTION",
            "COLLECTIONS",
            "SERIES",
            "系列",
            "合集",
            "FOLDER",
            "FOLDERS",
            "DIR",
            "DIRECTORY",
            "DATA",
            "UNCENSORED",
            "CENSORED",
            "無碼",
            "有碼",
            "FC2",
            "PPV",
            "DELETED",
            "TRASH",
            "RECYCLE",
            "回收站",
            "垃圾桶",
            "轉檔1",
            "轉檔2",
            "轉檔3",
            "轉檔",
            "CONVERT",
            "ENCODING",
            "AV2",
            "20251110",
            "轉編1",
        }

        # 組合所有需要排除的資料夾
        all_excluded = studio_folders | excluded_folders

        if folder_name_upper in all_excluded:
            self.logger.debug(f"排除片商/系統資料夾: {folder_name}")
            return False

        # 檢查是否已經在片商資料夾內（避免重複處理）
        parent_name = folder_path.parent.name.upper()
        if parent_name in studio_folders:
            self.logger.debug(f"排除已在片商資料夾內: {folder_name}")
            return False

        # 排除過短或過長的資料夾名稱（可能不是女優名稱）
        if len(folder_name) < 2 or len(folder_name) > 30:
            self.logger.debug(
                f"排除名稱長度不符: {folder_name} (長度: {len(folder_name)})"
            )
            return False

        # 排除純數字資料夾名稱
        if folder_name.isdigit():
            self.logger.debug(f"排除純數字資料夾: {folder_name}")
            return False

        # 排除看起來像番號的資料夾名稱
        import re

        if re.match(r"^[A-Z]{2,6}-?\d{3,5}[A-Z]?$", folder_name_upper):
            self.logger.debug(f"排除番號格式資料夾: {folder_name}")
            return False

        # 🔑 關鍵邏輯：優先檢查資料庫中是否有該女優
        # 使用 analyze_actress_primary_studio 來檢查女優是否存在
        try:
            analysis_result = self.db_manager.analyze_actress_primary_studio(
                folder_name, self._major_studios
            )
            total_videos = analysis_result.get("total_videos", 0)

            if total_videos > 0:
                # 資料庫中有該女優的影片記錄
                if progress_callback:
                    progress_callback(
                        f"  ✅ {folder_name} (資料庫中有 {total_videos} 部影片)\n"
                    )
                self.logger.debug(
                    f"✅ 資料庫確認女優: {folder_name} (影片數: {total_videos})"
                )
                return True
            else:
                if progress_callback:
                    progress_callback(f"  ⚠️ {folder_name} (資料庫中無影片記錄)\n")
                self.logger.debug(f"⚠️ 資料庫中無此女優影片: {folder_name}")
        except Exception as e:
            if progress_callback:
                progress_callback(f"  ❌ {folder_name} (檢查失敗: {str(e)[:50]})\n")
            self.logger.warning(
                f"檢查女優資料庫時發生錯誤 ({folder_name}): {e}", exc_info=True
            )

        # 次要檢查：如果資料庫中沒有，檢查資料夾內是否有檔案
        try:
            has_any_files = False

            for file_path in folder_path.iterdir():
                if file_path.is_file():
                    has_any_files = True
                    # 如果有影片檔案，也認定為女優資料夾
                    if file_path.suffix.lower() in self.supported_formats:
                        self.logger.debug(f"✅ 發現影片檔案: {folder_name}")
                        return True

            # 如果有任何檔案（字幕、圖片等），也可能是女優資料夾
            if has_any_files:
                self.logger.debug(f"⚠️ 有檔案但不在資料庫中: {folder_name}")
                # 不直接返回 True，讓後續邏輯決定

        except PermissionError:
            self.logger.debug(f"無權限存取資料夾: {folder_name}")
            return False
        except Exception as e:
            self.logger.debug(f"檢查資料夾檔案時發生錯誤 ({folder_name}): {e}")

        self.logger.debug(f"❌ 不符合條件: {folder_name} (不在資料庫且無影片檔案)")
        return False

    def _update_actress_statistics(
        self, actress_folders: list[Path], progress_callback=None
    ) -> dict[str, dict]:
        """
        重新掃描女優資料夾並更新片商統計（含大片商例外邏輯）。
        若影片數<=3且屬於大片商，推薦分類為片商。
        """
        updated_stats = {}

        if progress_callback:
            progress_callback("📊 正在使用增強版演算法分析女優片商分佈...\n")

        for i, actress_folder in enumerate(actress_folders, 1):
            actress_name = actress_folder.name

            try:
                # 使用資料庫的增強分析功能
                analysis_result = self.db_manager.analyze_actress_primary_studio(
                    actress_name, self._major_studios
                )

                if analysis_result["total_videos"] > 0:
                    updated_stats[actress_name] = {
                        "folder_path": actress_folder,
                        "studio_stats": analysis_result["studio_distribution"],
                        "main_studio": analysis_result["primary_studio"],
                        "confidence": analysis_result["confidence"],
                        "total_videos": analysis_result["total_videos"],
                        "recommendation": analysis_result["recommendation"],
                        "analysis_method": "enhanced_database",
                    }

                    if progress_callback and i % 5 == 0:
                        progress_callback(
                            f"   處理進度: {i}/{len(actress_folders)} ({actress_name}: {analysis_result['primary_studio']} {analysis_result['confidence']}%)\n"
                        )

                else:
                    # 如果資料庫沒有資料，回退到檔案掃描方式
                    video_files = []
                    for file_path in actress_folder.iterdir():
                        if (
                            file_path.is_file()
                            and file_path.suffix.lower() in self.supported_formats
                        ):
                            video_files.append(file_path)

                    if video_files:  # 使用檔案掃描方式作為備援
                        studio_stats = self._calculate_studio_distribution(video_files)
                        if studio_stats:
                            main_studio, confidence = self._determine_main_studio(
                                studio_stats
                            )
                            # 只有大片商才能歸類到片商資料夾，其他都歸類單體企劃
                            if self._is_major_studio(main_studio):
                                # 大片商：影片數少時強制推薦片商分類
                                if len(video_files) <= 3 or confidence >= 50:
                                    recommendation = "studio_classification"
                                else:
                                    recommendation = "solo_artist"
                            else:
                                # 非大片商一律歸類為單體企劃
                                recommendation = "solo_artist"

                            updated_stats[actress_name] = {
                                "folder_path": actress_folder,
                                "studio_stats": studio_stats,
                                "main_studio": main_studio,
                                "confidence": confidence,
                                "total_videos": len(video_files),
                                "recommendation": recommendation,
                                "analysis_method": "file_scan_fallback",
                            }

            except Exception as e:
                self.logger.error(f"處理女優 {actress_name} 時發生錯誤: {e}")
                continue

        if progress_callback:
            progress_callback(
                f"✅ 完成增強版統計分析，處理了 {len(updated_stats)} 位女優\n"
            )

            # 顯示統計摘要
            studio_count = sum(
                1
                for stats in updated_stats.values()
                if stats["recommendation"] == "studio_classification"
            )
            solo_count = len(updated_stats) - studio_count
            progress_callback(
                f"📊 分析結果預覽: {studio_count} 位歸屬特定片商, {solo_count} 位歸為單體企劃\n\n"
            )

        return updated_stats

    def _calculate_studio_distribution(self, video_files: list[Path]) -> dict[str, int]:
        """計算影片檔案的片商分佈"""
        studio_stats = defaultdict(int)

        for video_file in video_files:
            # 提取番號
            code = self.code_extractor.extract_code(video_file.name)
            if code:
                # 識別片商
                studio = self.studio_identifier.identify_studio(code)
                if studio and studio != "UNKNOWN":
                    studio_stats[studio] += 1
        return dict(studio_stats)

    def _identify_major_studios(self) -> set:
        """
        識別所有定義為「大片商」的片商名稱集合。
        使用用戶指定的大片商名單。
        注意：片商名稱需與資料庫中的實際名稱大小寫完全一致
        """
        # 用戶指定的大片商名單（需與資料庫中的實際名稱一致）
        major_studios = {
            "E-BODY",
            "FALENO",
            "S1",
            "SOD",
            "PRESTIGE",
            "MOODYZ",
            "MADONNA",
            "IdeaPocket",
            "kawaii",  # kawaii 是小寫
            "OPPAI",
            "FITCH",
            "ATTACKERS",
            "PREMIUM",
            "DAS",
            "MOODYZ DIVA",  # 新增
            "FALENO star",
            "FALENO TUBE",  # FALENO 相關
            "kira☆kira",
            "WANZ FACTORY",
        }
        return major_studios

    def _is_major_studio(self, studio: str) -> bool:
        """
        判斷指定片商是否屬於「大片商」集合
        """
        return studio in self._major_studios

    def _determine_main_studio(self, studio_stats: dict[str, int]) -> tuple[str, float]:
        """
        根據片商分佈決定主要片商及信心度。
        改進邏輯：有大片商作品且小片商作品不多時，優先歸類大片商。
        """
        if not studio_stats:
            return "UNKNOWN", 0.0

        total_videos = sum(studio_stats.values())
        if total_videos == 0:
            return "UNKNOWN", 0.0

        # 分析大片商與小片商作品分佈
        major_studio_stats = {}
        minor_studio_work_count = 0

        for studio, count in studio_stats.items():
            if self._is_major_studio(studio):
                major_studio_stats[studio] = count
            else:
                minor_studio_work_count += count

        # 找出作品數最多的片商（整體）
        main_studio = max(studio_stats.items(), key=lambda x: x[1])
        studio_name, video_count = main_studio
        confidence = round((video_count / total_videos) * 100, 1)

        # 應用新的大片商優先邏輯
        if major_studio_stats:
            # 有大片商作品
            best_major_studio = max(major_studio_stats.items(), key=lambda x: x[1])
            major_studio_name, major_video_count = best_major_studio

            if self._is_major_studio(studio_name):
                # 最多作品的片商就是大片商
                if video_count >= 3 and confidence >= 70:
                    # 標準條件：≥3部作品且信心度≥70%
                    confidence = max(confidence, 70.0)
                elif video_count >= 1 and minor_studio_work_count < 10:
                    # 新條件：有大片商作品且小片商作品<10部
                    confidence = max(confidence, 60.0)
                    # 如果不符合標準條件但符合新條件，仍保持現有信心度
            else:
                # 最多作品的片商不是大片商，但有大片商作品
                if major_video_count >= 1 and minor_studio_work_count < 10:
                    # 優先考慮大片商
                    studio_name = major_studio_name
                    confidence = round((major_video_count / total_videos) * 100, 1)
                    confidence = max(confidence, 60.0)

        return studio_name, confidence

    def _move_actresses_by_studio(
        self, root_folder: Path, actress_stats: dict[str, dict], progress_callback=None
    ) -> dict:
        """根據片商統計移動女優資料夾"""
        move_stats = {
            "moved": 0,  # 成功移動到片商資料夾
            "solo_artist": 0,  # 移動到單體企劃女優
            "failed": 0,  # 移動失敗
            "skipped": 0,  # 跳過（來源不存在）
        }

        # 取得單體企劃女優資料夾名稱
        solo_folder_name = self.preference_manager.get_solo_folder_name()
        confidence_threshold = self.preference_manager.get_confidence_threshold()

        if progress_callback:
            progress_callback("🚚 開始按片商移動女優資料夾...\n")

        total_to_process = len(actress_stats)
        processed_count = 0

        for actress_name, stats in actress_stats.items():
            try:
                processed_count += 1
                if progress_callback:
                    progress_callback(
                        f"📍 處理進度: {processed_count}/{total_to_process} ({actress_name})\n"
                    )

                source_folder = stats["folder_path"]
                main_studio = stats["main_studio"]
                confidence = stats["confidence"]

                # 檢查來源資料夾是否存在
                if not source_folder.exists():
                    move_stats["skipped"] += 1
                    self.logger.warning(f"來源資料夾不存在，跳過: {source_folder}")
                    if progress_callback:
                        progress_callback(f"⏩ 跳過 {actress_name}: 來源資料夾不存在\n")
                    continue

                # 檢查來源是否為目錄
                if not source_folder.is_dir():
                    move_stats["skipped"] += 1
                    self.logger.warning(f"來源不是目錄，跳過: {source_folder}")
                    if progress_callback:
                        progress_callback(f"⏩ 跳過 {actress_name}: 來源不是目錄\n")
                    continue

                # 安全檢查：確保來源資料夾在根目錄的第一層
                if source_folder.parent != root_folder:
                    move_stats["skipped"] += 1
                    self.logger.warning(
                        f"來源資料夾不在根目錄第一層，跳過: {source_folder}"
                    )
                    if progress_callback:
                        progress_callback(f"⏩ 跳過 {actress_name}: 不在根目錄第一層\n")
                    continue

                # 安全檢查：確保這是真的女優資料夾
                if not self._is_actress_folder(source_folder):
                    move_stats["skipped"] += 1
                    self.logger.warning(
                        f"重新檢查發現不是女優資料夾，跳過: {source_folder}"
                    )
                    if progress_callback:
                        progress_callback(
                            f"⏩ 跳過 {actress_name}: 重新檢查後不符合女優資料夾條件\n"
                        )
                    continue

                # 決定目標片商資料夾（完全信任資料庫的推薦系統）
                recommendation = stats.get("recommendation", "solo_artist")

                # 使用資料庫的智慧推薦,不再額外檢查信心度
                # 因為 analyze_actress_primary_studio 已經包含了完整的分類邏輯
                if (
                    recommendation == "studio_classification"
                    and main_studio != "UNKNOWN"
                ):
                    target_studio_folder = root_folder / main_studio
                    category = "studio"
                else:
                    target_studio_folder = root_folder / solo_folder_name
                    category = "solo"

                # 安全檢查：避免移動到自己或循環移動
                target_actress_folder = target_studio_folder / actress_name
                if (
                    source_folder == target_studio_folder
                    or target_actress_folder == source_folder
                ):
                    move_stats["skipped"] += 1
                    if progress_callback:
                        progress_callback(f"⏩ 跳過 {actress_name}: 避免循環移動\n")
                    continue

                # 建立目標片商資料夾
                try:
                    target_studio_folder.mkdir(exist_ok=True)
                except Exception as e:
                    move_stats["failed"] += 1
                    self.logger.error(f"建立目標資料夾失敗 {target_studio_folder}: {e}")
                    if progress_callback:
                        progress_callback(
                            f"❌ {actress_name}: 無法建立目標資料夾 - {str(e)}\n"
                        )
                    continue
                # 檢查是否已存在目標資料夾
                if target_actress_folder.exists():
                    # 目標資料夾已存在，進行合併操作
                    try:
                        merge_result = self._merge_actress_folders(
                            source_folder, target_actress_folder, progress_callback
                        )
                        if merge_result["success"]:
                            if category == "solo":
                                move_stats["solo_artist"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"🔄 {actress_name} → {solo_folder_name}/ (合併 {merge_result['files_moved']} 個檔案, 信心度: {confidence}%)\n"
                                    )
                            else:
                                move_stats["moved"] += 1
                                if progress_callback:
                                    progress_callback(
                                        f"🔄 {actress_name} → {main_studio}/ (合併 {merge_result['files_moved']} 個檔案, 信心度: {confidence}%)\n"
                                    )
                        else:
                            move_stats["failed"] += 1
                            if progress_callback:
                                progress_callback(
                                    f"❌ {actress_name}: 合併失敗 - {merge_result['error']}\n"
                                )
                    except Exception as e:
                        move_stats["failed"] += 1
                        self.logger.error(f"合併資料夾失敗 {actress_name}: {e}")
                        if progress_callback:
                            progress_callback(
                                f"❌ {actress_name}: 合併時發生錯誤 - {str(e)}\n"
                            )
                    continue

                # 執行移動
                try:
                    shutil.move(str(source_folder), str(target_actress_folder))

                    if category == "solo":
                        move_stats["solo_artist"] += 1
                        if progress_callback:
                            progress_callback(
                                f"🎭 {actress_name} → {solo_folder_name}/ (信心度: {confidence}%)\n"
                            )
                    else:
                        move_stats["moved"] += 1
                        if progress_callback:
                            progress_callback(
                                f"✅ {actress_name} → {main_studio}/ (信心度: {confidence}%)\n"
                            )

                except FileNotFoundError as e:
                    move_stats["skipped"] += 1
                    move_stats["failed"] += 1
                    self.logger.warning(f"來源檔案不存在，無法移動 {actress_name}: {e}")
                    if progress_callback:
                        progress_callback(f"⏩ 跳過 {actress_name}: 來源檔案不存在\n")

                except PermissionError as e:
                    move_stats["failed"] += 1
                    self.logger.error(f"權限不足，無法移動 {actress_name}: {e}")
                    if progress_callback:
                        progress_callback(f"❌ {actress_name}: 權限不足 - {str(e)}\n")

                except OSError as e:
                    move_stats["failed"] += 1
                    self.logger.error(f"系統錯誤，無法移動 {actress_name}: {e}")
                    if progress_callback:
                        progress_callback(f"❌ {actress_name}: 系統錯誤 - {str(e)}\n")

            except Exception as e:
                move_stats["failed"] += 1
                self.logger.error(
                    f"移動女優 {actress_name} 時發生未預期的錯誤: {e}", exc_info=True
                )
                if progress_callback:
                    progress_callback(f"❌ {actress_name}: 未預期的錯誤 - {str(e)}\n")

        return move_stats

    def _merge_actress_folders(
        self, source_folder: Path, target_folder: Path, progress_callback=None
    ) -> dict:
        """
        合併女優資料夾：將來源資料夾的內容移動到目標資料夾
        返回合併結果統計
        """
        merge_result = {
            "success": False,
            "files_moved": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "error": None,
        }

        try:
            self.logger.info(f"開始合併資料夾: {source_folder} → {target_folder}")
            if progress_callback:
                progress_callback("  🔄 開始合併資料夾內容...\n")

            # 遍歷來源資料夾中的所有檔案和子資料夾
            items = list(source_folder.iterdir())
            total_items = len(items)
            processed_items = 0

            for item in items:
                try:
                    processed_items += 1
                    if progress_callback and processed_items % 10 == 0:
                        progress_callback(
                            f"  🔄 合併進度: {processed_items}/{total_items}\n"
                        )

                    target_item = target_folder / item.name

                    if item.is_file():
                        # 處理檔案
                        if target_item.exists():
                            # 檔案名稱衝突處理
                            base_name = item.stem
                            extension = item.suffix
                            counter = 1
                            max_attempts = 1000  # 防止無限迴圈

                            # 找一個不衝突的檔案名稱
                            while target_item.exists() and counter < max_attempts:
                                new_name = f"{base_name}_{counter}{extension}"
                                target_item = target_folder / new_name
                                counter += 1

                            if counter >= max_attempts:
                                self.logger.error(f"無法找到唯一檔案名稱: {item.name}")
                                merge_result["files_failed"] += 1
                                continue

                            if counter > 1:
                                self.logger.info(
                                    f"檔案重名，重新命名: {item.name} → {target_item.name}"
                                )

                        # 移動檔案
                        shutil.move(str(item), str(target_item))
                        merge_result["files_moved"] += 1

                    elif item.is_dir():
                        # 處理子資料夾
                        if target_item.exists():
                            # 遞迴合併子資料夾
                            sub_merge_result = self._merge_actress_folders(
                                item, target_item, progress_callback
                            )
                            merge_result["files_moved"] += sub_merge_result[
                                "files_moved"
                            ]
                            merge_result["files_skipped"] += sub_merge_result[
                                "files_skipped"
                            ]
                            merge_result["files_failed"] += sub_merge_result[
                                "files_failed"
                            ]
                        else:
                            # 直接移動整個子資料夾
                            shutil.move(str(item), str(target_item))
                            # 計算移動的檔案數
                            moved_count = sum(
                                1 for _ in target_item.rglob("*") if _.is_file()
                            )
                            merge_result["files_moved"] += moved_count

                except Exception as e:
                    merge_result["files_failed"] += 1
                    self.logger.error(f"移動項目失敗 {item}: {e}")
                    continue

            # 檢查來源資料夾是否已空
            remaining_items = list(source_folder.iterdir())
            if not remaining_items:
                # 來源資料夾已空，可以刪除
                try:
                    source_folder.rmdir()
                    self.logger.info(f"已刪除空的來源資料夾: {source_folder}")
                except Exception as e:
                    self.logger.warning(f"無法刪除來源資料夾 {source_folder}: {e}")
            else:
                self.logger.warning(
                    f"來源資料夾非空，保留: {source_folder} (剩餘 {len(remaining_items)} 個項目)"
                )

            merge_result["success"] = True
            self.logger.info(f"合併完成: 移動 {merge_result['files_moved']} 個檔案")

        except Exception as e:
            merge_result["success"] = False
            merge_result["error"] = str(e)
            self.logger.error(f"合併資料夾時發生錯誤: {e}", exc_info=True)

        return merge_result

    def get_classification_summary(self, total_actresses: int, move_stats: dict) -> str:
        """生成片商分類結果摘要"""
        solo_folder_name = self.preference_manager.get_solo_folder_name()

        return (
            f"📊 片商分類完成！\n\n"
            f"  📁 掃描女優總數: {total_actresses}\n"
            f"  ✅ 移動到片商資料夾: {move_stats.get('moved', 0)}\n"
            f"  🎭 移動到{solo_folder_name}: {move_stats.get('solo_artist', 0)}\n"
            f"  ⏩ 跳過處理: {move_stats.get('skipped', 0)}\n"
            f"  ❌ 移動失敗: {move_stats.get('failed', 0)}\n"
            f"\n💡 已存在的資料夾已自動合併內容"
        )
