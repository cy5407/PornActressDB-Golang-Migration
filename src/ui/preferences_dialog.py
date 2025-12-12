"""
偏好設定對話框模組
"""

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

logger = logging.getLogger(__name__)


class PreferenceDialog:
    """偏好設定對話框 - 包含片商分類設定"""

    def __init__(self, parent, preference_manager):
        self.parent = parent
        self.preference_manager = preference_manager
        self.dialog = tk.Toplevel(parent)
        self.setup_dialog()

    def setup_dialog(self):
        self.dialog.title("⚙️ 偏好設定")
        self.dialog.geometry("650x550")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill="both", expand=True)

        # 標題
        ttk.Label(main_frame, text="⚙️ 個人化偏好設定", font=("Arial", 14, "bold")).pack(
            pady=(0, 15)
        )

        # 筆記本容器
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 15))

        # 女優偏好頁面
        self._setup_actress_preferences_tab(notebook)

        # 分類選項頁面
        self._setup_classification_options_tab(notebook)

        # 片商分類頁面
        self._setup_studio_classification_tab(notebook)

        # 共演記錄頁面
        self._setup_collaboration_tab(notebook)

        # 按鈕區域
        self._setup_buttons(main_frame)

        # 載入當前設定
        self.load_current_preferences()

    def _setup_actress_preferences_tab(self, notebook):
        """設定女優偏好頁面"""
        actress_frame = ttk.Frame(notebook, padding="10")
        notebook.add(actress_frame, text="👩 女優偏好")

        # 最愛女優設定
        ttk.Label(
            actress_frame, text="⭐ 最愛女優（最高優先級）", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 5))
        fav_frame = ttk.Frame(actress_frame)
        fav_frame.pack(fill="x", pady=(0, 15))

        self.favorite_listbox = tk.Listbox(fav_frame, height=4)
        self.favorite_listbox.pack(side="left", fill="both", expand=True)

        fav_btn_frame = ttk.Frame(fav_frame)
        fav_btn_frame.pack(side="right", fill="y", padx=(10, 0))
        ttk.Button(
            fav_btn_frame, text="新增", command=lambda: self.add_actress("favorite")
        ).pack(fill="x", pady=1)
        ttk.Button(
            fav_btn_frame, text="移除", command=lambda: self.remove_actress("favorite")
        ).pack(fill="x", pady=1)

        # 優先女優設定
        ttk.Label(
            actress_frame, text="🔸 優先女優（次要優先級）", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 5))
        priority_frame = ttk.Frame(actress_frame)
        priority_frame.pack(fill="x", pady=(0, 15))

        self.priority_listbox = tk.Listbox(priority_frame, height=4)
        self.priority_listbox.pack(side="left", fill="both", expand=True)

        priority_btn_frame = ttk.Frame(priority_frame)
        priority_btn_frame.pack(side="right", fill="y", padx=(10, 0))
        ttk.Button(
            priority_btn_frame,
            text="新增",
            command=lambda: self.add_actress("priority"),
        ).pack(fill="x", pady=1)
        ttk.Button(
            priority_btn_frame,
            text="移除",
            command=lambda: self.remove_actress("priority"),
        ).pack(fill="x", pady=1)

    def _setup_classification_options_tab(self, notebook):
        """設定分類選項頁面"""
        options_frame = ttk.Frame(notebook, padding="10")
        notebook.add(options_frame, text="🔧 分類選項")

        # 檔名標籤選項
        ttk.Label(
            options_frame, text="📝 檔案命名選項", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))

        self.auto_tag_var = tk.BooleanVar(
            value=self.preference_manager.preferences.get("auto_tag_filenames", True)
        )
        ttk.Checkbutton(
            options_frame,
            text="自動標籤化檔名（在多人共演檔案名稱中標記所有女優）",
            variable=self.auto_tag_var,
        ).pack(anchor="w", pady=2)

        # 跳過選項
        ttk.Label(options_frame, text="⏭️ 跳過選項", font=("Arial", 11, "bold")).pack(
            anchor="w", pady=(20, 10)
        )

        self.skip_single_var = tk.BooleanVar(
            value=self.preference_manager.preferences.get("skip_single_actress", False)
        )
        ttk.Checkbutton(
            options_frame,
            text="跳過單人作品的確認（單人作品直接分類，不詢問）",
            variable=self.skip_single_var,
        ).pack(anchor="w", pady=2)

    def _setup_studio_classification_tab(self, notebook):
        """設定片商分類頁面"""
        studio_frame = ttk.Frame(notebook, padding="10")
        notebook.add(studio_frame, text="🏢 片商分類")

        # 資料夾命名設定
        ttk.Label(
            studio_frame, text="📁 資料夾命名設定", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))

        # 單體企劃女優資料夾名稱
        solo_name_frame = ttk.Frame(studio_frame)
        solo_name_frame.pack(fill="x", pady=(0, 15))

        ttk.Label(solo_name_frame, text="單體企劃女優資料夾名稱：").pack(side="left")
        self.solo_folder_var = tk.StringVar(
            value=self.preference_manager.get_solo_folder_name()
        )
        solo_entry = ttk.Entry(
            solo_name_frame, textvariable=self.solo_folder_var, width=20
        )
        solo_entry.pack(side="left", padx=(10, 0))

        # 說明文字
        solo_desc = ttk.Label(
            studio_frame,
            text="💡 說明：信心度不足60%或跨多片商的女優將歸類到此資料夾",
            font=("Arial", 9),
            foreground="gray",
        )
        solo_desc.pack(anchor="w", pady=(0, 20))

        # 分類規則設定
        ttk.Label(
            studio_frame, text="📊 分類規則設定", font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 10))

        # 信心度門檻設定
        threshold_frame = ttk.Frame(studio_frame)
        threshold_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(threshold_frame, text="片商信心度門檻：").pack(side="left")
        self.confidence_var = tk.DoubleVar(
            value=self.preference_manager.get_confidence_threshold()
        )
        confidence_spinbox = ttk.Spinbox(
            threshold_frame,
            from_=50.0,
            to=100.0,
            increment=5.0,
            textvariable=self.confidence_var,
            width=10,
            format="%.1f",
        )
        confidence_spinbox.pack(side="left", padx=(10, 5))
        ttk.Label(threshold_frame, text="%").pack(side="left")

        # 門檻說明
        threshold_desc = ttk.Label(
            studio_frame,
            text="💡 說明：女優在某片商的影片占比超過此門檻時，歸類到該片商資料夾",
            font=("Arial", 9),
            foreground="gray",
        )
        threshold_desc.pack(anchor="w", pady=(0, 20))

        # 其他選項
        ttk.Label(studio_frame, text="🔧 其他選項", font=("Arial", 11, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        # 自動建立片商資料夾
        self.auto_create_var = tk.BooleanVar(
            value=self.preference_manager.should_auto_create_studio_folders()
        )
        ttk.Checkbutton(
            studio_frame,
            text="自動建立片商資料夾（如果不存在）",
            variable=self.auto_create_var,
        ).pack(anchor="w", pady=2)

        # 移動前備份
        self.backup_before_var = tk.BooleanVar(
            value=self.preference_manager.should_backup_before_move()
        )
        ttk.Checkbutton(
            studio_frame, text="移動前建立備份記錄", variable=self.backup_before_var
        ).pack(anchor="w", pady=2)

    def _setup_collaboration_tab(self, notebook):
        """設定共演記錄頁面"""
        collaboration_frame = ttk.Frame(notebook, padding="10")
        notebook.add(collaboration_frame, text="🤝 共演記錄")

        ttk.Label(
            collaboration_frame,
            text="🤝 已記住的共演組合偏好",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        # 共演記錄列表
        collab_list_frame = ttk.Frame(collaboration_frame)
        collab_list_frame.pack(fill="both", expand=True)

        # 創建 Treeview 來顯示共演記錄
        columns = ("組合", "選擇的女優")
        self.collab_tree = ttk.Treeview(
            collab_list_frame, columns=columns, show="headings", height=10
        )
        self.collab_tree.heading("組合", text="共演組合")
        self.collab_tree.heading("選擇的女優", text="分類到")
        self.collab_tree.column("組合", width=300)
        self.collab_tree.column("選擇的女優", width=150)

        collab_scrollbar = ttk.Scrollbar(
            collab_list_frame, orient="vertical", command=self.collab_tree.yview
        )
        self.collab_tree.configure(yscrollcommand=collab_scrollbar.set)

        self.collab_tree.pack(side="left", fill="both", expand=True)
        collab_scrollbar.pack(side="right", fill="y")

        # 共演記錄按鈕
        collab_btn_frame = ttk.Frame(collaboration_frame)
        collab_btn_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(
            collab_btn_frame, text="🗑️ 清除選中記錄", command=self.remove_collaboration
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            collab_btn_frame,
            text="🗑️ 清除全部記錄",
            command=self.clear_all_collaborations,
        ).pack(side="left")

    def _setup_buttons(self, main_frame):
        """設定按鈕區域"""
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")

        ttk.Button(
            button_frame, text="💾 儲存設定", command=self.save_preferences
        ).pack(side="right", padx=(5, 0))
        ttk.Button(button_frame, text="❌ 取消", command=self.dialog.destroy).pack(
            side="right"
        )
        ttk.Button(
            button_frame, text="🔄 重設為預設值", command=self.reset_preferences
        ).pack(side="left")

    def load_current_preferences(self):
        """載入當前偏好設定"""
        # 載入最愛女優
        self.favorite_listbox.delete(0, tk.END)
        for actress in self.preference_manager.preferences.get(
            "favorite_actresses", []
        ):
            self.favorite_listbox.insert(tk.END, actress)

        # 載入優先女優
        self.priority_listbox.delete(0, tk.END)
        for actress in self.preference_manager.preferences.get(
            "priority_actresses", []
        ):
            self.priority_listbox.insert(tk.END, actress)

        # 載入共演記錄
        self.collab_tree.delete(*self.collab_tree.get_children())
        for combination, chosen in self.preference_manager.preferences.get(
            "collaboration_preferences", {}
        ).items():
            actresses = combination.replace("+", " & ")
            self.collab_tree.insert("", "end", values=(actresses, chosen))

        # 載入片商分類設定
        if hasattr(self, "solo_folder_var"):
            self.solo_folder_var.set(self.preference_manager.get_solo_folder_name())

        if hasattr(self, "confidence_var"):
            self.confidence_var.set(self.preference_manager.get_confidence_threshold())

        if hasattr(self, "auto_create_var"):
            self.auto_create_var.set(
                self.preference_manager.should_auto_create_studio_folders()
            )

        if hasattr(self, "backup_before_var"):
            self.backup_before_var.set(
                self.preference_manager.should_backup_before_move()
            )

    def add_actress(self, category: str):
        """新增女優到指定分類"""
        actress_name = simpledialog.askstring(
            "新增女優",
            f"請輸入要新增到{'最愛' if category == 'favorite' else '優先'}女優的名稱：",
        )
        if actress_name and actress_name.strip():
            actress_name = actress_name.strip()
            listbox = (
                self.favorite_listbox
                if category == "favorite"
                else self.priority_listbox
            )

            # 檢查是否已存在
            current_items = [listbox.get(i) for i in range(listbox.size())]
            if actress_name not in current_items:
                listbox.insert(tk.END, actress_name)
            else:
                messagebox.showwarning(
                    "重複項目", f"女優 '{actress_name}' 已在清單中！"
                )

    def remove_actress(self, category: str):
        """從指定分類移除女優"""
        listbox = (
            self.favorite_listbox if category == "favorite" else self.priority_listbox
        )
        selection = listbox.curselection()
        if selection:
            listbox.delete(selection[0])
        else:
            messagebox.showinfo("未選擇項目", "請先選擇要移除的女優！")

    def remove_collaboration(self):
        """移除選中的共演記錄"""
        selection = self.collab_tree.selection()
        if selection:
            for item in selection:
                self.collab_tree.delete(item)
        else:
            messagebox.showinfo("未選擇項目", "請先選擇要移除的共演記錄！")

    def clear_all_collaborations(self):
        """清除所有共演記錄"""
        if messagebox.askyesno(
            "確認清除", "確定要清除所有共演記錄嗎？此操作無法復原。"
        ):
            self.collab_tree.delete(*self.collab_tree.get_children())

    def reset_preferences(self):
        """重設為預設值"""
        if messagebox.askyesno(
            "確認重設", "確定要重設所有偏好設定為預設值嗎？此操作無法復原。"
        ):
            # 清空所有列表
            self.favorite_listbox.delete(0, tk.END)
            self.priority_listbox.delete(0, tk.END)
            self.collab_tree.delete(*self.collab_tree.get_children())

            # 重設選項
            self.auto_tag_var.set(True)
            self.skip_single_var.set(False)

            # 重設片商分類設定
            if hasattr(self, "solo_folder_var"):
                self.solo_folder_var.set("單體企劃女優")
            if hasattr(self, "confidence_var"):
                self.confidence_var.set(60.0)
            if hasattr(self, "auto_create_var"):
                self.auto_create_var.set(True)
            if hasattr(self, "backup_before_var"):
                self.backup_before_var.set(True)

    def save_preferences(self):
        """儲存偏好設定 - 包含片商分類設定"""
        try:
            # 收集最愛女優
            favorite_actresses = [
                self.favorite_listbox.get(i)
                for i in range(self.favorite_listbox.size())
            ]

            # 收集優先女優
            priority_actresses = [
                self.priority_listbox.get(i)
                for i in range(self.priority_listbox.size())
            ]

            # 收集共演記錄
            collaboration_preferences = {}
            for item in self.collab_tree.get_children():
                values = self.collab_tree.item(item)["values"]
                if len(values) >= 2:
                    combination_display = values[0]
                    chosen = values[1]
                    combination_key = combination_display.replace(" & ", "+")
                    collaboration_preferences[combination_key] = chosen

            # 收集片商分類設定
            solo_folder_name = self.solo_folder_var.get().strip()
            if not solo_folder_name:
                solo_folder_name = "單體企劃女優"

            confidence_threshold = self.confidence_var.get()
            auto_create_folders = self.auto_create_var.get()
            backup_before_move = self.backup_before_var.get()

            # 更新偏好設定
            self.preference_manager.preferences.update(
                {
                    "favorite_actresses": favorite_actresses,
                    "priority_actresses": priority_actresses,
                    "collaboration_preferences": collaboration_preferences,
                    "auto_tag_filenames": self.auto_tag_var.get(),
                    "skip_single_actress": self.skip_single_var.get(),
                    # 新增片商分類設定
                    "solo_folder_name": solo_folder_name,
                    "studio_classification": {
                        "confidence_threshold": confidence_threshold,
                        "auto_create_studio_folders": auto_create_folders,
                        "backup_before_move": backup_before_move,
                    },
                }
            )

            # 儲存到檔案
            self.preference_manager.save_preferences()

            messagebox.showinfo("設定已儲存", "偏好設定已成功儲存！")
            self.dialog.destroy()

        except Exception as e:
            messagebox.showerror("儲存失敗", f"儲存偏好設定時發生錯誤：\n{str(e)}")
