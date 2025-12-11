# -*- coding: utf-8 -*-
"""
搜尋結果預覽對話框
提供搜尋結果的表格顯示、排序、匯出功能
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SearchResultItem:
    """搜尋結果項目"""
    code: str
    actresses: List[str]
    source: str
    status: str  # 'success', 'failed', 'not_found'
    studio: str = ""
    tried_sources: List[str] = None
    
    def __post_init__(self):
        if self.tried_sources is None:
            self.tried_sources = []
    
    @property
    def is_success(self) -> bool:
        return self.status == 'success' and len(self.actresses) > 0


class SearchResultDialog:
    """搜尋結果預覽對話框"""
    
    def __init__(
        self, 
        parent: tk.Tk, 
        results: Dict[str, SearchResultItem], 
        title: str = "🔍 搜尋結果預覽"
    ):
        self.parent = parent
        self.results = results
        self.title = title
        self.sort_reverse = {}  # 記錄每個欄位的排序方向
        
        # 建立對話框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("900x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()  # 模態對話框
        
        # 居中顯示
        self._center_window()
        
        self._setup_ui()
        self._populate_data()
        
        # 綁定關閉事件
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _center_window(self):
        """將視窗置中"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f'+{x}+{y}')
    
    def _setup_ui(self):
        """建立 UI 元件"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 標題區
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            header_frame, 
            text="🔍 搜尋結果預覽", 
            font=("Microsoft JhengHei", 14, "bold")
        ).pack(side="left")
        
        # 統計資訊
        success_count = sum(1 for r in self.results.values() if r.is_success)
        total_count = len(self.results)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        
        stats_text = f"✅ {success_count} / {total_count} ({success_rate:.1f}%)"
        ttk.Label(
            header_frame,
            text=stats_text,
            font=("Microsoft JhengHei", 12)
        ).pack(side="right")
        
        # 篩選區
        filter_frame = ttk.Frame(main_frame)
        filter_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(filter_frame, text="篩選:").pack(side="left", padx=(0, 5))
        
        self.filter_var = tk.StringVar(value="all")
        filters = [
            ("全部", "all"),
            ("成功", "success"),
            ("失敗", "failed"),
        ]
        for text, value in filters:
            ttk.Radiobutton(
                filter_frame, 
                text=text, 
                variable=self.filter_var, 
                value=value,
                command=self._apply_filter
            ).pack(side="left", padx=5)
        
        # 搜尋框
        ttk.Label(filter_frame, text="  搜尋:").pack(side="left", padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self._apply_filter())
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side="left")
        
        # 表格區
        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill="both", expand=True, pady=5)
        
        # 建立 Treeview
        columns = ("code", "actresses", "source", "studio", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        
        # 設定欄位標題（可點擊排序）
        column_config = [
            ("code", "番號", 100),
            ("actresses", "女優", 300),
            ("source", "來源", 100),
            ("studio", "片商", 120),
            ("status", "狀態", 80),
        ]
        
        for col_id, col_text, col_width in column_config:
            self.tree.heading(
                col_id, 
                text=f"{col_text} ▼", 
                command=lambda c=col_id: self._sort_by(c)
            )
            self.tree.column(col_id, width=col_width, minwidth=50)
            self.sort_reverse[col_id] = False
        
        # 垂直捲軸
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scrollbar.set)
        
        # 水平捲軸
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=h_scrollbar.set)
        
        # 放置元件
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        # 雙擊查看詳細
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # 按鈕區
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(
            button_frame, 
            text="📥 匯出 CSV", 
            command=self._export_csv
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, 
            text="📋 複製失敗番號", 
            command=self._copy_failed
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, 
            text="📋 複製成功番號", 
            command=self._copy_success
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, 
            text="📋 複製選取項目", 
            command=self._copy_selected
        ).pack(side="left", padx=5)
        
        ttk.Button(
            button_frame, 
            text="關閉", 
            command=self._on_close
        ).pack(side="right", padx=5)
        
        # 狀態列
        self.status_var = tk.StringVar(value=f"共 {total_count} 筆結果")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill="x", pady=(5, 0))
    
    def _populate_data(self):
        """填充資料"""
        for code, result in self.results.items():
            self._insert_item(code, result)
    
    def _insert_item(self, code: str, result: SearchResultItem) -> str:
        """插入單一項目，返回 item id"""
        # 格式化女優列表
        if result.actresses:
            if len(result.actresses) > 3:
                actresses_str = ", ".join(result.actresses[:3]) + f" (+{len(result.actresses)-3})"
            else:
                actresses_str = ", ".join(result.actresses)
        else:
            actresses_str = "❌ 未找到"
        
        # 狀態顯示
        status_map = {
            'success': '✅ 成功',
            'failed': '❌ 失敗',
            'not_found': '⚠️ 無資料'
        }
        status_display = status_map.get(result.status, result.status)
        
        # 標籤（用於樣式）
        tags = (result.status,)
        
        return self.tree.insert("", "end", values=(
            code,
            actresses_str,
            result.source or "-",
            result.studio or "-",
            status_display
        ), tags=tags)
    
    def _apply_filter(self):
        """套用篩選"""
        # 清空現有項目
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        filter_value = self.filter_var.get()
        search_text = self.search_var.get().lower()
        
        filtered_count = 0
        for code, result in self.results.items():
            # 狀態篩選
            if filter_value == "success" and not result.is_success:
                continue
            if filter_value == "failed" and result.is_success:
                continue
            
            # 搜尋篩選
            if search_text:
                searchable = f"{code} {' '.join(result.actresses)} {result.source} {result.studio}".lower()
                if search_text not in searchable:
                    continue
            
            self._insert_item(code, result)
            filtered_count += 1
        
        # 更新狀態列
        total = len(self.results)
        self.status_var.set(f"顯示 {filtered_count} / {total} 筆結果")
    
    def _sort_by(self, column: str):
        """按欄位排序"""
        # 切換排序方向
        self.sort_reverse[column] = not self.sort_reverse.get(column, False)
        reverse = self.sort_reverse[column]
        
        # 取得所有項目
        items = [(self.tree.set(item, column), item) for item in self.tree.get_children("")]
        
        # 排序
        items.sort(key=lambda x: x[0], reverse=reverse)
        
        # 重新排列
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)
        
        # 更新標題箭頭
        arrow = "▲" if reverse else "▼"
        column_config = {
            "code": "番號",
            "actresses": "女優",
            "source": "來源",
            "studio": "片商",
            "status": "狀態"
        }
        for col_id, col_text in column_config.items():
            if col_id == column:
                self.tree.heading(col_id, text=f"{col_text} {arrow}")
            else:
                self.tree.heading(col_id, text=col_text)
    
    def _on_double_click(self, event):
        """雙擊查看詳細"""
        item = self.tree.selection()
        if not item:
            return
        
        values = self.tree.item(item[0], "values")
        code = values[0]
        
        if code in self.results:
            result = self.results[code]
            self._show_detail_dialog(code, result)
    
    def _show_detail_dialog(self, code: str, result: SearchResultItem):
        """顯示詳細資訊對話框"""
        detail_window = tk.Toplevel(self.dialog)
        detail_window.title(f"詳細資訊 - {code}")
        detail_window.geometry("400x300")
        detail_window.transient(self.dialog)
        
        frame = ttk.Frame(detail_window, padding="15")
        frame.pack(fill="both", expand=True)
        
        # 番號
        ttk.Label(frame, text="番號:", font=("Microsoft JhengHei", 10, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(frame, text=code).grid(row=0, column=1, sticky="w", pady=2)
        
        # 狀態
        ttk.Label(frame, text="狀態:", font=("Microsoft JhengHei", 10, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        status_text = "✅ 成功" if result.is_success else "❌ 失敗"
        ttk.Label(frame, text=status_text).grid(row=1, column=1, sticky="w", pady=2)
        
        # 女優
        ttk.Label(frame, text="女優:", font=("Microsoft JhengHei", 10, "bold")).grid(row=2, column=0, sticky="nw", pady=2)
        actresses_text = "\n".join(result.actresses) if result.actresses else "未找到"
        actresses_label = ttk.Label(frame, text=actresses_text, wraplength=250)
        actresses_label.grid(row=2, column=1, sticky="w", pady=2)
        
        # 來源
        ttk.Label(frame, text="來源:", font=("Microsoft JhengHei", 10, "bold")).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(frame, text=result.source or "-").grid(row=3, column=1, sticky="w", pady=2)
        
        # 片商
        ttk.Label(frame, text="片商:", font=("Microsoft JhengHei", 10, "bold")).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(frame, text=result.studio or "-").grid(row=4, column=1, sticky="w", pady=2)
        
        # 嘗試的來源
        if result.tried_sources:
            ttk.Label(frame, text="嘗試來源:", font=("Microsoft JhengHei", 10, "bold")).grid(row=5, column=0, sticky="w", pady=2)
            ttk.Label(frame, text=" → ".join(result.tried_sources)).grid(row=5, column=1, sticky="w", pady=2)
        
        # 關閉按鈕
        ttk.Button(frame, text="關閉", command=detail_window.destroy).grid(row=6, column=0, columnspan=2, pady=15)
    
    def _export_csv(self):
        """匯出為 CSV"""
        filepath = filedialog.asksaveasfilename(
            parent=self.dialog,
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv"), ("所有檔案", "*.*")],
            title="匯出搜尋結果"
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["番號", "女優", "來源", "片商", "狀態", "嘗試來源"])
                
                for code, result in self.results.items():
                    writer.writerow([
                        code,
                        " # ".join(result.actresses) if result.actresses else "",
                        result.source or "",
                        result.studio or "",
                        result.status,
                        " → ".join(result.tried_sources) if result.tried_sources else ""
                    ])
            
            messagebox.showinfo("匯出成功", f"已匯出至:\n{filepath}", parent=self.dialog)
            logger.info(f"搜尋結果已匯出至: {filepath}")
            
        except Exception as e:
            messagebox.showerror("匯出失敗", f"匯出時發生錯誤:\n{e}", parent=self.dialog)
            logger.error(f"匯出 CSV 失敗: {e}")
    
    def _copy_failed(self):
        """複製失敗的番號到剪貼簿"""
        failed_codes = [code for code, r in self.results.items() if not r.is_success]
        self._copy_to_clipboard(failed_codes, "失敗")
    
    def _copy_success(self):
        """複製成功的番號到剪貼簿"""
        success_codes = [code for code, r in self.results.items() if r.is_success]
        self._copy_to_clipboard(success_codes, "成功")
    
    def _copy_selected(self):
        """複製選取的番號到剪貼簿"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "請先選取要複製的項目", parent=self.dialog)
            return
        
        codes = [self.tree.item(item, "values")[0] for item in selected]
        self._copy_to_clipboard(codes, "選取")
    
    def _copy_to_clipboard(self, codes: List[str], label: str):
        """複製到剪貼簿"""
        if codes:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append("\n".join(codes))
            messagebox.showinfo("已複製", f"已複製 {len(codes)} 個{label}番號到剪貼簿", parent=self.dialog)
        else:
            messagebox.showinfo("無資料", f"沒有{label}的番號", parent=self.dialog)
    
    def _on_close(self):
        """關閉對話框"""
        self.dialog.grab_release()
        self.dialog.destroy()


def show_search_results(parent: tk.Tk, results: Dict[str, Any], title: str = "搜尋結果預覽") -> None:
    """
    顯示搜尋結果預覽對話框的便利函式
    
    Args:
        parent: 父視窗
        results: 搜尋結果字典，格式為 {code: {actresses: [], source: str, status: str, studio: str}}
        title: 對話框標題
    """
    # 轉換結果格式
    search_results = {}
    for code, detail in results.items():
        if isinstance(detail, SearchResultItem):
            search_results[code] = detail
        elif isinstance(detail, dict):
            search_results[code] = SearchResultItem(
                code=code,
                actresses=detail.get('actresses', []),
                source=detail.get('source', ''),
                status='success' if detail.get('actresses') else 'not_found',
                studio=detail.get('studio', ''),
                tried_sources=detail.get('tried_sources', [])
            )
        else:
            logger.warning(f"無法處理結果格式: {type(detail)}")
    
    if search_results:
        SearchResultDialog(parent, search_results, title)
    else:
        messagebox.showinfo("無結果", "沒有搜尋結果可顯示", parent=parent)
