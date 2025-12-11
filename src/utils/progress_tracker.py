# -*- coding: utf-8 -*-
"""
進度追蹤模組
提供搜尋進度追蹤、時間預估與格式化輸出
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Any


@dataclass
class SearchProgressInfo:
    """搜尋進度資訊類別"""
    
    # 基本進度
    current: int = 0
    total: int = 0
    current_code: str = ""
    
    # 統計資訊
    success: int = 0
    failed: int = 0
    
    # 時間追蹤
    start_time: float = field(default_factory=time.time)
    
    # 級聯搜尋資訊
    current_source: str = "AV-WIKI"
    current_phase: int = 1
    total_phases: int = 1
    phase_name: str = ""
    
    # 來源統計
    source_stats: Dict[str, int] = field(default_factory=dict)
    
    # 執行緒安全鎖
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def reset(self, total: int = 0):
        """重置進度"""
        with self._lock:
            self.current = 0
            self.total = total
            self.current_code = ""
            self.success = 0
            self.failed = 0
            self.start_time = time.time()
            self.current_source = "AV-WIKI"
            self.current_phase = 1
            self.total_phases = 1
            self.phase_name = ""
            self.source_stats = {}
    
    def update(
        self, 
        code: str = None, 
        is_success: bool = None, 
        source: str = None,
        increment: bool = True
    ):
        """
        更新進度
        
        Args:
            code: 當前處理的番號
            is_success: 是否成功
            source: 搜尋來源
            increment: 是否增加計數
        """
        with self._lock:
            if increment:
                self.current += 1
            
            if code:
                self.current_code = code
            
            if source:
                self.current_source = source
            
            if is_success is not None:
                if is_success:
                    self.success += 1
                    # 更新來源統計
                    src = source or self.current_source
                    if src not in self.source_stats:
                        self.source_stats[src] = 0
                    self.source_stats[src] += 1
                else:
                    self.failed += 1
    
    def set_phase(self, phase: int, name: str, total_phases: int = None):
        """設定當前階段"""
        with self._lock:
            self.current_phase = phase
            self.phase_name = name
            if total_phases:
                self.total_phases = total_phases
    
    @property
    def elapsed_seconds(self) -> float:
        """已經過的時間（秒）"""
        return time.time() - self.start_time
    
    @property
    def items_per_second(self) -> float:
        """每秒處理數量"""
        elapsed = self.elapsed_seconds
        if elapsed == 0 or self.current == 0:
            return 0.0
        return self.current / elapsed
    
    @property
    def estimated_remaining_seconds(self) -> float:
        """預估剩餘時間（秒）"""
        speed = self.items_per_second
        if speed == 0:
            return 0.0
        remaining_items = self.total - self.current
        return remaining_items / speed
    
    @property
    def success_rate(self) -> float:
        """成功率（0-100）"""
        processed = self.success + self.failed
        if processed == 0:
            return 0.0
        return (self.success / processed) * 100
    
    @property
    def completion_rate(self) -> float:
        """完成進度（0-100）"""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100
    
    def format_time(self, seconds: float) -> str:
        """格式化時間顯示"""
        if seconds <= 0:
            return "--"
        elif seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}:{mins:02d}:00"
    
    def format_progress(self) -> str:
        """
        格式化進度顯示
        
        範例輸出：
        [15/51] 搜尋 STARS-707 | ✅ 12 ❌ 3 (80.0%) | ⏱️ 剩餘 2:30 | 🚀 5.2/s | 📡 AV-WIKI
        """
        parts = [
            f"[{self.current}/{self.total}]",
            f"搜尋 {self.current_code}",
        ]
        
        # 成功率（只有在開始處理後才顯示）
        if self.current > 0:
            parts.append(f"| ✅ {self.success} ❌ {self.failed} ({self.success_rate:.1f}%)")
        
        # 剩餘時間
        remaining = self.estimated_remaining_seconds
        parts.append(f"| ⏱️ 剩餘 {self.format_time(remaining)}")
        
        # 速度
        speed = self.items_per_second
        if speed > 0:
            parts.append(f"| 🚀 {speed:.1f}/s")
        
        # 來源
        if self.current_source:
            parts.append(f"| 📡 {self.current_source}")
        
        return " ".join(parts)
    
    def format_summary(self) -> str:
        """
        格式化完成摘要
        
        範例輸出：
        ============================================================
        📊 搜尋完成摘要
        
          ⏱️ 總耗時: 3:45
          📁 總番號: 51
          ✅ 成功: 47 (92.2%)
          ❌ 失敗: 4 (7.8%)
        
          📡 各來源貢獻:
             • AV-WIKI: 39 個 (83.0%)
             • chiba-f: 5 個 (10.6%)
             • JAVDB: 3 個 (6.4%)
        
          🚀 平均速度: 0.23 個/秒
        ============================================================
        """
        total_processed = self.success + self.failed
        
        lines = [
            "=" * 60,
            "📊 搜尋完成摘要",
            "",
            f"  ⏱️ 總耗時: {self.format_time(self.elapsed_seconds)}",
            f"  📁 總番號: {self.total}",
        ]
        
        if total_processed > 0:
            success_pct = (self.success / total_processed) * 100
            fail_pct = (self.failed / total_processed) * 100
            lines.append(f"  ✅ 成功: {self.success} ({success_pct:.1f}%)")
            lines.append(f"  ❌ 失敗: {self.failed} ({fail_pct:.1f}%)")
        
        # 來源統計
        if self.source_stats:
            lines.append("")
            lines.append("  📡 各來源貢獻:")
            total_success = sum(self.source_stats.values())
            for source, count in sorted(self.source_stats.items(), key=lambda x: -x[1]):
                pct = (count / total_success * 100) if total_success > 0 else 0
                lines.append(f"     • {source}: {count} 個 ({pct:.1f}%)")
        
        # 速度
        lines.append("")
        lines.append(f"  🚀 平均速度: {self.items_per_second:.2f} 個/秒")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'current': self.current,
            'total': self.total,
            'current_code': self.current_code,
            'success': self.success,
            'failed': self.failed,
            'elapsed_seconds': self.elapsed_seconds,
            'items_per_second': self.items_per_second,
            'estimated_remaining_seconds': self.estimated_remaining_seconds,
            'success_rate': self.success_rate,
            'current_source': self.current_source,
            'source_stats': dict(self.source_stats),
        }


class ProgressThrottler:
    """
    進度更新節流器
    避免過於頻繁的 GUI 更新導致卡頓
    """
    
    def __init__(self, min_interval_ms: int = 100):
        """
        初始化節流器
        
        Args:
            min_interval_ms: 最小更新間隔（毫秒）
        """
        self.min_interval = min_interval_ms / 1000
        self.last_update = 0.0
        self.pending_message: Optional[str] = None
        self.lock = threading.Lock()
    
    def should_update(self, message: str, force: bool = False) -> bool:
        """
        檢查是否應該更新
        
        Args:
            message: 進度訊息
            force: 是否強制更新（用於重要訊息）
            
        Returns:
            是否應該更新
        """
        current_time = time.time()
        
        with self.lock:
            if force or (current_time - self.last_update) >= self.min_interval:
                self.last_update = current_time
                self.pending_message = None
                return True
            else:
                self.pending_message = message
                return False
    
    def is_important(self, message: str) -> bool:
        """檢查是否為重要訊息"""
        important_keywords = ['完成', '錯誤', '開始', '====', '階段', '失敗', '成功', '摘要']
        return any(keyword in message for keyword in important_keywords)
    
    def flush(self) -> Optional[str]:
        """取得待處理的訊息（如果有）"""
        with self.lock:
            msg = self.pending_message
            self.pending_message = None
            return msg


class LoadingIndicator:
    """
    載入指示器
    在狀態列顯示旋轉動畫
    """
    
    FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    
    def __init__(self, update_callback, base_text: str = "處理中"):
        """
        初始化載入指示器
        
        Args:
            update_callback: 更新回呼函式，接受一個字串參數
            base_text: 基本文字
        """
        self.update_callback = update_callback
        self.base_text = base_text
        self.running = False
        self.frame_index = 0
        self._timer = None
    
    def start(self, text: str = None):
        """開始動畫"""
        self.base_text = text or self.base_text
        self.running = True
        self.frame_index = 0
        self._animate()
    
    def stop(self, final_text: str = "就緒"):
        """停止動畫"""
        self.running = False
        if self._timer:
            try:
                self._timer.cancel()
            except:
                pass
        self.update_callback(final_text)
    
    def update_text(self, text: str):
        """更新基本文字"""
        self.base_text = text
    
    def _animate(self):
        """動畫循環"""
        if self.running:
            frame = self.FRAMES[self.frame_index % len(self.FRAMES)]
            self.update_callback(f"{frame} {self.base_text}")
            self.frame_index += 1
            
            # 使用 threading.Timer 來避免阻塞
            self._timer = threading.Timer(0.1, self._animate)
            self._timer.daemon = True
            self._timer.start()


# 匯出的搜尋結果資料結構
@dataclass
class CascadeSearchResult:
    """級聯搜尋結果"""
    code: str
    actresses: list
    source: str = ""              # 最終成功的來源
    tried_sources: list = field(default_factory=list)  # 嘗試過的來源
    studio: str = ""
    status: str = "not_found"     # 'success', 'failed', 'not_found'
    search_time_ms: float = 0.0
    
    @property
    def is_success(self) -> bool:
        """是否搜尋成功"""
        return bool(self.actresses)


@dataclass
class CascadeSearchSummary:
    """級聯搜尋總結"""
    total: int = 0
    success: int = 0
    failed: int = 0
    by_source: Dict[str, int] = field(default_factory=dict)
    failed_codes: list = field(default_factory=list)
    elapsed_seconds: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率（0-100）"""
        if self.total == 0:
            return 0.0
        return (self.success / self.total) * 100
