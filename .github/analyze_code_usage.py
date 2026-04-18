"""
程式碼使用情況分析工具
分析專案中哪些檔案未被使用，應該移到待刪除資料夾
"""
import ast
import logging
from pathlib import Path
from typing import Set, Dict, List
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class CodeUsageAnalyzer:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.src_dir = project_root / "src"
        self.tools_dir = project_root / "tools"
        self.tests_dir = project_root / "tests"
        
        # 記錄所有檔案
        self.all_files: Set[Path] = set()
        # 記錄被匯入的檔案
        self.imported_files: Set[Path] = set()
        # 記錄匯入關係
        self.import_graph: Dict[Path, Set[Path]] = defaultdict(set)
        
    def collect_all_python_files(self) -> None:
        """收集所有 Python 檔案"""
        for directory in [self.src_dir, self.tools_dir, self.tests_dir]:
            if directory.exists():
                for py_file in directory.rglob("*.py"):
                    if "__pycache__" not in str(py_file):
                        self.all_files.add(py_file)
        
        # 加入主程式
        run_py = self.project_root / "run.py"
        if run_py.exists():
            self.all_files.add(run_py)
            
        logger.info(f"📊 找到 {len(self.all_files)} 個 Python 檔案")
        
    def parse_imports(self, file_path: Path) -> Set[str]:
        """解析檔案中的 import 語句"""
        imports = set()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content, filename=str(file_path))
                
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split('.')[0])
        except Exception as e:
            logger.debug(f"⚠️ 無法解析 {file_path.name}: {e}")
            
        return imports
        
    def module_name_to_path(self, module_name: str) -> Path | None:
        """將模組名稱轉換為檔案路徑"""
        # 處理 src 下的模組
        if module_name in ['models', 'services', 'scrapers', 'ui', 'utils']:
            mod_dir = self.src_dir / module_name
            init_file = mod_dir / "__init__.py"
            if init_file.exists():
                return init_file
                
        # 處理具體檔案
        for directory in [self.src_dir / 'models', self.src_dir / 'services', 
                         self.src_dir / 'scrapers', self.src_dir / 'ui', 
                         self.src_dir / 'utils']:
            if directory.exists():
                py_file = directory / f"{module_name}.py"
                if py_file.exists():
                    return py_file
                    
        return None
        
    def analyze_usage(self) -> None:
        """分析所有檔案的使用情況"""
        logger.info("\n🔍 分析檔案使用情況...")
        
        for file_path in self.all_files:
            imports = self.parse_imports(file_path)
            
            for imp in imports:
                imported_path = self.module_name_to_path(imp)
                if imported_path and imported_path in self.all_files:
                    self.imported_files.add(imported_path)
                    self.import_graph[file_path].add(imported_path)
                    
    def find_entry_points(self) -> Set[Path]:
        """找出主要進入點"""
        entry_points = set()
        
        # 主程式
        run_py = self.project_root / "run.py"
        if run_py.exists():
            entry_points.add(run_py)
            
        # 測試檔案
        for test_file in self.tests_dir.rglob("test_*.py"):
            entry_points.add(test_file)
            
        # CLI 工具
        for tool_file in self.tools_dir.rglob("*.py"):
            if tool_file.name not in ['__init__.py']:
                entry_points.add(tool_file)
                
        logger.info(f"📍 找到 {len(entry_points)} 個進入點")
        return entry_points
        
    def trace_dependencies(self, entry_point: Path, visited: Set[Path] = None) -> Set[Path]:
        """追蹤檔案的依賴關係"""
        if visited is None:
            visited = set()
            
        if entry_point in visited or entry_point not in self.all_files:
            return visited
            
        visited.add(entry_point)
        
        # 遞迴追蹤依賴
        for dep in self.import_graph.get(entry_point, set()):
            self.trace_dependencies(dep, visited)
            
        return visited
        
    def find_unused_files(self) -> Dict[str, List[Path]]:
        """找出未使用的檔案"""
        logger.info("\n🎯 追蹤依賴關係...")
        
        entry_points = self.find_entry_points()
        used_files = set()
        
        for entry in entry_points:
            deps = self.trace_dependencies(entry)
            used_files.update(deps)
            
        unused = self.all_files - used_files
        
        # 分類未使用的檔案
        categorized = {
            'src': [],
            'tests': [],
            'tools': [],
            'other': []
        }
        
        for file_path in unused:
            # 排除 __init__.py 和測試檔案（可能用於手動執行）
            if file_path.name == '__init__.py':
                continue
                
            if 'src' in file_path.parts:
                categorized['src'].append(file_path)
            elif 'tests' in file_path.parts:
                categorized['tests'].append(file_path)
            elif 'tools' in file_path.parts:
                categorized['tools'].append(file_path)
            else:
                categorized['other'].append(file_path)
                
        return categorized
        
    def generate_report(self, unused: Dict[str, List[Path]]) -> str:
        """生成分析報告"""
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("📋 程式碼使用情況分析報告")
        report_lines.append("=" * 70)
        report_lines.append("")
        report_lines.append(f"📊 總檔案數: {len(self.all_files)}")
        
        total_unused = sum(len(files) for files in unused.values())
        report_lines.append(f"❌ 未使用檔案數: {total_unused}")
        report_lines.append(f"✅ 使用中檔案數: {len(self.all_files) - total_unused}")
        report_lines.append("")
        
        for category, files in unused.items():
            if files:
                report_lines.append(f"\n{'=' * 70}")
                report_lines.append(f"📁 {category.upper()} 目錄未使用檔案 ({len(files)} 個)")
                report_lines.append("=" * 70)
                
                for file_path in sorted(files):
                    rel_path = file_path.relative_to(self.project_root)
                    size_kb = file_path.stat().st_size / 1024
                    report_lines.append(f"  ❌ {rel_path} ({size_kb:.1f} KB)")
                    
                    # 檢查是否有任何檔案匯入它
                    imported_by = []
                    for src, deps in self.import_graph.items():
                        if file_path in deps:
                            imported_by.append(src.name)
                    
                    if imported_by:
                        report_lines.append(f"      ⚠️  被引用但未追蹤: {', '.join(imported_by[:3])}")
                        
        report_lines.append("")
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
        
    def run(self) -> Dict[str, List[Path]]:
        """執行完整分析"""
        self.collect_all_python_files()
        self.analyze_usage()
        unused = self.find_unused_files()
        
        report = self.generate_report(unused)
        print(report)
        
        # 儲存報告
        report_file = self.project_root / "code_usage_analysis.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"\n💾 報告已儲存至: {report_file}")
        
        return unused


def main():
    project_root = Path(__file__).parent.parent
    analyzer = CodeUsageAnalyzer(project_root)
    unused_files = analyzer.run()
    
    # 詢問是否移動檔案
    print("\n" + "=" * 70)
    total_unused = sum(len(files) for files in unused_files.values())
    print(f"發現 {total_unused} 個未使用的檔案")
    print("=" * 70)
    
    return unused_files


if __name__ == "__main__":
    main()
