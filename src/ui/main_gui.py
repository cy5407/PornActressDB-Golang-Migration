"""
主要 GUI 介面
統合所有功能的圖形化使用者介面
"""

import logging
import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from models.config import ConfigManager
from services.classifier_core import UnifiedClassifierCore
from services.interactive_classifier import InteractiveClassifier
from ui.operation_history_dialog import show_operation_history
from ui.preferences_dialog import PreferenceDialog

logger = logging.getLogger(__name__)


class ProgressThrottler:
    """
    進度更新節流器
    避免過於頻繁的 GUI 更新導致卡頓
    """

    def __init__(self, min_interval_ms: int = 100):
        self.min_interval = min_interval_ms / 1000
        self.last_update = 0.0
        self.pending_message = None
        self.lock = threading.Lock()

    def should_update(self, message: str, force: bool = False) -> bool:
        current_time = time.time()

        with self.lock:
            # 重要訊息強制更新
            if force or self._is_important(message):
                self.last_update = current_time
                self.pending_message = None
                return True

            if (current_time - self.last_update) >= self.min_interval:
                self.last_update = current_time
                self.pending_message = None
                return True
            else:
                self.pending_message = message
                return False

    def _is_important(self, message: str) -> bool:
        important_keywords = [
            "完成",
            "錯誤",
            "開始",
            "====",
            "階段",
            "失敗",
            "摘要",
            "💥",
            "🎉",
            "⚠️",
            "💾",
            "已寫入",
        ]
        return any(keyword in message for keyword in important_keywords)

    def flush(self):
        with self.lock:
            msg = self.pending_message
            self.pending_message = None
            return msg


class GUIMessageType(Enum):
    """GUI 訊息類型"""

    TEXT = "text"  # 一般文字
    ERROR = "error"  # 錯誤訊息
    STATUS = "status"  # 狀態列更新
    CLEAR = "clear"  # 清除文字
    CALLBACK = "callback"  # 執行回呼函式


@dataclass
class GUIMessage:
    """執行緒安全的 GUI 訊息"""

    msg_type: GUIMessageType
    content: Any = None
    callback: Callable | None = None


class SafeGUIUpdater:
    """
    執行緒安全的 GUI 更新器

    使用 Queue 實現執行緒間通訊，避免競爭條件
    """

    def __init__(self, root: tk.Tk, result_text: tk.Text, status_var: tk.StringVar):
        self.root = root
        self.result_text = result_text
        self.status_var = status_var
        self.message_queue: queue.Queue[GUIMessage] = queue.Queue()
        self.is_running = True
        self._start_queue_processor()

    def _start_queue_processor(self):
        """啟動訊息佇列處理器"""
        self._process_queue()

    def _process_queue(self):
        """處理訊息佇列（高頻率輪詢，確保進度即時顯示）"""
        if not self.is_running:
            return

        try:
            # 批次處理訊息以提高效率
            messages_processed = 0
            max_messages_per_cycle = 100

            while messages_processed < max_messages_per_cycle:
                try:
                    msg = self.message_queue.get_nowait()
                    self._process_message(msg)
                    messages_processed += 1
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"❌ 處理 GUI 訊息佇列時發生錯誤: {e}")
        finally:
            # 排程下一次處理
            if self.is_running:
                from contextlib import suppress
                with suppress(tk.TclError):
                    self.root.after(20, self._process_queue)

    def _process_message(self, msg: GUIMessage):
        """處理單一訊息"""
        try:
            if msg.msg_type == GUIMessageType.TEXT:
                if self._widget_exists(self.result_text):
                    self.result_text.insert(tk.END, msg.content)
                    self.result_text.see(tk.END)

            elif msg.msg_type == GUIMessageType.ERROR:
                if self._widget_exists(self.result_text):
                    self.result_text.insert(tk.END, f"❌ {msg.content}\n")
                    self.result_text.see(tk.END)

            elif msg.msg_type == GUIMessageType.STATUS:
                self.status_var.set(msg.content)

            elif msg.msg_type == GUIMessageType.CLEAR:
                if self._widget_exists(self.result_text):
                    self.result_text.delete(1.0, tk.END)

            elif msg.msg_type == GUIMessageType.CALLBACK and msg.callback:
                msg.callback()

        except tk.TclError as e:
            logger.warning(f"⚠️ GUI 元件已銷毀，忽略訊息: {e}")
        except Exception as e:
            logger.error(f"❌ 處理 GUI 訊息時發生錯誤: {e}")

    def _widget_exists(self, widget) -> bool:
        """安全檢查元件是否存在"""
        try:
            return widget.winfo_exists()
        except tk.TclError:
            return False

    def send_text(self, text: str):
        """發送文字訊息到 GUI"""
        self.message_queue.put(GUIMessage(GUIMessageType.TEXT, text))

    def send_error(self, error: str):
        """發送錯誤訊息到 GUI"""
        self.message_queue.put(GUIMessage(GUIMessageType.ERROR, error))

    def send_status(self, status: str):
        """發送狀態更新到 GUI"""
        self.message_queue.put(GUIMessage(GUIMessageType.STATUS, status))

    def send_clear(self):
        """發送清除訊息"""
        self.message_queue.put(GUIMessage(GUIMessageType.CLEAR))

    def send_callback(self, callback: Callable):
        """發送回呼函式到 GUI 執行緒執行"""
        self.message_queue.put(GUIMessage(GUIMessageType.CALLBACK, callback=callback))

    def stop(self):
        """停止處理器"""
        self.is_running = False


class UnifiedActressClassifierGUI:
    """整合版圖形介面 - 包含片商分類功能"""

    def __init__(self, root):
        self.root = root
        self.root.title("女優分類系統 - v5.2 (智慧搜尋版)")
        self.root.geometry("900x750")
        self.is_running = True
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.config_manager = ConfigManager()
        self.core = UnifiedClassifierCore(self.config_manager)

        # 建立並設定偏好管理器
        from models.config import PreferenceManager

        preference_manager = PreferenceManager()
        self.core.set_preference_manager(preference_manager)

        # 設定互動式分類器
        self.interactive_classifier = InteractiveClassifier(
            preference_manager, self.root
        )
        self.core.set_interactive_classifier(self.interactive_classifier)

        self.selected_path = tk.StringVar(
            value=self.config_manager.get("paths", "default_input_dir", ".")
        )
        self.stop_event = threading.Event()

        # 新增進度節流器
        self.progress_throttler = ProgressThrottler(min_interval_ms=100)

        # 搜尋結果暫存（用於結果預覽）
        self.last_search_results = {}

        # 安全 GUI 更新器（在 setup_ui 後初始化）
        self.gui_updater: SafeGUIUpdater | None = None

        self.setup_ui()

        # 初始化安全 GUI 更新器
        self.gui_updater = SafeGUIUpdater(self.root, self.result_text, self.status_var)
        logger.info("✅ SafeGUIUpdater 已初始化")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        # 標題區域
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            title_frame, text="🎬 女優分類系統 v5.2", font=("Arial", 16, "bold")
        ).pack()
        ttk.Label(
            title_frame,
            text="智慧搜尋版 - AV-WIKI 批次搜尋 + JAVDB / shiroutowiki 獨立搜尋",
            font=("Arial", 10),
        ).pack()

        # 路徑選擇區域
        path_frame = ttk.LabelFrame(main_frame, text="📁 目標資料夾", padding="10")
        path_frame.pack(fill="x", pady=5)
        path_entry = ttk.Entry(
            path_frame, textvariable=self.selected_path, font=("Arial", 10)
        )
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.browse_btn = ttk.Button(
            path_frame, text="瀏覽...", command=self.browse_folder
        )
        self.browse_btn.pack(side="left")

        # 搜尋選項區域（新增）
        options_frame = ttk.LabelFrame(main_frame, text="🔧 搜尋選項", padding="5")
        options_frame.pack(fill="x", pady=5)

        self.show_results_var = tk.BooleanVar(value=True)
        results_check = ttk.Checkbutton(
            options_frame,
            text="📊 搜尋完成後顯示結果預覽",
            variable=self.show_results_var,
        )
        results_check.pack(side="left", padx=5)

        # 功能按鈕區域
        button_frame = ttk.LabelFrame(main_frame, text="🔧 功能選擇", padding="10")
        button_frame.pack(fill="x", pady=5)
        # 第一排按鈕 - 分離的搜尋按鈕
        row1_frame = ttk.Frame(button_frame)
        row1_frame.pack(fill="x", pady=(0, 5))
        row1_frame.columnconfigure((0, 1, 2, 3), weight=1)

        self.search_japanese_btn = ttk.Button(
            row1_frame, text="🇯🇵 日文網站搜尋", command=self.start_japanese_search
        )
        self.search_japanese_btn.grid(
            row=0, column=0, padx=(0, 2), sticky="ew", ipady=5
        )

        self.search_javdb_btn = ttk.Button(
            row1_frame, text="📊 JAVDB 搜尋", command=self.start_javdb_search
        )
        self.search_javdb_btn.grid(row=0, column=1, padx=2, sticky="ew", ipady=5)

        self.search_shiroutowiki_btn = ttk.Button(
            row1_frame,
            text="🧑 shiroutowiki 搜尋",
            command=self.start_shiroutowiki_search,
        )
        self.search_shiroutowiki_btn.grid(
            row=0, column=2, padx=2, sticky="ew", ipady=5
        )

        self.settings_btn = ttk.Button(
            row1_frame, text="⚙️ 偏好設定", command=self.show_preferences
        )
        self.settings_btn.grid(row=0, column=3, padx=(2, 0), sticky="ew", ipady=5)

        # 第二排按鈕 - 包含片商分類按鈕
        row2_frame = ttk.Frame(button_frame)
        row2_frame.pack(fill="x", pady=(0, 5))
        row2_frame.columnconfigure((0, 1, 2, 3), weight=1)

        self.interactive_move_btn = ttk.Button(
            row2_frame, text="🤝 互動式移動", command=self.start_interactive_move
        )
        self.interactive_move_btn.grid(
            row=0, column=0, padx=(0, 2), sticky="ew", ipady=5
        )

        self.standard_move_btn = ttk.Button(
            row2_frame, text="📁 標準移動", command=self.start_standard_move
        )
        self.standard_move_btn.grid(row=0, column=1, padx=2, sticky="ew", ipady=5)

        # 新增智慧搜尋並分類按鈕
        self.smart_search_move_btn = ttk.Button(
            row2_frame,
            text="🔍📁 智慧搜尋並分類",
            command=self.start_smart_search_and_move,
        )
        self.smart_search_move_btn.grid(row=0, column=2, padx=2, sticky="ew", ipady=5)

        self.stop_btn = ttk.Button(
            row2_frame, text="🛑 中止任務", command=self.stop_task, state="disabled"
        )
        self.stop_btn.grid(row=0, column=3, padx=(2, 0), sticky="ew", ipady=5)

        # 第三排按鈕 - 片商分類、修正片商資料和操作歷史
        row3_frame = ttk.Frame(button_frame)
        row3_frame.pack(fill="x")
        row3_frame.columnconfigure((0, 1, 2), weight=1)

        self.studio_classify_btn = ttk.Button(
            row3_frame, text="🏢 片商分類", command=self.start_studio_classification
        )
        self.studio_classify_btn.grid(row=0, column=0, padx=(0, 2), sticky="ew", ipady=5)

        self.fix_studios_btn = ttk.Button(
            row3_frame, text="🔧 修正片商資料", command=self.start_fix_studios
        )
        self.fix_studios_btn.grid(row=0, column=1, padx=(2, 2), sticky="ew", ipady=5)

        # 新增操作歷史按鈕
        self.history_btn = ttk.Button(
            row3_frame, text="📜 操作歷史", command=self.show_operation_history
        )
        self.history_btn.grid(row=0, column=2, padx=(2, 0), sticky="ew", ipady=5)

        # 結果顯示區域
        result_frame = ttk.LabelFrame(main_frame, text="📋 執行結果", padding="10")
        result_frame.pack(fill="both", expand=True, pady=5)

        self.result_text = tk.Text(
            result_frame,
            wrap="word",
            font=("Consolas", 9),
            height=25,
            relief="flat",
            padx=5,
            pady=5,
        )
        scrollbar = ttk.Scrollbar(
            result_frame, orient="vertical", command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 狀態列
        self.status_var = tk.StringVar(value="就緒")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=2,
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.show_welcome_message()

    def show_welcome_message(self):
        """顯示歡迎訊息"""
        welcome_text = """🎬 女優分類系統 v5.1 - 互動式分類版
========================================

✨ 功能總覽：
• 🔍 掃描與搜尋：建立影片與女優資料庫
• 🤝 互動式移動：多女優共演時可選擇個人偏好
• 📁 標準移動：使用第一位女優進行快速分類
• 🏢 片商分類：將女優資料夾按片商歸類整理 ⭐ 新功能

🎯 建議使用流程：
1. 選擇包含影片檔案的資料夾
2. 點擊「掃描與搜尋」建立影片資料庫
3. 使用「互動式移動」進行個人化分類
4. 使用「片商分類」整理女優資料夾到片商結構

🏢 片商分類功能特色：
• 自動分析女優的片商分佈統計
• 信心度≥60%歸類到主片商資料夾
• 信心度<60%歸類到「單體企劃女優」資料夾
• 可在偏好設定中自訂分類規則

準備好開始了嗎？請選擇資料夾並開始您的分類之旅！
"""
        self.result_text.insert(tk.END, welcome_text)

    def show_preferences(self):
        """顯示偏好設定對話框"""
        PreferenceDialog(self.root, self.core.preference_manager)

    def show_operation_history(self):
        """顯示操作歷史對話框"""
        show_operation_history(self.root, self.core.file_mover)

    def _get_result_message(self, result, default: str = "未知錯誤") -> str:
        """統一取得背景工作的提示訊息。"""
        if isinstance(result, dict):
            return result.get("message") or result.get("error") or default
        if result:
            return str(result)
        return default

    def _show_result_error(self, result):
        """統一顯示背景工作的錯誤提示。"""
        error_msg = self._get_result_message(result)
        self.update_progress(f"\n{'=' * 60}\n❌ 錯誤: {error_msg}\n")
        self.status_var.set(f"錯誤: {error_msg}")

    def _append_search_summary(self, title: str, result: dict):
        """統一顯示搜尋工作的摘要。"""
        summary_lines = [f"\n{'=' * 60}\n{title}\n"]

        if "new_codes" in result:
            summary_lines.append(f"\n  🎯 搜尋目標: {result.get('new_codes', 0)}\n")
        if "success" in result:
            summary_lines.append(f"  ✅ 找到資料: {result.get('success', 0)}\n")
        if "failed" in result:
            summary_lines.append(f"  ❌ 未找到: {result.get('failed', 0)}\n")
        if "first_round_success" in result:
            summary_lines.append(
                f"\n  ✅ 第一輪成功: {result.get('first_round_success', 0)}\n"
            )
            summary_lines.append(
                f"  ❌ 第一輪失敗: {result.get('first_round_failed', 0)}\n"
            )
            summary_lines.append(
                f"  🔄 二次搜尋成功: {result.get('second_round_success', 0)}\n"
            )
        if result.get("source_stats"):
            summary_lines.append("\n  📈 來源統計:\n")
            for source, count in sorted(
                result["source_stats"].items(), key=lambda item: -item[1]
            ):
                summary_lines.append(f"    • {source}: {count}\n")
        if (
            not any(
                key in result
                for key in ("new_codes", "success", "failed", "first_round_success")
            )
            and result.get("message")
        ):
            summary_lines.append(f"\n  ℹ️ {result['message']}\n")

        self.update_progress("".join(summary_lines))

    def on_closing(self):
        """程式關閉時的處理"""
        self.is_running = False
        self.stop_event.set()

        # 0. 停止所有背景操作以避免並行寫入
        if self.gui_updater:
            self.gui_updater.stop()

        # 給背景操作短暫時間完成
        import time
        time.sleep(0.5)

        # 1. 強制合併增量資料庫並儲存到 data.json（加鎖保護）
        try:
            if hasattr(self.core, "db_manager"):
                # 強制執行完整合併（不只是檢查閾值）
                if hasattr(self.core.db_manager, "compact"):
                    print("🔄 正在強制合併資料庫...（關閉前儲存所有資料）")
                    self.core.db_manager.compact()
                    print("✅ 資料庫已完整儲存到 data.json")
                elif hasattr(self.core.db_manager, "compact_if_needed"):
                    print("正在檢查是否需要合併資料庫...")
                    self.core.db_manager.compact_if_needed()
        except Exception as e:
            print(f"❌ 資料庫合併失敗: {e}")
            # 繼續執行，不中斷關閉流程

        # 2. 清理過期快取（使用統一快取管理器）
        try:
            from services.unified_cache import get_cache_manager

            cache_mgr = get_cache_manager(self.config_manager)

            # 讀取設定
            ttl_days = self.config_manager.getint("cache", "ttl_days", fallback=7)
            max_size_mb = self.config_manager.getint(
                "cache", "max_size_mb", fallback=500
            )
            auto_cleanup = self.config_manager.getboolean(
                "cache", "auto_cleanup_on_exit", fallback=True
            )

            if auto_cleanup:
                result = cache_mgr.cleanup_all(
                    ttl_days=ttl_days, max_size_mb=max_size_mb
                )
                if result.get("total_deleted", 0) > 0:
                    print(
                        f"已清理 {result['total_deleted']} 個快取項目，釋放 {result['total_freed_mb']:.1f} MB"
                    )
        except Exception as e:
            print(f"快取清理失敗: {e}")

        # 3. 關閉根視窗
        self.root.destroy()

    def browse_folder(self):
        initial_dir = self.selected_path.get()
        if not Path(initial_dir).is_dir():
            initial_dir = str(Path.home())
        folder_path = filedialog.askdirectory(
            title="選擇目標資料夾", initialdir=initial_dir
        )
        if folder_path:
            self.selected_path.set(folder_path)
            self.config_manager.config.set("paths", "default_input_dir", folder_path)
            self.config_manager.save_config()

    def clear_results(self):
        """清除結果文字（執行緒安全）"""
        if self.gui_updater:
            self.gui_updater.send_clear()
        elif self.is_running and self.result_text.winfo_exists():
            self.result_text.delete(1.0, tk.END)

    def update_progress(self, message: str):
        """更新進度顯示（執行緒安全，有節流機制）"""
        if not self.is_running:
            return

        # 使用節流器判斷是否更新
        if self.progress_throttler.should_update(message):
            if self.gui_updater:
                self.gui_updater.send_text(message)
            else:
                # 備用方案：直接使用 after
                self.safe_gui_update(lambda: self._insert_text(message))

    def safe_gui_update(self, callback: Callable):
        """
        安全的 GUI 更新包裝器

        確保 GUI 操作在主執行緒執行，並處理元件已銷毀的情況

        Args:
            callback: 要執行的 GUI 更新函式
        """

        def wrapped_callback():
            try:
                if not self.is_running:
                    return
                if not self.root.winfo_exists():
                    return
                callback()
            except tk.TclError as e:
                logger.warning(f"⚠️ GUI 元件已銷毀: {e}")
            except Exception as e:
                logger.error(f"❌ GUI 更新失敗: {e}", exc_info=True)

        from contextlib import suppress
        with suppress(tk.TclError):
            self.root.after(0, wrapped_callback)

    def _insert_text(self, message: str):
        """插入文字到結果區域（內部使用）"""
        try:
            if self.is_running and self.result_text.winfo_exists():
                self.result_text.insert(tk.END, message)
                self.result_text.see(tk.END)

                # 檢查是否有待處理的訊息
                pending = self.progress_throttler.flush()
                if pending:
                    self.result_text.insert(tk.END, pending)
                    self.result_text.see(tk.END)
        except tk.TclError as e:
            logger.warning(f"⚠️ 文字插入失敗，元件可能已銷毀: {e}")

    def _toggle_buttons(self, is_task_running: bool):
        if not self.is_running:
            return
        search_state = "disabled" if is_task_running else "normal"
        stop_state = "normal" if is_task_running else "disabled"

        # 更新按鈕列表，包含分離搜尋按鈕和片商分類按鈕
        buttons = [
            self.browse_btn,
            self.search_japanese_btn,
            self.search_javdb_btn,
            self.search_shiroutowiki_btn,
            self.interactive_move_btn,
            self.standard_move_btn,
            self.smart_search_move_btn,
            self.studio_classify_btn,
            self.fix_studios_btn,
            self.history_btn,
            self.settings_btn,
        ]

        for btn in buttons:
            if btn.winfo_exists():
                btn.config(state=search_state)
        if self.stop_btn.winfo_exists():
            self.stop_btn.config(state=stop_state)

    def _run_task(self, task_func, *args):
        if self.is_running:
            self.root.after(0, self._toggle_buttons, True)
        try:
            task_func(*args)
        finally:
            if self.is_running:
                self.root.after(0, self._toggle_buttons, False)

    def stop_task(self):
        """中止當前任務"""
        if not self.stop_event.is_set():
            self.stop_event.set()

            # 更新 UI 回饋
            self.status_var.set("🛑 正在中止任務...")
            if self.stop_btn.winfo_exists():
                self.stop_btn.config(state="disabled")

            # 顯示中止訊息
            self.update_progress("\n⚠️ 使用者要求中止，正在等待當前操作完成...\n")

    def start_search(self):
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n{'=' * 60}\n")
        self.stop_event.clear()
        threading.Thread(
            target=self._run_task, args=(self._search_worker, path), daemon=True
        ).start()

    def _search_worker(self, path):
        self.status_var.set("執行中：掃描與搜尋...")
        result = self.core.process_and_search(
            path, self.stop_event, self.update_progress
        )
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress("\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result["status"] == "success":
                self._append_search_summary("🎉 搜尋任務完成！", result)
                self.status_var.set("就緒")
            else:
                self._show_result_error(result)

    def start_japanese_search(self):
        """開始日文網站搜尋"""
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n")
        self.update_progress("搜尋模式: 🇯🇵 AV-WIKI (av-wiki.net)\n")
        self.update_progress(f"{'=' * 60}\n")
        self.stop_event.clear()
        threading.Thread(
            target=self._run_task,
            args=(self._japanese_search_worker, path),
            daemon=True,
        ).start()

    def start_javdb_search(self):
        """開始JAVDB搜尋"""
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n")
        self.update_progress("搜尋模式: 📊 JAVDB 網站\n")
        self.update_progress(f"{'=' * 60}\n")
        self.stop_event.clear()
        threading.Thread(
            target=self._run_task, args=(self._javdb_search_worker, path), daemon=True
        ).start()

    def start_shiroutowiki_search(self):
        """開始 shiroutowiki 搜尋"""
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n")
        self.update_progress("搜尋模式: 🧑 shiroutowiki.work\n")
        self.update_progress(f"{'=' * 60}\n")
        self.stop_event.clear()
        threading.Thread(
            target=self._run_task,
            args=(self._shiroutowiki_search_worker, path),
            daemon=True,
        ).start()

    def _japanese_search_worker(self, path):
        """日文網站搜尋工作者（AV-WIKI 批次搜尋 + 結果預覽）"""
        self.status_var.set("執行中：日文網站搜尋...")
        result = self.core.process_and_search_cascade(
            path, self.stop_event, self.update_progress
        )

        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress("\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result.get("status") == "success":
                self._append_search_summary("🎉 日文網站搜尋任務完成！", result)
                self.status_var.set("就緒")

                # 儲存搜尋結果供預覽使用
                self.last_search_results = result.get("search_results", {})

                # 顯示結果預覽（如果啟用）
                if self.show_results_var.get() and self.last_search_results:
                    self.root.after(100, self._show_search_results_dialog)
            else:
                self._show_result_error(result)

    def _javdb_search_worker(self, path):
        """JAVDB搜尋工作者"""
        self.status_var.set("執行中：JAVDB搜尋...")
        result = self.core.process_and_search_javdb(
            path, self.stop_event, self.update_progress
        )
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress("\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result["status"] == "success":
                self._append_search_summary("🎉 JAVDB 搜尋任務完成！", result)
                self.status_var.set("就緒")
            else:
                self._show_result_error(result)

    def _shiroutowiki_search_worker(self, path):
        """shiroutowiki 搜尋工作者"""
        self.status_var.set("執行中：shiroutowiki 搜尋...")
        result = self.core.process_and_search_shiroutowiki(
            path, self.stop_event, self.update_progress
        )
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress("\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result.get("status") == "success":
                self._append_search_summary("🎉 shiroutowiki 搜尋任務完成！", result)
                self.status_var.set("就緒")
                self.last_search_results = result.get("search_results", {})
                if self.show_results_var.get() and self.last_search_results:
                    self.root.after(100, self._show_search_results_dialog)
            else:
                self._show_result_error(result)

    def start_interactive_move(self):
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return

        confirm_text = f"""確定要進行互動式分類嗎？

📁 目標資料夾: {path}

🤝 互動式分類特色：
• 遇到多女優共演時會彈出選擇對話框
• 可選擇您偏好的女優進行分類
• 自動記住您的選擇偏好
• 檔名會標記所有參演女優資訊

⚠️ 注意：只會移動此資料夾根目錄下的檔案"""

        if not messagebox.askyesno("確認互動式移動", confirm_text):
            return
        self.clear_results()
        self.update_progress(f"🤝 互動式分類模式\n目標資料夾: {path}\n{'=' * 60}\n")
        threading.Thread(
            target=self._run_task,
            args=(self._interactive_move_worker, path),
            daemon=True,
        ).start()

    def _interactive_move_worker(self, path):
        self.status_var.set("執行中：互動式檔案移動...")
        result = self.core.interactive_move_files(path, self.update_progress)
        if self.is_running:
            if result.get("status") == "success" and "stats" in result:
                stats = result["stats"]
                summary = (
                    f"\n{'=' * 60}\n🤝 互動式分類完成！\n\n"
                    f"  ✅ 成功移動: {stats['success']}\n"
                    f"  ⚠️ 已存在: {stats['exists']}\n"
                    f"  ❓ 無資料: {stats['no_data']}\n"
                    f"  ⏭️ 跳過: {stats['skipped']}\n"
                    f"  ❌ 失敗: {stats['failed']}\n"
                )
                self.update_progress(summary)
                self.status_var.set("就緒")
            elif result.get("status") == "no_data":
                self.update_progress(
                    f"\n{'=' * 60}\n⚠️ {self._get_result_message(result)}\n"
                )
                self.status_var.set("就緒")
            else:
                self._show_result_error(result)

    def start_standard_move(self):
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        if not messagebox.askyesno(
            "確認智慧分類",
            f"確定要將 '{path}' 資料夾中的影片進行智慧分類嗎？\n\n🎯 智慧分類模式：\n• 單人影片：自動分類到對應女優資料夾\n• 多人共演：彈出互動選擇對話框\n\n（只會移動此資料夾根目錄下的檔案）",
        ):
            return
        self.clear_results()
        self.update_progress(f"📁 智慧分類模式\n目標資料夾: {path}\n{'=' * 60}\n")
        threading.Thread(
            target=self._run_task, args=(self._standard_move_worker, path), daemon=True
        ).start()

    def _standard_move_worker(self, path):
        self.status_var.set("執行中：智慧檔案移動...")
        result = self.core.move_files(path, self.update_progress)
        if self.is_running:
            if result.get("status") == "success" and "stats" in result:
                stats = result["stats"]
                interactive_info = (
                    f"  🤝 互動處理: {stats['interactive']}\n"
                    if stats.get("interactive", 0) > 0
                    else ""
                )
                summary = (
                    f"\n{'=' * 60}\n📁 智慧分類完成！\n\n"
                    f"  ✅ 成功: {stats['success']}\n"
                    f"  ⚠️ 已存在: {stats['exists']}\n"
                    f"  ❓ 無資料: {stats['no_data']}\n"
                    f"  ❌ 失敗: {stats['failed']}\n"
                    f"{interactive_info}"
                )
                self.update_progress(summary)
                self.status_var.set("就緒")
            else:
                self._show_result_error(result)

    def start_smart_search_and_move(self):
        """開始智慧搜尋並分類"""
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return

        # 詢問搜尋方式
        use_full_search = messagebox.askyesno(
            "選擇搜尋方式",
            "🔍 智慧搜尋並分類\n\n"
            "系統會自動搜尋無資料的番號，然後進行智慧分類。\n\n"
            "請選擇搜尋方式：\n\n"
            "• 是 → 使用完整搜尋（AV-WIKI → JAVDB）\n"
            "• 否 → 僅使用 AV-WIKI 搜尋\n\n"
            "建議：如果 AV-WIKI 找不到，選擇完整搜尋",
        )

        if not messagebox.askyesno(
            "確認智慧搜尋並分類",
            f"確定要對 '{path}' 執行智慧搜尋並分類嗎？\n\n"
            f"🔍 搜尋方式: {'完整搜尋（含 JAVDB）' if use_full_search else '日文網站搜尋'}\n\n"
            f"流程：\n"
            f"1. 掃描影片檔案\n"
            f"2. 搜尋無資料番號\n"
            f"3. 自動智慧分類\n\n"
            f"（只會處理此資料夾根目錄下的檔案）",
        ):
            return

        self.clear_results()
        self.update_progress(
            f"🔍📁 智慧搜尋並分類模式\n目標資料夾: {path}\n{'=' * 60}\n"
        )
        self.stop_event.clear()

        # 在背景執行
        threading.Thread(
            target=self._run_task,
            args=(self._smart_search_and_move_worker, path, use_full_search),
            daemon=True,
        ).start()

    def _smart_search_and_move_worker(self, path, use_full_search):
        """智慧搜尋並分類工作執行緒"""
        self.status_var.set("執行中：智慧搜尋並分類...")

        try:
            result = self.core.smart_search_and_move(
                path,
                self.stop_event,
                self.update_progress,
                use_full_search=use_full_search,
            )

            if self.is_running:
                if self.stop_event.is_set():
                    self.update_progress("\n🛑 任務已由使用者中止。\n")
                    self.status_var.set("任務已中止")
                elif result.get("status") == "success":
                    stats = result.get("stats", {})
                    interactive_info = (
                        f"  🤝 互動處理: {stats['interactive']}\n"
                        if stats.get("interactive", 0) > 0
                        else ""
                    )
                    summary = (
                        f"\n{'=' * 60}\n🎉 智慧搜尋並分類完成！\n\n"
                        f"  ✅ 成功: {stats.get('success', 0)}\n"
                        f"  ⚠️ 已存在: {stats.get('exists', 0)}\n"
                        f"  ❓ 無資料: {stats.get('no_data', 0)}\n"
                        f"  ❌ 失敗: {stats.get('failed', 0)}\n"
                        f"{interactive_info}"
                    )
                    self.update_progress(summary)
                    self.status_var.set("就緒")
                else:
                    self._show_result_error(result)
        except Exception as e:
            logger.error(f"智慧搜尋並分類失敗: {e}", exc_info=True)
            if self.is_running:
                self._show_result_error({"message": str(e)})

    def start_studio_classification(self):
        """開始片商分類功能"""
        path = self.selected_path.get()
        if not Path(path).is_dir():
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return

        # 確認對話框
        solo_folder_name = self.core.preference_manager.get_solo_folder_name()
        confidence_threshold = self.core.preference_manager.get_confidence_threshold()

        confirm_text = f"""確定要進行片商分類嗎？

📁 目標資料夾: {path}

🏢 片商分類規則：
• 信心度 ≥ {confidence_threshold}%：歸類到主片商資料夾
• 信心度 < {confidence_threshold}%：歸類到「{solo_folder_name}」資料夾

⚠️ 注意事項：
• 會遞迴掃描所有子資料夾中的女優資料夾
• 會重新統計女優的片商分佈（確保資料準確）
• 移動操作無法復原，建議先備份重要資料

是否繼續執行？"""

        if not messagebox.askyesno("確認片商分類", confirm_text):
            return

        self.clear_results()
        self.update_progress(f"🏢 片商分類模式\n目標資料夾: {path}\n{'=' * 60}\n")

        # 在背景執行片商分類
        threading.Thread(
            target=self._run_task,
            args=(self._studio_classification_worker, path),
            daemon=True,
        ).start()

    def _studio_classification_worker(self, path):
        """片商分類工作執行緒"""
        self.status_var.set("執行中：片商分類...")

        try:
            result = self.core.classify_actresses_by_studio(path, self.update_progress)

            if self.is_running:
                if result.get("status") == "success":
                    # 顯示結果摘要
                    move_stats = result.get("move_stats", {})
                    total_actresses = result.get("total_actresses", 0)

                    summary = self.core.studio_classifier.get_classification_summary(
                        total_actresses, move_stats
                    )
                    self.update_progress(f"\n{'=' * 60}\n{summary}")

                    self.status_var.set("就緒")
                else:
                    error_msg = result.get("message", "未知錯誤")
                    self.update_progress(f"\n💥 錯誤: {error_msg}\n")
                    self.status_var.set(f"錯誤: {error_msg}")

        except Exception as e:
            if self.is_running:
                self.update_progress(f"\n💥 片商分類發生未預期錯誤: {str(e)}\n")
                self.status_var.set(f"錯誤: {str(e)}")

    def start_fix_studios(self):
        """批次修正資料庫內 UNKNOWN/空白片商"""
        from services.go_bridge import get_bridge
        bridge = get_bridge()
        if not bridge.is_available:
            messagebox.showwarning("警告", "Go CLI 不可用，無法執行片商批次修正。\n請確認 classifier.exe 存在。")
            return

        if not messagebox.askyesno(
            "確認修正片商資料",
            "此操作將掃描整個資料庫，\n對 UNKNOWN 或空白片商的影片自動識別並更新片商名稱。\n\n是否繼續？",
        ):
            return

        self.clear_results()
        self.update_progress("🔧 修正片商資料\n" + "=" * 60 + "\n")

        threading.Thread(
            target=self._run_task,
            args=(self._fix_studios_worker,),
            daemon=True,
        ).start()

    def _fix_studios_worker(self):
        """修正片商工作執行緒"""
        from services.go_bridge import get_bridge
        self.status_var.set("執行中：修正片商資料...")
        try:
            bridge = get_bridge()
            if not bridge.is_available:
                self.update_progress("❌ Go CLI 不可用\n")
                self.status_var.set("錯誤")
                return

            # 從 db_manager 取得資料庫路徑
            db_manager = self.core.db_manager
            data_dir = str(getattr(db_manager, "data_dir", "data/json_db"))

            self.update_progress(f"📂 資料庫路徑: {data_dir}\n🚀 開始批次識別...\n")

            result = bridge.db_fix_studios(data_dir=data_dir)

            if not self.is_running:
                return

            if result.get("success"):
                updated = result.get("updated", 0)
                total = result.get("total", 0)
                skipped = result.get("skipped", 0)
                already_correct = result.get("already_correct", 0)

                self.update_progress(
                    f"\n{'=' * 60}\n"
                    f"📊 修正結果摘要\n"
                    f"  總計影片: {total}\n"
                    f"  已更新:   {updated}\n"
                    f"  已正確:   {already_correct}\n"
                    f"  無法識別: {skipped}\n"
                )

                changes = result.get("changes") or []
                if changes:
                    self.update_progress(f"\n📝 更新明細 (共 {len(changes)} 筆):\n")
                    for c in changes[:50]:
                        self.update_progress(
                            f"  {c['code']}: {c['from'] or '(空白)'} → {c['to']}\n"
                        )
                    if len(changes) > 50:
                        self.update_progress(f"  ... 及其他 {len(changes) - 50} 筆\n")
                else:
                    self.update_progress("  (無變更)\n")

                self.status_var.set(f"片商修正完成，更新 {updated} 筆")
            else:
                err = result.get("error", "未知錯誤")
                self.update_progress(f"\n❌ 修正失敗: {err}\n")
                self.status_var.set(f"錯誤: {err}")

        except Exception as e:
            if self.is_running:
                self.update_progress(f"\n💥 修正片商發生未預期錯誤: {str(e)}\n")
                self.status_var.set(f"錯誤: {str(e)}")

    # ============================================================
    # 搜尋結果預覽功能（新增）
    # ============================================================

    def _show_search_results_dialog(self):
        """顯示搜尋結果預覽對話框"""
        if not self.last_search_results:
            messagebox.showinfo("無結果", "沒有搜尋結果可顯示", parent=self.root)
            return

        try:
            from ui.search_result_dialog import SearchResultDialog, SearchResultItem

            # 轉換結果格式
            search_results = {}
            for code, detail in self.last_search_results.items():
                if isinstance(detail, dict):
                    actresses = detail.get("actresses", [])
                    search_results[code] = SearchResultItem(
                        code=code,
                        actresses=actresses,
                        source=detail.get("final_source", detail.get("source", "")),
                        status="success" if actresses else "not_found",
                        studio=detail.get("studio", ""),
                        tried_sources=detail.get("tried_sources", []),
                    )

            if search_results:
                SearchResultDialog(self.root, search_results, "🔍 搜尋結果預覽")
            else:
                messagebox.showinfo("無結果", "沒有搜尋結果可顯示", parent=self.root)

        except ImportError as e:
            logger.error(f"無法匯入搜尋結果對話框: {e}")
            messagebox.showerror(
                "錯誤", f"無法顯示搜尋結果預覽:\n{e}", parent=self.root
            )
        except Exception as e:
            logger.error(f"顯示搜尋結果預覽失敗: {e}")
            messagebox.showerror(
                "錯誤", f"顯示搜尋結果預覽失敗:\n{e}", parent=self.root
            )
