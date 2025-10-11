"""
主要 GUI 介面
統合所有功能的圖形化使用者介面
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path

from models.config import ConfigManager
from services.classifier_core import UnifiedClassifierCore
from services.interactive_classifier import InteractiveClassifier
from ui.preferences_dialog import PreferenceDialog


class UnifiedActressClassifierGUI:
    """整合版圖形介面 - 包含片商分類功能"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("女優分類系統 - v5.1 (包含片商分類功能)")
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
        self.interactive_classifier = InteractiveClassifier(preference_manager, self.root)
        self.core.set_interactive_classifier(self.interactive_classifier)
        
        self.selected_path = tk.StringVar(value=self.config_manager.get('paths', 'default_input_dir', '.'))
        self.stop_event = threading.Event()
        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 標題區域
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(title_frame, text="🎬 女優分類系統 v5.1", font=("Arial", 16, "bold")).pack()
        ttk.Label(title_frame, text="互動式分類版 - 支援多女優共演的個人偏好選擇 + 片商分類功能", font=("Arial", 10)).pack()
        
        # 路徑選擇區域
        path_frame = ttk.LabelFrame(main_frame, text="📁 目標資料夾", padding="10")
        path_frame.pack(fill="x", pady=5)
        path_entry = ttk.Entry(path_frame, textvariable=self.selected_path, font=("Arial", 10))
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.browse_btn = ttk.Button(path_frame, text="瀏覽...", command=self.browse_folder)
        self.browse_btn.pack(side="left")
        
        # 功能按鈕區域
        button_frame = ttk.LabelFrame(main_frame, text="🔧 功能選擇", padding="10")
        button_frame.pack(fill="x", pady=5)
          # 第一排按鈕 - 分離的搜尋按鈕
        row1_frame = ttk.Frame(button_frame)
        row1_frame.pack(fill="x", pady=(0, 5))
        row1_frame.columnconfigure((0, 1, 2), weight=1)
        
        self.search_japanese_btn = ttk.Button(row1_frame, text="🇯🇵 日文網站搜尋", command=self.start_japanese_search)
        self.search_japanese_btn.grid(row=0, column=0, padx=(0, 2), sticky="ew", ipady=5)
        
        self.search_javdb_btn = ttk.Button(row1_frame, text="📊 JAVDB 搜尋", command=self.start_javdb_search)
        self.search_javdb_btn.grid(row=0, column=1, padx=2, sticky="ew", ipady=5)
        
        self.settings_btn = ttk.Button(row1_frame, text="⚙️ 偏好設定", command=self.show_preferences)
        self.settings_btn.grid(row=0, column=2, padx=(2, 0), sticky="ew", ipady=5)
        
        # 第二排按鈕 - 包含片商分類按鈕
        row2_frame = ttk.Frame(button_frame)
        row2_frame.pack(fill="x", pady=(0, 5))
        row2_frame.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.interactive_move_btn = ttk.Button(row2_frame, text="🤝 互動式移動", command=self.start_interactive_move)
        self.interactive_move_btn.grid(row=0, column=0, padx=(0, 2), sticky="ew", ipady=5)
        
        self.standard_move_btn = ttk.Button(row2_frame, text="📁 標準移動", command=self.start_standard_move)
        self.standard_move_btn.grid(row=0, column=1, padx=2, sticky="ew", ipady=5)
        
        # 新增片商分類按鈕
        self.studio_classify_btn = ttk.Button(row2_frame, text="🏢 片商分類", command=self.start_studio_classification)
        self.studio_classify_btn.grid(row=0, column=2, padx=2, sticky="ew", ipady=5)
        
        self.stop_btn = ttk.Button(row2_frame, text="🛑 中止任務", command=self.stop_task, state="disabled")
        self.stop_btn.grid(row=0, column=3, padx=(2, 0), sticky="ew", ipady=5)
        
        # 結果顯示區域
        result_frame = ttk.LabelFrame(main_frame, text="📋 執行結果", padding="10")
        result_frame.pack(fill="both", expand=True, pady=5)
        
        self.result_text = tk.Text(result_frame, wrap="word", font=("Consolas", 9), height=25, relief="flat", padx=5, pady=5)
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 狀態列
        self.status_var = tk.StringVar(value="就緒")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
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

    def on_closing(self):
        self.is_running = False
        self.stop_event.set()
        self.root.destroy()

    def browse_folder(self):
        initial_dir = self.selected_path.get()
        if not Path(initial_dir).is_dir(): 
            initial_dir = str(Path.home())
        folder_path = filedialog.askdirectory(title="選擇目標資料夾", initialdir=initial_dir)
        if folder_path:
            self.selected_path.set(folder_path)
            self.config_manager.config.set('paths', 'default_input_dir', folder_path)
            self.config_manager.save_config()

    def clear_results(self):
        if self.is_running and self.result_text.winfo_exists():
            self.result_text.delete(1.0, tk.END)

    def update_progress(self, message: str):
        if self.is_running and self.root.winfo_exists():
            self.root.after(0, self._insert_text, message)

    def _insert_text(self, message: str):
        if self.is_running and self.result_text.winfo_exists():
            self.result_text.insert(tk.END, message)
            self.result_text.see(tk.END)

    def _toggle_buttons(self, is_task_running: bool):
        if not self.is_running: 
            return
        search_state = 'disabled' if is_task_running else 'normal'
        stop_state = 'normal' if is_task_running else 'disabled'
        
        # 更新按鈕列表，包含分離搜尋按鈕和片商分類按鈕
        buttons = [
            self.browse_btn, self.search_japanese_btn, self.search_javdb_btn,
            self.interactive_move_btn, self.standard_move_btn, self.studio_classify_btn, self.settings_btn
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
        self.update_progress("\n⚠️ 正在中止任務，請稍候...\n")
        self.stop_event.set()

    def start_search(self):
        path = self.selected_path.get()
        if not Path(path).is_dir(): 
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n{'='*60}\n")
        self.stop_event.clear()
        threading.Thread(target=self._run_task, args=(self._search_worker, path), daemon=True).start()

    def _search_worker(self, path):
        self.status_var.set("執行中：掃描與搜尋...")
        result = self.core.process_and_search(path, self.stop_event, self.update_progress)
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress(f"\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result['status'] == 'success':
                self.update_progress(f"\n{'='*60}\n🎉 搜尋任務完成！\n")
                self.status_var.set("就緒")
            else:
                self.update_progress(f"\n💥 錯誤: {result['message']}\n")
                self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")

    def start_japanese_search(self):
        """開始日文網站搜尋"""
        path = self.selected_path.get()
        if not Path(path).is_dir(): 
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n")
        self.update_progress(f"搜尋模式: 🇯🇵 日文網站 (av-wiki.net, chiba-f.net)\n")
        self.update_progress(f"{'='*60}\n")
        self.stop_event.clear()
        threading.Thread(target=self._run_task, args=(self._japanese_search_worker, path), daemon=True).start()

    def start_javdb_search(self):
        """開始JAVDB搜尋"""
        path = self.selected_path.get()
        if not Path(path).is_dir(): 
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        self.clear_results()
        self.update_progress(f"目標資料夾: {path}\n")
        self.update_progress(f"搜尋模式: 📊 JAVDB 網站\n")
        self.update_progress(f"{'='*60}\n")
        self.stop_event.clear()
        threading.Thread(target=self._run_task, args=(self._javdb_search_worker, path), daemon=True).start()

    def _japanese_search_worker(self, path):
        """日文網站搜尋工作者"""
        self.status_var.set("執行中：日文網站搜尋...")
        result = self.core.process_and_search_japanese_sites(path, self.stop_event, self.update_progress)
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress(f"\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result['status'] == 'success':
                self.update_progress(f"\n{'='*60}\n🎉 日文網站搜尋任務完成！\n")
                self.status_var.set("就緒")
            else:
                self.update_progress(f"\n💥 錯誤: {result['message']}\n")
                self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")

    def _javdb_search_worker(self, path):
        """JAVDB搜尋工作者"""
        self.status_var.set("執行中：JAVDB搜尋...")
        result = self.core.process_and_search_javdb(path, self.stop_event, self.update_progress)
        if self.is_running:
            if self.stop_event.is_set():
                self.update_progress(f"\n🛑 任務已由使用者中止。\n")
                self.status_var.set("任務已中止")
            elif result['status'] == 'success':
                self.update_progress(f"\n{'='*60}\n🎉 JAVDB搜尋任務完成！\n")
                self.status_var.set("就緒")
            else:
                self.update_progress(f"\n💥 錯誤: {result['message']}\n")
                self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")

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
        self.update_progress(f"🤝 互動式分類模式\n目標資料夾: {path}\n{'='*60}\n")
        threading.Thread(target=self._run_task, args=(self._interactive_move_worker, path), daemon=True).start()

    def _interactive_move_worker(self, path):
        self.status_var.set("執行中：互動式檔案移動...")
        result = self.core.interactive_move_files(path, self.update_progress)
        if self.is_running:
            if result.get('status') == 'success' and 'stats' in result:
                stats = result['stats']
                summary = (f"\n{'='*60}\n🤝 互動式分類完成！\n\n"
                          f"  ✅ 成功移動: {stats['success']}\n"
                          f"  ⚠️ 已存在: {stats['exists']}\n"
                          f"  ❓ 無資料: {stats['no_data']}\n"
                          f"  ⏭️ 跳過: {stats['skipped']}\n"
                          f"  ❌ 失敗: {stats['failed']}\n")
                self.update_progress(summary)
                self.status_var.set("就緒")
            else:
                self.update_progress(f"\n💥 錯誤: {result.get('message', '未知錯誤')}\n")
                self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")

    def start_standard_move(self):
        path = self.selected_path.get()
        if not Path(path).is_dir(): 
            messagebox.showerror("錯誤", "請選擇一個有效的資料夾！")
            return
        if not messagebox.askyesno("確認智慧分類", f"確定要將 '{path}' 資料夾中的影片進行智慧分類嗎？\n\n🎯 智慧分類模式：\n• 單人影片：自動分類到對應女優資料夾\n• 多人共演：彈出互動選擇對話框\n\n（只會移動此資料夾根目錄下的檔案）"): 
            return
        self.clear_results()
        self.update_progress(f"📁 智慧分類模式\n目標資料夾: {path}\n{'='*60}\n")
        threading.Thread(target=self._run_task, args=(self._standard_move_worker, path), daemon=True).start()

    def _standard_move_worker(self, path):
        self.status_var.set("執行中：智慧檔案移動...")
        result = self.core.move_files(path, self.update_progress)
        if self.is_running:
            if result.get('status') == 'success' and 'stats' in result:
                stats = result['stats']
                interactive_info = f"  🤝 互動處理: {stats['interactive']}\n" if stats.get('interactive', 0) > 0 else ""
                summary = (f"\n{'='*60}\n📁 智慧分類完成！\n\n"
                          f"  ✅ 成功: {stats['success']}\n"
                          f"  ⚠️ 已存在: {stats['exists']}\n"
                          f"  ❓ 無資料: {stats['no_data']}\n"
                          f"  ❌ 失敗: {stats['failed']}\n"
                          f"{interactive_info}")
                self.update_progress(summary)
                self.status_var.set("就緒")
            else:
                self.update_progress(f"\n💥 錯誤: {result.get('message', '未知錯誤')}\n")
                self.status_var.set(f"錯誤: {result.get('message', '未知錯誤')}")

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
        self.update_progress(f"🏢 片商分類模式\n目標資料夾: {path}\n{'='*60}\n")
        
        # 在背景執行片商分類
        threading.Thread(target=self._run_task, args=(self._studio_classification_worker, path), daemon=True).start()

    def _studio_classification_worker(self, path):
        """片商分類工作執行緒"""
        self.status_var.set("執行中：片商分類...")
        
        try:
            result = self.core.classify_actresses_by_studio(path, self.update_progress)
            
            if self.is_running:
                if result.get('status') == 'success':
                    # 顯示結果摘要
                    move_stats = result.get('move_stats', {})
                    total_actresses = result.get('total_actresses', 0)
                    
                    summary = self.core.studio_classifier.get_classification_summary(total_actresses, move_stats)
                    self.update_progress(f"\n{'='*60}\n{summary}")
                    
                    self.status_var.set("就緒")
                else:
                    error_msg = result.get('message', '未知錯誤')
                    self.update_progress(f"\n💥 錯誤: {error_msg}\n")
                    self.status_var.set(f"錯誤: {error_msg}")
                    
        except Exception as e:
            if self.is_running:
                self.update_progress(f"\n💥 片商分類發生未預期錯誤: {str(e)}\n")
                self.status_var.set(f"錯誤: {str(e)}")
