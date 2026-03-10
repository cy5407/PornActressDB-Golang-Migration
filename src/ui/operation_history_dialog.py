"""
操作歷史對話框

提供 Go CLI 操作歷史檢視和回滾功能的 GUI 介面
"""

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

logger = logging.getLogger(__name__)


class OperationHistoryDialog:
    """
    操作歷史對話框
    
    顯示檔案移動操作的歷史紀錄，並提供回滾功能
    """
    
    def __init__(self, parent: tk.Tk, file_mover):
        """
        初始化對話框
        
        Args:
            parent: 父視窗
            file_mover: FileMover 實例
        """
        self.parent = parent
        self.file_mover = file_mover
        self.dialog: Optional[tk.Toplevel] = None
        self.tree: Optional[ttk.Treeview] = None
        self.operations: list = []
        
    def show(self):
        """顯示對話框"""
        # 檢查 Go 模式是否可用
        if not self.file_mover.use_go:
            messagebox.showinfo(
                "提示",
                "操作歷史功能需要啟用 Go 加速模式。\n\n"
                "請在 config.ini 中設定：\n"
                "[go_integration]\n"
                "enabled = true",
                parent=self.parent
            )
            return
        
        if not self.file_mover.go_bridge:
            messagebox.showerror(
                "錯誤",
                "無法連接到 Go CLI。\n\n"
                "請確認 classifier.exe 是否存在。",
                parent=self.parent
            )
            return
        
        # 建立對話框
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("📜 操作歷史")
        self.dialog.geometry("700x450")
        self.dialog.minsize(600, 350)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 置中顯示
        self._center_dialog()
        
        # 建立內容
        self._create_widgets()
        
        # 載入歷史
        self._load_history()
        
    def _center_dialog(self):
        """將對話框置中"""
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 700) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 450) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
    def _create_widgets(self):
        """建立介面元件"""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 標題和說明
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            header_frame,
            text="📜 檔案移動操作歷史",
            font=("Microsoft JhengHei UI", 12, "bold")
        ).pack(side="left")
        
        # 重新整理按鈕
        refresh_btn = ttk.Button(
            header_frame,
            text="🔄 重新整理",
            command=self._load_history,
            width=12
        )
        refresh_btn.pack(side="right")
        
        # 操作列表
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Treeview
        columns = ("id", "time", "type", "status", "items")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )
        
        # 設定欄位
        self.tree.heading("id", text="操作 ID")
        self.tree.heading("time", text="時間")
        self.tree.heading("type", text="類型")
        self.tree.heading("status", text="狀態")
        self.tree.heading("items", text="項目數")
        
        self.tree.column("id", width=120, anchor="w")
        self.tree.column("time", width=150, anchor="center")
        self.tree.column("type", width=100, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("items", width=80, anchor="center")
        
        # 捲軸
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 綁定雙擊事件
        self.tree.bind("<Double-1>", self._on_item_double_click)
        
        # 底部按鈕區
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        # 狀態標籤
        self.status_label = ttk.Label(
            button_frame,
            text="選擇一個操作進行回滾",
            foreground="gray"
        )
        self.status_label.pack(side="left")
        
        # 關閉按鈕
        close_btn = ttk.Button(
            button_frame,
            text="關閉",
            command=self.dialog.destroy,
            width=10
        )
        close_btn.pack(side="right", padx=(5, 0))
        
        # 回滾按鈕
        self.rollback_btn = ttk.Button(
            button_frame,
            text="⏪ 回滾選中操作",
            command=self._rollback_selected,
            width=15
        )
        self.rollback_btn.pack(side="right")
        
        # 查看詳情按鈕
        self.detail_btn = ttk.Button(
            button_frame,
            text="📋 查看詳情",
            command=self._show_details,
            width=12
        )
        self.detail_btn.pack(side="right", padx=(0, 5))
        
    def _load_history(self):
        """載入操作歷史"""
        # 清空現有項目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            # 從 Go 橋接層取得歷史
            self.operations = self.file_mover.list_operations(limit=50)
            
            if not self.operations:
                self.status_label.config(text="沒有操作紀錄", foreground="gray")
                return
            
            # 填充列表
            for op in self.operations:
                op_id = op.get("id", "")[:12] + "..."  # 縮短 ID
                timestamp = op.get("timestamp", "")
                op_type = self._format_type(op.get("type", ""))
                status = self._format_status(op.get("status", ""))
                items = len(op.get("items", []))
                
                self.tree.insert("", "end", values=(op_id, timestamp, op_type, status, items))
            
            self.status_label.config(
                text=f"共 {len(self.operations)} 筆紀錄",
                foreground="black"
            )
            
        except Exception as e:
            logger.error(f"載入操作歷史失敗: {e}")
            self.status_label.config(text=f"載入失敗: {e}", foreground="red")
    
    def _format_type(self, op_type: str) -> str:
        """格式化操作類型"""
        type_map = {
            "move": "📁 移動",
            "batch_move": "📦 批次移動",
            "move_batch": "📦 批次移動",
            "copy": "📋 複製",
        }
        return type_map.get(op_type, op_type)
    
    def _format_status(self, status: str) -> str:
        """格式化狀態"""
        status_map = {
            "completed": "✅ 完成",
            "partial": "⚠️ 部分",
            "failed": "❌ 失敗",
            "rolled_back": "↩️ 已回滾",
        }
        return status_map.get(status, status)
    
    def _get_selected_operation(self) -> Optional[dict]:
        """取得選中的操作"""
        selection = self.tree.selection()
        if not selection:
            return None
        
        # 取得選中項目的索引
        item = selection[0]
        index = self.tree.index(item)
        
        if 0 <= index < len(self.operations):
            return self.operations[index]
        return None
    
    def _on_item_double_click(self, event):
        """雙擊項目時顯示詳情"""
        self._show_details()
    
    def _show_details(self):
        """顯示操作詳情"""
        op = self._get_selected_operation()
        if not op:
            messagebox.showinfo("提示", "請先選擇一個操作", parent=self.dialog)
            return
        
        # 建立詳情對話框
        detail_dialog = tk.Toplevel(self.dialog)
        detail_dialog.title("操作詳情")
        detail_dialog.geometry("500x400")
        detail_dialog.transient(self.dialog)
        detail_dialog.grab_set()
        
        # 內容
        frame = ttk.Frame(detail_dialog, padding="10")
        frame.pack(fill="both", expand=True)
        
        # 基本資訊
        info_text = f"""操作 ID: {op.get('id', 'N/A')}
時間: {op.get('timestamp', 'N/A')}
類型: {op.get('type', 'N/A')}
狀態: {op.get('status', 'N/A')}

移動項目:
"""
        
        ttk.Label(frame, text=info_text, justify="left").pack(anchor="w")
        
        # 項目列表
        items_frame = ttk.Frame(frame)
        items_frame.pack(fill="both", expand=True, pady=(5, 10))
        
        items_text = tk.Text(items_frame, wrap="word", height=15)
        scrollbar = ttk.Scrollbar(items_frame, orient="vertical", command=items_text.yview)
        items_text.configure(yscrollcommand=scrollbar.set)
        
        items_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 填充項目
        for item in op.get("items", []):
            src = item.get("source", "")
            dst = item.get("destination", "")
            items_text.insert("end", f"• {src}\n  → {dst}\n\n")
        
        items_text.config(state="disabled")
        
        # 關閉按鈕
        ttk.Button(
            frame,
            text="關閉",
            command=detail_dialog.destroy,
            width=10
        ).pack(side="right")
    
    def _rollback_selected(self):
        """回滾選中的操作"""
        op = self._get_selected_operation()
        if not op:
            messagebox.showinfo("提示", "請先選擇一個操作", parent=self.dialog)
            return
        
        op_id = op.get("id", "")
        items_count = len(op.get("items", []))
        
        # 確認
        if not messagebox.askyesno(
            "確認回滾",
            f"確定要回滾此操作嗎？\n\n"
            f"操作 ID: {op_id[:12]}...\n"
            f"項目數: {items_count}\n\n"
            f"回滾後，所有已移動的檔案將被移回原位置。",
            parent=self.dialog
        ):
            return
        
        # 執行回滾
        try:
            result = self.file_mover.rollback(op_id)
            
            if result.get("success"):
                rolled_back = result.get("rolled_back", 0)
                messagebox.showinfo(
                    "回滾成功",
                    f"已成功回滾 {rolled_back} 個項目。",
                    parent=self.dialog
                )
                # 重新載入歷史
                self._load_history()
            else:
                error = result.get("error", "未知錯誤")
                messagebox.showerror(
                    "回滾失敗",
                    f"回滾操作失敗：\n{error}",
                    parent=self.dialog
                )
                
        except Exception as e:
            logger.error(f"回滾操作失敗: {e}")
            messagebox.showerror(
                "錯誤",
                f"回滾時發生錯誤：\n{e}",
                parent=self.dialog
            )


def show_operation_history(parent: tk.Tk, file_mover) -> None:
    """
    顯示操作歷史對話框的便捷函式
    
    Args:
        parent: 父視窗
        file_mover: FileMover 實例
    """
    dialog = OperationHistoryDialog(parent, file_mover)
    dialog.show()
