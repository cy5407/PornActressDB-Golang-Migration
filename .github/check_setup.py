"""
Copilot Agent 設定檢查工具
快速驗證所有必要檔案與設定是否正確
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def check_file_exists(file_path: Path, description: str) -> bool:
    """檢查檔案是否存在"""
    exists = file_path.exists()
    status = f"{Colors.GREEN}✅{Colors.RESET}" if exists else f"{Colors.RED}❌{Colors.RESET}"
    size = f"({file_path.stat().st_size} bytes)" if exists else "(不存在)"
    print(f"  {status} {description:<40} {size}")
    return exists

def check_json_content(file_path: Path, required_keys: List[str]) -> Tuple[bool, List[str]]:
    """檢查 JSON 檔案內容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 移除註解（JSONC 格式）
            content = ""
            for line in f:
                stripped = line.strip()
                if not stripped.startswith('//'):
                    # 移除行內註解
                    if '//' in line:
                        line = line[:line.index('//')]
                    content += line
            
            data = json.loads(content)
            missing = [key for key in required_keys if key not in data]
            return len(missing) == 0, missing
    except Exception as e:
        return False, [str(e)]

def check_markdown_sections(file_path: Path, required_sections: List[str]) -> Tuple[bool, List[str]]:
    """檢查 Markdown 檔案是否包含必要章節"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            missing = [section for section in required_sections if section not in content]
            return len(missing) == 0, missing
    except Exception as e:
        return False, [str(e)]

def main():
    project_root = Path(__file__).parent.parent
    github_dir = project_root / ".github"
    vscode_dir = project_root / ".vscode"
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'🔍 Copilot Agent 設定檢查':^70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.RESET}\n")
    
    all_ok = True
    
    # ==================== 檔案存在性檢查 ====================
    print(f"{Colors.BOLD}{Colors.BLUE}📁 檔案存在性檢查{Colors.RESET}\n")
    
    required_files = {
        github_dir / "copilot-instructions.md": "Agent 指令檔",
        github_dir / "COPILOT_TEMPLATES.md": "任務範本庫",
        github_dir / "AGENT_LOG.md": "任務執行記錄",
        github_dir / "AGENT_SETUP_GUIDE.md": "設定指南",
        github_dir / "agent_verify.py": "自動驗證腳本",
        github_dir / "powershell_aliases.ps1": "PowerShell 別名",
        github_dir / "README.md": "Agent README",
        vscode_dir / "settings.json": "VS Code 設定"
    }
    
    for file_path, description in required_files.items():
        if not check_file_exists(file_path, description):
            all_ok = False
    
    # ==================== VS Code 設定檢查 ====================
    print(f"\n{Colors.BOLD}{Colors.BLUE}⚙️ VS Code 設定檢查{Colors.RESET}\n")
    
    settings_file = vscode_dir / "settings.json"
    if settings_file.exists():
        required_keys = [
            "github.copilot.chat.codeGeneration.useInstructionFiles",
            "chat.useAgentSkills",
            "chat.tools.terminal.autoApprove"
        ]
        
        ok, missing = check_json_content(settings_file, required_keys)
        if ok:
            print(f"  {Colors.GREEN}✅{Colors.RESET} 所有必要設定存在")
            
            # 檢查終端機自動核准設定
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    content = ""
                    for line in f:
                        if not line.strip().startswith('//'):
                            content += line
                    data = json.loads(content)
                    
                    auto_approve = data.get("chat.tools.terminal.autoApprove", {})
                    if isinstance(auto_approve, dict) and len(auto_approve) > 0:
                        print(f"  {Colors.GREEN}✅{Colors.RESET} 終端機自動核准已設定")
                        for cmd, enabled in auto_approve.items():
                            status = "啟用" if enabled else "停用"
                            print(f"     - {cmd}: {status}")
                    else:
                        print(f"  {Colors.YELLOW}⚠️{Colors.RESET} 終端機自動核准未設定")
                        all_ok = False
            except Exception as e:
                print(f"  {Colors.RED}❌{Colors.RESET} 讀取設定時發生錯誤: {e}")
                all_ok = False
        else:
            print(f"  {Colors.RED}❌{Colors.RESET} 缺少必要設定:")
            for key in missing:
                print(f"     - {key}")
            all_ok = False
    else:
        print(f"  {Colors.RED}❌{Colors.RESET} settings.json 不存在")
        all_ok = False
    
    # ==================== Copilot Instructions 檢查 ====================
    print(f"\n{Colors.BOLD}{Colors.BLUE}🧠 Copilot Instructions 檢查{Colors.RESET}\n")
    
    instructions_file = github_dir / "copilot-instructions.md"
    if instructions_file.exists():
        required_sections = [
            "自主執行準則",
            "終端機權限",
            "錯誤處理自動化",
            "開發規範"
        ]
        
        ok, missing = check_markdown_sections(instructions_file, required_sections)
        if ok:
            print(f"  {Colors.GREEN}✅{Colors.RESET} 所有必要章節存在")
        else:
            print(f"  {Colors.YELLOW}⚠️{Colors.RESET} 建議補充以下章節:")
            for section in missing:
                print(f"     - {section}")
    else:
        print(f"  {Colors.RED}❌{Colors.RESET} copilot-instructions.md 不存在")
        all_ok = False
    
    # ==================== 專案結構檢查 ====================
    print(f"\n{Colors.BOLD}{Colors.BLUE}📦 專案結構檢查{Colors.RESET}\n")
    
    project_files = {
        project_root / "go.mod": "Go 模組檔案",
        project_root / "requirements.txt": "Python 相依套件",
        project_root / "cmd" / "scanner" / "main.go": "Go CLI 主程式",
        project_root / "src" / "services" / "go_bridge.py": "Python-Go 橋接層",
        project_root / "tests": "測試目錄"
    }
    
    for file_path, description in project_files.items():
        check_file_exists(file_path, description)
    
    # ==================== 總結 ====================
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.RESET}")
    
    if all_ok:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ 所有設定檢查通過！Copilot Agent 已準備就緒。{Colors.RESET}\n")
        print(f"{Colors.CYAN}下一步：{Colors.RESET}")
        print(f"  1. 在 VS Code 按 Ctrl + Alt + I 開啟 Chat")
        print(f"  2. 確認模式為 'Agent'")
        print(f"  3. 開啟 .github/COPILOT_TEMPLATES.md 複製範本")
        print(f"  4. 開始使用自動化功能！\n")
    else:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️ 部分檢查未通過，請檢查上方錯誤訊息。{Colors.RESET}\n")
        print(f"{Colors.CYAN}建議動作：{Colors.RESET}")
        print(f"  1. 確認所有檔案已正確建立")
        print(f"  2. 檢查 .vscode/settings.json 設定")
        print(f"  3. 閱讀 .github/AGENT_SETUP_GUIDE.md\n")
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 70}{Colors.RESET}\n")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
