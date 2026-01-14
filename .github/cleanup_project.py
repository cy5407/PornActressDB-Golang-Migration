"""
專案清理腳本 - 移動未使用的檔案到 _to_delete 資料夾
根據 CLEANUP_PLAN.md 自動執行清理操作
"""
import shutil
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class ProjectCleaner:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.to_delete_dir = project_root / "_to_delete"
        self.moved_items = []
        self.errors = []
        
    def create_cleanup_dirs(self):
        """建立清理用的目錄結構"""
        dirs = [
            self.to_delete_dir / "analysis_tools",
            self.to_delete_dir / "diagnostic_tools",
            self.to_delete_dir / "manual_tests",
            self.to_delete_dir / "temp_files",
            self.to_delete_dir / "old_backups",
            self.to_delete_dir / "failed_tests",
            self.to_delete_dir / "outdated_docs",
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ 建立目錄: {dir_path.relative_to(self.project_root)}")
            
    def move_safely(self, source: Path, dest_category: str, reason: str = "") -> bool:
        """安全地移動檔案或目錄"""
        if not source.exists():
            logger.warning(f"⚠️  來源不存在: {source}")
            return False
            
        dest_dir = self.to_delete_dir / dest_category
        dest_path = dest_dir / source.name
        
        try:
            if dest_path.exists():
                # 如果目標已存在，加上時間戳
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_path = dest_dir / f"{source.stem}_{timestamp}{source.suffix}"
                
            shutil.move(str(source), str(dest_path))
            
            self.moved_items.append({
                'source': str(source.relative_to(self.project_root)),
                'dest': str(dest_path.relative_to(self.project_root)),
                'reason': reason,
                'type': 'dir' if source.is_dir() else 'file',
                'size': self._get_size(source) if source.is_file() else self._get_dir_size(dest_path)
            })
            
            logger.info(f"✅ 已移動: {source.relative_to(self.project_root)} → {dest_category}/")
            if reason:
                logger.info(f"   原因: {reason}")
            return True
            
        except Exception as e:
            error_msg = f"移動 {source} 時發生錯誤: {e}"
            self.errors.append(error_msg)
            logger.error(f"❌ {error_msg}")
            return False
            
    def _get_size(self, file_path: Path) -> int:
        """取得檔案大小（bytes）"""
        try:
            return file_path.stat().st_size
        except:
            return 0
            
    def _get_dir_size(self, dir_path: Path) -> int:
        """取得目錄總大小"""
        total = 0
        try:
            for item in dir_path.rglob('*'):
                if item.is_file():
                    total += item.stat().st_size
        except:
            pass
        return total
        
    def phase1_safe_cleanup(self):
        """Phase 1: 安全清理（不影響主程式）"""
        logger.info("\n" + "=" * 70)
        logger.info("📦 Phase 1: 安全清理開發工具與臨時檔案")
        logger.info("=" * 70 + "\n")
        
        items_to_move = [
            # 分析工具
            (self.project_root / "tools" / "analysis", "analysis_tools", "開發過程中的分析工具"),
            
            # 診斷工具
            (self.project_root / "tools" / "diagnostics", "diagnostic_tools", "診斷與除錯工具"),
            (self.project_root / "tools" / "verify", "diagnostic_tools", "驗證工具"),
            
            # 手動測試
            (self.project_root / "tools" / "manual_tests", "manual_tests", "手動測試腳本"),
            
            # 臨時檔案
            (self.project_root / "temp_benchmark", "temp_files", "基準測試臨時檔案"),
            (self.project_root / "my-test-project", "temp_files", "測試專案"),
            
            # 舊備份
            (self.project_root / "backups" / "scripts", "old_backups", "舊的腳本備份"),
            (self.project_root / "backups" / "data_backup_20251017_150802.json", "old_backups", "舊資料備份"),
            (self.project_root / "backups" / "data.json", "old_backups", "舊資料檔案"),
            (self.project_root / "backups" / "cache", "old_backups", "舊快取"),
            (self.project_root / "backups" / "logs", "old_backups", "舊日誌"),
            
            # 過時文件
            (self.project_root / "docs" / "archives", "outdated_docs", "文件檔案庫"),
            
            # 分析報告（已產生）
            (self.project_root / "code_usage_analysis.txt", "temp_files", "程式碼使用分析報告"),
        ]
        
        moved_count = 0
        for source, category, reason in items_to_move:
            if self.move_safely(source, category, reason):
                moved_count += 1
                
        logger.info(f"\n✅ Phase 1 完成：已移動 {moved_count} 項")
        
    def generate_report(self):
        """生成清理報告"""
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("📋 專案清理報告")
        report_lines.append("=" * 70)
        report_lines.append(f"📅 執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"📊 總移動項目數: {len(self.moved_items)}")
        
        # 計算總大小
        total_size = sum(item['size'] for item in self.moved_items)
        total_mb = total_size / (1024 * 1024)
        report_lines.append(f"💾 總移動大小: {total_mb:.2f} MB")
        report_lines.append("")
        
        # 按類別分組
        by_category = {}
        for item in self.moved_items:
            parts = item['dest'].replace('\\', '/').split('/')
            category = parts[1] if len(parts) > 1 else 'other'
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(item)
            
        for category, items in sorted(by_category.items()):
            report_lines.append(f"\n{'=' * 70}")
            report_lines.append(f"📁 {category.replace('_', ' ').title()} ({len(items)} 項)")
            report_lines.append("=" * 70)
            
            for item in items:
                size_kb = item['size'] / 1024
                type_icon = "📂" if item['type'] == 'dir' else "📄"
                report_lines.append(f"  {type_icon} {item['source']}")
                report_lines.append(f"      → {item['dest']} ({size_kb:.1f} KB)")
                if item['reason']:
                    report_lines.append(f"      原因: {item['reason']}")
                report_lines.append("")
                
        # 錯誤報告
        if self.errors:
            report_lines.append(f"\n{'=' * 70}")
            report_lines.append(f"❌ 錯誤 ({len(self.errors)} 項)")
            report_lines.append("=" * 70)
            for error in self.errors:
                report_lines.append(f"  • {error}")
            report_lines.append("")
            
        report_lines.append("=" * 70)
        report_lines.append("✅ 清理完成")
        report_lines.append("")
        report_lines.append("⚠️  注意事項：")
        report_lines.append("  1. 請檢查主程式是否正常運作")
        report_lines.append("  2. 執行測試確認功能完整")
        report_lines.append("  3. 確認無誤後可手動刪除 _to_delete 資料夾")
        report_lines.append("  4. 建議先備份後再刪除")
        report_lines.append("")
        report_lines.append("🧪 驗證指令：")
        report_lines.append("  python .github\\agent_verify.py")
        report_lines.append("  python run.py --test-mode")
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
        
    def save_report(self, report: str):
        """儲存報告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.to_delete_dir / f"CLEANUP_REPORT_{timestamp}.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
            
        logger.info(f"\n💾 報告已儲存: {report_file.relative_to(self.project_root)}")
        
    def run(self):
        """執行完整清理"""
        logger.info("\n" + "=" * 70)
        logger.info("🧹 開始專案清理")
        logger.info("=" * 70)
        
        # 建立目錄
        self.create_cleanup_dirs()
        
        # Phase 1: 安全清理
        self.phase1_safe_cleanup()
        
        # 生成報告
        report = self.generate_report()
        print("\n" + report)
        self.save_report(report)
        
        return len(self.moved_items) > 0


def main():
    project_root = Path(__file__).parent.parent
    cleaner = ProjectCleaner(project_root)
    
    # 執行清理
    success = cleaner.run()
    
    if success:
        logger.info("\n" + "=" * 70)
        logger.info("✅ 清理完成！")
        logger.info("=" * 70)
        logger.info("\n📋 後續步驟：")
        logger.info("  1. 執行驗證：python .github\\agent_verify.py")
        logger.info("  2. 測試主程式：python run.py")
        logger.info("  3. 確認無誤後可刪除 _to_delete 資料夾")
        logger.info("")
    else:
        logger.warning("\n⚠️  沒有檔案被移動")


if __name__ == "__main__":
    main()
