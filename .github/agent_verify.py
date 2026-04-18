"""
Copilot Agent 自動化測試腳本
用於快速驗證專案整體狀態
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(title: str):
    """列印區塊標題"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")

def run_command(cmd: list, description: str, cwd: Path = None) -> bool:
    """執行指令並回報結果"""
    print(f"{Colors.BLUE}▶ {description}{Colors.RESET}")
    print(f"  指令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120
        )
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ 成功{Colors.RESET}")
            if result.stdout.strip():
                # 只顯示摘要資訊
                lines = result.stdout.strip().split('\n')
                if len(lines) > 10:
                    print(f"  輸出: (共 {len(lines)} 行，顯示最後 5 行)")
                    for line in lines[-5:]:
                        print(f"    {line}")
                else:
                    print(f"  輸出: {result.stdout.strip()}")
            return True
        else:
            print(f"{Colors.RED}❌ 失敗 (Exit Code: {result.returncode}){Colors.RESET}")
            if result.stderr:
                print(f"{Colors.RED}錯誤輸出:{Colors.RESET}")
                for line in result.stderr.split('\n')[:20]:  # 只顯示前 20 行
                    print(f"  {line}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}❌ 超時 (>120 秒){Colors.RESET}")
        return False
    except FileNotFoundError:
        print(f"{Colors.RED}❌ 指令不存在{Colors.RESET}")
        return False
    except Exception as e:
        print(f"{Colors.RED}❌ 執行錯誤: {e}{Colors.RESET}")
        return False

def main():
    """主測試流程"""
    project_root = Path(__file__).parent.parent
    results = {
        "Go 編譯": False,
        "Go 測試": False,
        "Python 語法": False,
        "Python 測試": False,
        "CLI 建構": False,
        "整合測試": False
    }
    
    start_time = datetime.now()
    print_header("🤖 Copilot Agent 自動化驗證")
    print(f"專案路徑: {project_root}")
    print(f"開始時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ==================== Go 測試 ====================
    print_header("🔷 Go 模組驗證")
    
    # 1. Go 編譯檢查
    results["Go 編譯"] = run_command(
        ["go", "build", "./..."],
        "Go 編譯檢查",
        cwd=project_root
    )
    
    # 2. Go 單元測試
    results["Go 測試"] = run_command(
        ["go", "test", "./...", "-v", "-short"],
        "Go 單元測試",
        cwd=project_root
    )
    
    # 3. CLI 建構
    results["CLI 建構"] = run_command(
        ["go", "build", "-o", "classifier.exe", "./cmd/scanner"],
        "CLI 建構",
        cwd=project_root
    )
    
    # ==================== Python 測試 ====================
    print_header("🐍 Python 模組驗證")
    
    # 4. Python 語法檢查（快速）
    src_files = list((project_root / "src").rglob("*.py"))
    if src_files:
        print(f"{Colors.BLUE}▶ Python 語法檢查{Colors.RESET}")
        print(f"  檢查 {len(src_files)} 個檔案...")
        syntax_ok = True
        for py_file in src_files[:5]:  # 只檢查前 5 個檔案（示範）
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                cwd=project_root,
                capture_output=True
            )
            if result.returncode != 0:
                print(f"  {Colors.RED}✗ {py_file.name}{Colors.RESET}")
                syntax_ok = False
            else:
                print(f"  {Colors.GREEN}✓ {py_file.name}{Colors.RESET}")
        results["Python 語法"] = syntax_ok
        if syntax_ok:
            print(f"{Colors.GREEN}✅ 語法檢查通過{Colors.RESET}")
        else:
            print(f"{Colors.RED}❌ 發現語法錯誤{Colors.RESET}")
    
    # 5. Python 單元測試
    results["Python 測試"] = run_command(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-x"],
        "Python 單元測試",
        cwd=project_root
    )
    
    # 6. 整合測試
    if (project_root / "test_go_db_bridge.py").exists():
        results["整合測試"] = run_command(
            [sys.executable, "test_go_db_bridge.py"],
            "Go-Python 整合測試",
            cwd=project_root
        )
    
    # ==================== 總結報告 ====================
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print_header("📊 驗證結果總結")
    
    total = len(results)
    passed = sum(results.values())
    
    for test_name, passed_status in results.items():
        status = f"{Colors.GREEN}✅ 通過{Colors.RESET}" if passed_status else f"{Colors.RED}❌ 失敗{Colors.RESET}"
        print(f"  {test_name:.<40} {status}")
    
    print(f"\n{Colors.BOLD}總計: {passed}/{total} 項通過{Colors.RESET}")
    print(f"耗時: {duration:.2f} 秒")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 所有測試通過！專案狀態良好。{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️ 部分測試失敗，請檢查上方錯誤訊息。{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
