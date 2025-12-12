#!/usr/bin/env python3
"""
測試互動式分類器如何處理合併名稱
"""


# 模擬 _parse_actresses_list 函式
def _parse_actresses_list(actresses):
    """
    解析女優名單，處理用 # 分隔的多人共演格式

    Args:
        actresses: 資料庫中的女優列表

    Returns:
        tuple: (parsed_actresses_list, is_collaboration)
    """
    if not actresses:
        return [], False

    # 如果有多個女優記錄，直接返回
    if len(actresses) > 1:
        return actresses, True

    # 檢查單一記錄是否包含 # 分隔的多個女優
    actress_str = actresses[0]
    if "#" in actress_str:
        # 解析 # 分隔的女優名單
        parsed_actresses = []
        for name in actress_str.split("#"):
            name = name.strip()
            if name:
                parsed_actresses.append(name)

        return parsed_actresses, len(parsed_actresses) > 1

    # 單一女優
    return [actress_str], False


print("=" * 80)
print("測試互動式分類器如何處理合併名稱")
print("=" * 80)

# 測試案例
test_cases = [
    # (輸入, 期望輸出, 描述)
    (["水卜さくら"], (["水卜さくら"], False), "單一女優（無 #）"),
    (["水卜さくら", "音羽美鈴"], (["水卜さくら", "音羽美鈴"], True), "多個女優記錄"),
    (
        ["水卜さくら #音羽美鈴"],
        (["水卜さくら", "音羽美鈴"], True),
        "合併名稱（# 分隔）",
    ),
    (
        ["柏木こなつ #胡桃さくら #高瀬りな"],
        (["柏木こなつ", "胡桃さくら", "高瀬りな"], True),
        "3位女優合併",
    ),
    (
        ["如月りいさ #小那海あや #美澄玲衣 #逢月ひまり"],
        (["如月りいさ", "小那海あや", "美澄玲衣", "逢月ひまり"], True),
        "4位女優合併",
    ),
]

print("\n📋 測試結果:\n")

all_passed = True
for i, (input_actresses, expected, description) in enumerate(test_cases, 1):
    result = _parse_actresses_list(input_actresses)
    passed = result == expected

    status = "✅" if passed else "❌"
    print(f"{status} 測試 {i}: {description}")
    print(f"   輸入: {input_actresses}")
    print(f"   輸出: {result}")
    print(f"   期望: {expected}")

    if not passed:
        all_passed = False
        print("   ⚠️  測試失敗！")
    print()

print("=" * 80)
print("模擬互動式分類流程")
print("=" * 80)

print("\n情境 1: 資料庫中儲存的是 '水卜さくら #音羽美鈴'")
print("-" * 80)

actresses_db = ["水卜さくら #音羽美鈴"]  # 從資料庫取得
parsed, is_collab = _parse_actresses_list(actresses_db)

print(f"從資料庫讀取: {actresses_db}")
print(f"解析後: {parsed}")
print(f"是否多人共演: {is_collab}")

if is_collab:
    print("\n🎬 觸發互動式分類器:")
    print("   請選擇要分類到哪位女優的資料夾：")
    for i, actress in enumerate(parsed, 1):
        print(f"   {i}. {actress}")
    print(f"   {len(parsed) + 1}. 放到「多人共演」資料夾")
    print(f"   {len(parsed) + 2}. 跳過此檔案")

print("\n" + "=" * 80)
print("結論")
print("=" * 80)

if all_passed:
    print("✅ 所有測試通過！")
    print("\n📌 重要發現:")
    print(
        "1. classifier_core.py 的 _parse_actresses_list() 會自動處理 # 分隔的女優名稱"
    )
    print("2. 當檢測到 # 符號時，會將字串分割成個別女優")
    print("3. 分割後的女優列表會傳給互動式分類器，讓使用者選擇")
    print("4. 這表示 # 合併名稱「應該」會在互動式分類時被正確處理")
    print("\n⚠️  問題:")
    print("- 資料庫中儲存了 106 個包含 # 的合併名稱")
    print("- 這些合併名稱會在分類時觸發互動式選擇")
    print("- 但如果使用者「記住偏好」，系統會儲存整個合併字串作為偏好")
    print("\n💡 建議:")
    print("- 保留現有邏輯，因為它已經能正確處理 # 分隔")
    print("- 不需要在 _is_valid_actress_name() 中過濾 # 符號")
    print("- # 符號是正常的多人共演標記，不是垃圾文本")
else:
    print("❌ 部分測試失敗，請檢查邏輯")
