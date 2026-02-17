#!/bin/bash

# Claude Skills 驗證器
# 驗證技能是否符合 Claude Code Skills 標準

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 使用方式
usage() {
    echo "用法: $0 [技能目錄路徑]"
    echo ""
    echo "範例:"
    echo "  $0 .claude/skills/my-skill"
    echo "  $0 ./my-skill"
    echo ""
    exit 1
}

# 印出狀態訊息
print_status() {
    local status=$1
    local message=$2
    case $status in
        "ok")
            echo -e "${GREEN}✅${NC} $message"
            ;;
        "warn")
            echo -e "${YELLOW}⚠️${NC} $message"
            ;;
        "error")
            echo -e "${RED}❌${NC} $message"
            ;;
        "info")
            echo -e "${BLUE}ℹ️${NC} $message"
            ;;
    esac
}

# 檢查必要工具
check_dependencies() {
    local deps=("jq" "grep" "sed")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            print_status "warn" "建議安裝 $dep 以獲得更好的驗證效果"
        fi
    done
}

# 驗證技能名稱
validate_skill_name() {
    local name=$1
    
    # 檢查長度
    if [ ${#name} -gt 64 ]; then
        print_status "error" "技能名稱過長 (${#name} > 64 字元)"
        return 1
    fi
    
    # 檢查格式 (只允許小寫字母、數字和連字號)
    if [[ ! $name =~ ^[a-z0-9-]+$ ]]; then
        print_status "error" "技能名稱格式不正確 (只允許小寫字母、數字和連字號)"
        return 1
    fi
    
    # 檢查是否以連字號開頭或結尾
    if [[ $name =~ ^-.*-$ ]]; then
        print_status "error" "技能名稱不應以連字號開頭或結尾"
        return 1
    fi
    
    print_status "ok" "技能名稱格式正確: $name"
    return 0
}

# 驗證 YAML 前置資料
validate_frontmatter() {
    local skill_file=$1
    
    # 檢查是否有前置資料
    if ! grep -q "^---" "$skill_file"; then
        print_status "error" "缺少 YAML 前置資料"
        return 1
    fi
    
    # 提取前置資料
    local frontmatter=$(sed -n '/^---$/,/^---$/p' "$skill_file")
    
    # 檢查必要欄位
    if ! echo "$frontmatter" | grep -q "name:"; then
        print_status "error" "前置資料缺少 'name' 欄位"
        return 1
    fi
    
    if ! echo "$frontmatter" | grep -q "description:"; then
        print_status "warn" "建議添加 'description' 欄位以改善技能發現"
    fi
    
    # 檢查技能名稱
    local name=$(echo "$frontmatter" | grep "name:" | sed 's/name:\s*//' | tr -d '"' | xargs)
    if [ -n "$name" ]; then
        validate_skill_name "$name"
    fi
    
    print_status "ok" "YAML 前置資料格式有效"
    return 0
}

# 驗證檔案結構
validate_file_structure() {
    local skill_dir=$1
    local skill_name=$(basename "$skill_dir")
    
    # 檢查 SKILL.md 是否存在
    if [ ! -f "$skill_dir/SKILL.md" ]; then
        print_status "error" "缺少必要檔案: SKILL.md"
        return 1
    fi
    
    print_status "ok" "SKILL.md 檔案存在"
    
    # 檢查建議的目錄結構
    local suggested_dirs=("examples" "templates" "scripts")
    for dir in "${suggested_dirs[@]}"; do
        if [ -d "$skill_dir/$dir" ]; then
            print_status "ok" "包含建議目錄: $dir/"
        else
            print_status "info" "可考慮添加目錄: $dir/"
        fi
    done
    
    return 0
}

# 驗證內容品質
validate_content_quality() {
    local skill_file=$1
    
    # 檢查檔案大小 (太小可能內容不足)
    local file_size=$(wc -c < "$skill_file")
    if [ $file_size -lt 200 ]; then
        print_status "warn" "技能內容較少 ($file_size bytes)，考慮添加更多說明"
    fi
    
    # 檢查是否有使用說明
    if grep -q -i "使用\|usage\|example" "$skill_file"; then
        print_status "ok" "包含使用說明或範例"
    else
        print_status "warn" "建議添加使用說明或範例"
    fi
    
    # 檢查是否有 $ARGUMENTS 佔位符
    if grep -q "\$ARGUMENTS" "$skill_file"; then
        print_status "ok" "正確使用 \$ARGUMENTS 佔位符"
    else
        print_status "info" "未使用 \$ARGUMENTS 佔位符 (如果技能不需要參數則正常)"
    fi
    
    return 0
}

# 驗證工具權限
validate_tool_permissions() {
    local skill_file=$1
    
    if grep -q "allowed-tools:" "$skill_file"; then
        local tools=$(grep "allowed-tools:" "$skill_file" | sed 's/allowed-tools:\s*//')
        print_status "ok" "已設定工具權限: $tools"
        
        # 檢查是否過於寬泛
        if echo "$tools" | grep -q -E "(Read|Write|Edit|Bash|Grep|Glob)" | wc -l | grep -q "[6-9]"; then
            print_status "warn" "工具權限可能過於寬泛，考慮只授予必要權限"
        fi
    else
        print_status "info" "未限制工具權限 (使用預設權限)"
    fi
    
    return 0
}

# 安全性檢查
validate_security() {
    local skill_file=$1
    
    # 檢查是否有潛在的安全問題
    if grep -q -E "rm\s+-rf|sudo|passwd|chmod\s+777" "$skill_file"; then
        print_status "warn" "檢測到潛在的高風險命令，請確保安全性"
    fi
    
    # 檢查是否有 disable-model-invocation 設定
    if grep -q "disable-model-invocation:\s*true" "$skill_file"; then
        print_status "ok" "已設定防止自動觸發 (適用於高風險操作)"
    fi
    
    return 0
}

# 主要驗證函數
validate_skill() {
    local skill_path=$1
    
    if [ ! -d "$skill_path" ]; then
        print_status "error" "技能目錄不存在: $skill_path"
        return 1
    fi
    
    local skill_file="$skill_path/SKILL.md"
    local skill_name=$(basename "$skill_path")
    
    echo -e "${BLUE}🔍 驗證技能: $skill_name${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local errors=0
    local warnings=0
    
    # 執行各項檢查
    validate_file_structure "$skill_path" || ((errors++))
    
    if [ -f "$skill_file" ]; then
        validate_frontmatter "$skill_file" || ((errors++))
        validate_content_quality "$skill_file" || ((warnings++))
        validate_tool_permissions "$skill_file"
        validate_security "$skill_file"
    fi
    
    # 總結
    echo ""
    echo -e "${BLUE}📊 驗證總結${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ $errors -eq 0 ]; then
        if [ $warnings -eq 0 ]; then
            print_status "ok" "技能通過所有檢查 ✨"
            echo -e "${GREEN}評分: 10/10${NC}"
        else
            print_status "ok" "技能基本合格，有 $warnings 個改善建議"
            echo -e "${YELLOW}評分: 8/10${NC}"
        fi
    else
        print_status "error" "發現 $errors 個錯誤，$warnings 個警告"
        echo -e "${RED}評分: $((10 - errors - warnings))/10${NC}"
        echo ""
        echo "請修復錯誤後重新驗證。"
        return 1
    fi
    
    return 0
}

# 主程式
main() {
    if [ $# -eq 0 ]; then
        usage
    fi
    
    local skill_path=$1
    
    # 檢查相依工具
    check_dependencies
    
    # 執行驗證
    validate_skill "$skill_path"
}

# 如果腳本被直接執行 (而不是被 source)
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi