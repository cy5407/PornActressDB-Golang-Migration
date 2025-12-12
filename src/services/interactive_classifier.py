"""
互動式分類器模組
"""

import logging
import tkinter as tk
from tkinter import ttk

from src.models.config import PreferenceManager

logger = logging.getLogger(__name__)


class InteractiveClassifier:
    """互動式分類器 - 處理多女優共演的偏好選擇"""

    def __init__(self, preference_manager: PreferenceManager, gui_parent=None):
        self.preference_manager = preference_manager
        self.gui_parent = gui_parent
        self.pending_decisions = {}

    def get_classification_choice(
        self, code: str, actresses: list[str]
    ) -> tuple[str, bool]:
        """取得分類選擇 - 返回 (選擇的女優, 是否記住偏好)"""

        if len(actresses) == 1:
            return actresses[0], False

        # 檢查已有偏好
        preferred = self.preference_manager.get_preferred_actress(actresses)
        if preferred:
            return preferred, False

        # 需要使用者選擇
        if self.gui_parent:
            return self._show_gui_choice_dialog(code, actresses)
        else:
            return self._show_console_choice(code, actresses)

    def _show_gui_choice_dialog(
        self, code: str, actresses: list[str]
    ) -> tuple[str, bool]:
        """顯示 GUI 選擇對話框"""

        logger.info(f"🎬 顯示互動式對話框 - 番號: {code}, 女優: {actresses}")
        result = {"choice": None, "remember": False}

        dialog = tk.Toplevel(self.gui_parent)
        dialog.title(f"選擇分類偏好 - {code}")
        dialog.geometry("600x500")
        dialog.resizable(True, True)  # 允許調整視窗大小
        dialog.minsize(500, 450)  # 設定最小大小

        # 確保對話框在最前面並獲得焦點
        dialog.transient(self.gui_parent)
        dialog.grab_set()
        dialog.focus_set()
        dialog.lift()
        dialog.attributes("-topmost", True)

        # 置中顯示對話框
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (500 // 2)
        dialog.geometry(f"600x500+{x}+{y}")
        # 主要內容框架
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)

        # 標題
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill="x", pady=(0, 15))
        ttk.Label(
            title_frame, text=f"🎬 影片 {code} 包含多位女優", font=("Arial", 14, "bold")
        ).pack()
        ttk.Label(
            title_frame, text="請選擇要分類到哪位女優的資料夾：", font=("Arial", 10)
        ).pack(pady=5)

        # 選擇區域（可滾動）
        choice_frame = ttk.LabelFrame(main_frame, text="女優選擇", padding=10)
        choice_frame.pack(fill="both", expand=True, pady=(0, 10))

        # 創建滾動區域（當女優數量很多時）
        canvas = tk.Canvas(choice_frame)
        scrollbar = ttk.Scrollbar(choice_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        selected_actress = tk.StringVar()

        # 女優選項
        for i, actress in enumerate(actresses):
            rb = ttk.Radiobutton(
                scrollable_frame,
                text=f"{i + 1}. {actress}",
                variable=selected_actress,
                value=actress,
            )
            rb.pack(anchor="w", pady=2)
            if i == 0:
                rb.invoke()

        # 特殊選項
        ttk.Separator(scrollable_frame, orient="horizontal").pack(fill="x", pady=5)
        ttk.Radiobutton(
            scrollable_frame,
            text=f"{len(actresses) + 1}. 放到「多人共演」資料夾",
            variable=selected_actress,
            value="多人共演",
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            scrollable_frame,
            text=f"{len(actresses) + 2}. 跳過此檔案",
            variable=selected_actress,
            value="SKIP",
        ).pack(anchor="w", pady=2)

        # 只在需要時顯示滾動條
        if len(actresses) > 8:
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
        else:
            canvas.pack(fill="both", expand=True)

        # 記住偏好選項
        remember_frame = ttk.Frame(main_frame)
        remember_frame.pack(fill="x", pady=(10, 15))
        remember_var = tk.BooleanVar()
        ttk.Checkbutton(
            remember_frame,
            text="🧠 記住此組合的偏好設定 (下次自動分類)",
            variable=remember_var,
        ).pack()

        # 按鈕區域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=15)

        def confirm_choice():
            choice = selected_actress.get()
            logger.info(f"使用者選擇: {choice}")
            if choice:
                result["choice"] = choice
                result["remember"] = remember_var.get()
                logger.info(f"記住偏好: {result['remember']}")
                dialog.destroy()
            else:
                # 如果沒有選擇，提醒使用者
                from tkinter import messagebox

                messagebox.showwarning("請選擇", "請先選擇一個女優或選項！")

        def skip_all():
            result["choice"] = "SKIP_ALL"
            result["remember"] = False
            logger.info("使用者選擇跳過所有")
            dialog.destroy()

        def cancel_choice():
            result["choice"] = "SKIP"
            result["remember"] = False
            logger.info("使用者取消選擇")
            dialog.destroy()

        # 按鈕佈局改進
        button_frame.pack(fill="x", pady=(0, 0))

        confirm_btn = ttk.Button(
            button_frame, text="✅ 確認選擇", command=confirm_choice
        )
        confirm_btn.pack(side="left", padx=(0, 5), ipadx=10, ipady=3)

        skip_all_btn = ttk.Button(button_frame, text="⏭️ 全部跳過", command=skip_all)
        skip_all_btn.pack(side="left", padx=5, ipadx=10, ipady=3)

        cancel_btn = ttk.Button(button_frame, text="❌ 取消", command=cancel_choice)
        cancel_btn.pack(side="left", padx=5, ipadx=10, ipady=3)
        # 設置預設按鈕和鍵盤快捷鍵
        confirm_btn.focus_set()
        dialog.bind("<Return>", lambda e: confirm_choice())
        dialog.bind("<Escape>", lambda e: cancel_choice())

        # 添加滾輪支援
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        dialog.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<MouseWheel>", _on_mousewheel)

        # 等待使用者選擇
        dialog.wait_window()

        choice = result.get("choice")
        if not choice:
            return "SKIP", False

        remember = result.get("remember", False)
        return choice, remember

    def _show_console_choice(self, code: str, actresses: list[str]) -> tuple[str, bool]:
        """顯示控制台選擇介面"""

        print(f"\n🎬 影片 {code} 包含以下女優：")
        for i, actress in enumerate(actresses, 1):
            print(f"  {i}. {actress}")

        print(f"  {len(actresses) + 1}. 放到「多人共演」資料夾")
        print(f"  {len(actresses) + 2}. 跳過此檔案")
        print("  0. 跳過所有後續選擇")

        while True:
            try:
                choice = input("請選擇 (輸入數字): ").strip()

                if choice == "0":
                    return "SKIP_ALL", False

                choice_num = int(choice)

                if 1 <= choice_num <= len(actresses):
                    chosen = actresses[choice_num - 1]

                    remember_input = (
                        input(
                            f"是否記住 {', '.join(actresses)} 的分類偏好到 {chosen}？(y/n): "
                        )
                        .strip()
                        .lower()
                    )
                    remember = remember_input in ["y", "yes", "是"]

                    return chosen, remember

                elif choice_num == len(actresses) + 1:
                    return "多人共演", False

                elif choice_num == len(actresses) + 2:
                    return "SKIP", False

                else:
                    print("❌ 無效選擇，請重新輸入")

            except ValueError:
                print("❌ 請輸入有效的數字")
            except KeyboardInterrupt:
                print("\n⏹️ 使用者中斷操作")
                return "SKIP_ALL", False
