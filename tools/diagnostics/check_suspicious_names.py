#!/usr/bin/env python3
"""
檢查可疑的女優名稱
"""

import re


# 從 avwiki_scraper.py 複製驗證邏輯
def is_valid_actress_name(name: str) -> bool:
    """驗證是否為有效的女優名稱"""
    if not name or len(name) < 2:
        return False

    if len(name) > 50:
        return False

    # 垃圾文本模式
    garbage_patterns = [
        r"アナウンサー",
        r"監督",
        r"禁欲",
        r"同人",
        r"漫画",
        r"変態",
        r"コスプ",
        r"デカチン",
        r"純白",
        r"エロ",
        r"女神",
        r"降臨",
        r"クラス",
        r"人気",
        r"イカせ",
        r"やめて",
        r"細くて",
        r"ネット",
        r"ボデ",
        r"なまなか",
        r"止まらない",
        r"本の",
        r"みたいな",
        r"ヵ月",
        r"生活",
        r"天性",
        r"ド",
        r"エッ",
        r"カ$",
        r"ポ",
    ]

    for pattern in garbage_patterns:
        if re.search(pattern, name):
            return False

    # 排除關鍵詞
    exclude_keywords = [
        "ありません",
        "ありませんでした",
        "いない",
        "ない",
        "ません",
        "です",
        "ます",
        "ました",
        "Menu",
        "star",
        "SOKMIL",
        "actress",
    ]

    if any(keyword in name for keyword in exclude_keywords):
        return False

    if re.match(r"^\d+$", name) or len(re.findall(r"\d", name)) > len(name) // 2:
        return False

    if re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", name):
        return True

    return False


# 可疑名稱檢查
suspicious_names = [
    ("＊＊＊", "特殊符號"),
    ("逢見リカ", "正常名稱？"),
    ("臼井リカ", "正常名稱？"),
    ("(≥o≤)", "表情符號"),
    ("女神ジュン", "包含「女神」"),
    ("純白彩永", "包含「純白」"),
    ("宇野みれいエスワン", "片商合併？"),
]

print("=" * 70)
print("可疑女優名稱檢查")
print("=" * 70)

for name, reason in suspicious_names:
    is_valid = is_valid_actress_name(name)
    status = "✓ 通過" if is_valid else "✗ 過濾"

    print(f"\n{status}: {name}")
    print(f"  原因: {reason}")
    print(f"  長度: {len(name)} 字元")

    # 詳細分析
    if "＊" in name or "(" in name or ")" in name:
        print("  ⚠️  包含特殊符號")

    if "エスワン" in name or "S1" in name:
        print("  ⚠️  可能包含片商名稱")

    # 檢查是否匹配垃圾模式
    garbage_patterns = [r"女神", r"純白"]
    for pattern in garbage_patterns:
        if re.search(pattern, name):
            print(f"  ⚠️  匹配垃圾模式: {pattern}")

print("\n" + "=" * 70)
print("建議")
print("=" * 70)
print("1. ＊＊＊ - 應該移除（特殊符號）")
print("2. (≥o≤) - 應該移除（表情符號）")
print("3. 女神ジュン - 需要確認是否為真實女優名")
print("4. 純白彩永 - 需要確認是否為真實女優名")
print("5. 逢見リカ - 可能是正常名稱（4字元）")
print("6. 臼井リカ - 可能是正常名稱（4字元）")
print("7. 宇野みれいエスワン - 應該拆分為「宇野みれい」")
