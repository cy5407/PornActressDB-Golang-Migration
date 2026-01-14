#!/usr/bin/env python3
"""
批次修正 tools/ 目錄下所有腳本的 sys.path.insert 操作

執行方式：python tools/fix_sys_path.py
"""

import re
import sys
from pathlib import Path

# 設定專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def get_parent_depth(file_path: Path, project_root: Path) -> int:
    """計算從檔案到專案根目錄需要幾層 .parent"""
    relative = file_path.relative_to(project_root)
    return len(relative.parents)


def fix_sys_path_in_file(file_path: Path, project_root: Path, dry_run: bool = True):
    """修正單一檔案的 sys.path 操作"""

    content = file_path.read_text(encoding="utf-8")
    original_content = content

    # 計算需要的 .parent 層數
    depth = get_parent_depth(file_path, project_root)
    parent_chain = ".parent" * depth

    # 模式 1: sys.path.insert(0, str(project_root / "src"))
    pattern1 = r'project_root = Path\(__file__\)\.parent.*?\nsys\.path\.insert\(0, str\(project_root / "src"\)\)'
    replacement1 = f'# 設定專案路徑\nsys.path.insert(0, str(Path(__file__){parent_chain} / "src"))'

    if re.search(pattern1, content, re.DOTALL):
        content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)

    # 模式 2: sys.path.insert(0, "src")
    pattern2 = r'sys\.path\.insert\(0, "src"\)'
    replacement2 = f'sys.path.insert(0, str(Path(__file__){parent_chain} / "src"))'

    if re.search(pattern2, content):
        content = re.sub(pattern2, replacement2, content)
        # 確保有匯入 Path
        if "from pathlib import Path" not in content:
            content = re.sub(
                r'(import sys\n)',
                r'\1from pathlib import Path\n',
                content
            )

    # 模式 4: sys.path.insert(0, str(Path(__file__).parent / "src"))
    # 這是錯誤的模式，在 tools/subdir/ 中只回到 tools/ 層級
    pattern4 = r'sys\.path\.insert\(0, str\(Path\(__file__\)\.parent / "src"\)\)'
    replacement4 = f'sys.path.insert(0, str(Path(__file__){parent_chain} / "src"))'

    if re.search(pattern4, content):
        content = re.sub(pattern4, replacement4, content)

    # 模式 5: 分兩行的版本
    # src_path = Path(__file__).parent / "src"
    # sys.path.insert(0, str(src_path))
    pattern5 = r'src_path = Path\(__file__\)\.parent / "src"\nsys\.path\.insert\(0, str\(src_path\)\)'
    replacement5 = f'# 設定專案路徑\nsys.path.insert(0, str(Path(__file__){parent_chain} / "src"))'

    if re.search(pattern5, content):
        content = re.sub(pattern5, replacement5, content)

    # 模式 3: 多個 sys.path.insert (如 verify 腳本)
    pattern3 = r'src_path = Path\(__file__\)\.parent / "src"\nsys\.path\.insert\(0, str\(src_path\)\)\nsys\.path\.insert\(0, str\(Path\(__file__\)\.parent\)\)'
    replacement3 = f'# 設定專案路徑\nsys.path.insert(0, str(Path(__file__){parent_chain} / "src"))'

    if re.search(pattern3, content):
        content = re.sub(pattern3, replacement3, content)

    # 檢查是否有變更
    if content != original_content:
        if dry_run:
            print(f"[需修正] {file_path.relative_to(project_root)}")
            print(f"   深度: {depth} (.parent x {depth})")
            return True
        else:
            file_path.write_text(content, encoding="utf-8")
            print(f"[已修正] {file_path.relative_to(project_root)}")
            return True
    else:
        if dry_run:
            print(f"[跳過] {file_path.relative_to(project_root)}")
        return False


def main():
    """主程式"""
    project_root = Path(__file__).parent.parent
    tools_dir = project_root / "tools"

    # 找出所有包含 sys.path.insert 的 Python 檔案
    files_to_fix = []

    for py_file in tools_dir.rglob("*.py"):
        # 跳過本腳本自己
        if py_file.name == "fix_sys_path.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            if "sys.path.insert" in content:
                files_to_fix.append(py_file)
        except Exception as e:
            print(f"[錯誤] 讀取失敗: {py_file}, 錯誤: {e}")

    print(f"找到 {len(files_to_fix)} 個需要檢查的檔案\n")

    # Dry-run 模式
    print("=" * 60)
    print("第一階段：預覽模式 (Dry-run)")
    print("=" * 60)

    changed_count = 0
    for file_path in files_to_fix:
        if fix_sys_path_in_file(file_path, project_root, dry_run=True):
            changed_count += 1

    print(f"\n統計：{changed_count}/{len(files_to_fix)} 個檔案需要修正\n")

    # 詢問是否執行
    response = input("是否執行修正？(y/n): ")
    if response.lower() != "y":
        print("已取消")
        return

    print("\n" + "=" * 60)
    print("第二階段：執行修正")
    print("=" * 60)

    success_count = 0
    for file_path in files_to_fix:
        try:
            if fix_sys_path_in_file(file_path, project_root, dry_run=False):
                success_count += 1
        except Exception as e:
            print(f"[錯誤] 修正失敗: {file_path}, 錯誤: {e}")

    print(f"\n完成！成功修正 {success_count} 個檔案")


if __name__ == "__main__":
    main()
