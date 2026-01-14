"""
修復被重新命名的檔案 - 移除括號內的女優標籤
只保留番號部分
"""

import re
from pathlib import Path


def extract_video_code(filename: str) -> str | None:
    """從檔名提取番號"""
    # 移除副檔名
    stem = Path(filename).stem
    
    # 常見番號格式
    patterns = [
        r"^(hhd800\.com@)?(\[?[A-Za-z0-9._-]+\]?[A-Z]{2,6}[-_]?\d{3,5}(?:[-_][A-Za-z0-9]+)?)",  # 帶前綴
        r"(\[?[HhH]\.?265\]?)?([A-Z]{2,6}[-_]?\d{3,5}(?:[-_][A-Za-z0-9]+)?)",  # 標準格式
        r"^(\d{3,6}[-_][A-Z]{2,6}[-_]?\d{2,5})",  # 數字開頭格式
        r"^(FC2[-_]?PPV[-_]?\d+(?:[-_]\d+)?)",  # FC2 格式
    ]
    
    for pattern in patterns:
        match = re.search(pattern, stem, re.IGNORECASE)
        if match:
            # 取得匹配的部分
            code = match.group(0)
            return code
    
    return None


def should_fix(filename: str) -> bool:
    """檢查檔名是否需要修復（包含括號標籤）"""
    stem = Path(filename).stem
    # 檢查是否有括號包圍的內容（女優標籤格式）
    # 但排除 [H.265] 這類編碼標記
    if re.search(r'\s+\([^)]+,\s*[^)]+\)', stem):
        return True
    # 單個括號也檢查（如果有日文）
    if re.search(r'\s+\([ぁ-んァ-ン一-龥]+[,、]', stem):
        return True
    return False


def get_clean_filename(filename: str) -> str:
    """取得清理後的檔名"""
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix
    
    # 移除括號標籤 (xxx, xxx, xxx) 格式
    # 可能有多組括號
    cleaned = re.sub(r'\s*\([^)]*[,、][^)]*\)', '', stem)
    
    # 清理多餘空白
    cleaned = cleaned.strip()
    
    return cleaned + suffix


def scan_and_preview(folder: str, recursive: bool = True) -> list[tuple[Path, str]]:
    """掃描並預覽需要修復的檔案"""
    folder_path = Path(folder)
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    to_fix = []
    
    if recursive:
        files = folder_path.rglob('*')
    else:
        files = folder_path.glob('*')
    
    for file_path in files:
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            if should_fix(file_path.name):
                new_name = get_clean_filename(file_path.name)
                to_fix.append((file_path, new_name))
    
    return to_fix


def fix_filenames(folder: str, recursive: bool = True, dry_run: bool = True) -> dict:
    """修復檔案名稱"""
    to_fix = scan_and_preview(folder, recursive)
    
    stats = {
        'total': len(to_fix),
        'success': 0,
        'failed': 0,
        'skipped': 0,
    }
    
    print(f"\n{'=' * 60}")
    print(f"{'[預覽模式]' if dry_run else '[執行模式]'} 找到 {len(to_fix)} 個需要修復的檔案")
    print(f"{'=' * 60}\n")
    
    for i, (file_path, new_name) in enumerate(to_fix, 1):
        new_path = file_path.parent / new_name
        
        print(f"[{i}/{len(to_fix)}]")
        print(f"  原檔名: {file_path.name}")
        print(f"  新檔名: {new_name}")
        
        if dry_run:
            print(f"  狀態: 預覽 (不會實際修改)\n")
            continue
        
        try:
            if new_path.exists():
                print(f"  狀態: ⚠️ 跳過 (目標檔案已存在)\n")
                stats['skipped'] += 1
                continue
            
            file_path.rename(new_path)
            print(f"  狀態: ✅ 成功\n")
            stats['success'] += 1
        except Exception as e:
            print(f"  狀態: ❌ 失敗 ({e})\n")
            stats['failed'] += 1
    
    print(f"\n{'=' * 60}")
    print("修復統計:")
    print(f"  總計: {stats['total']}")
    if not dry_run:
        print(f"  成功: {stats['success']}")
        print(f"  跳過: {stats['skipped']}")
        print(f"  失敗: {stats['failed']}")
    print(f"{'=' * 60}\n")
    
    return stats


if __name__ == "__main__":
    import sys
    
    # 預設目標資料夾
    target_folder = r"C:\Users\cy540\Downloads"
    
    # 檢查命令列參數
    dry_run = True
    if len(sys.argv) > 1:
        if sys.argv[1] == "--execute":
            dry_run = False
        elif sys.argv[1] == "--help":
            print("用法: python fix_filenames.py [選項]")
            print("\n選項:")
            print("  --execute  實際執行修復（預設為預覽模式）")
            print("  --help     顯示此說明")
            sys.exit(0)
    
    print(f"目標資料夾: {target_folder}")
    fix_filenames(target_folder, recursive=True, dry_run=dry_run)
    
    if dry_run:
        print("💡 這是預覽模式，若要實際執行修復，請加上 --execute 參數")
        print("   python fix_filenames.py --execute")
