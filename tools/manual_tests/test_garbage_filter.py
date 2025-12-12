#!/usr/bin/env python3
"""
測試垃圾文本過濾效果
"""

import re


# 從 avwiki_scraper.py 複製驗證邏輯
def is_valid_actress_name(name: str) -> bool:
    """驗證女優名稱是否有效"""
    if not name or not isinstance(name, str):
        return False

    name = name.strip()

    # 女優名稱長度限制（允許 # 分隔的多人共演格式）
    if len(name) < 2 or len(name) > 50:
        return False

    # 垃圾文本模式（從標題誤提取的片段）
    # 注意：改為更精確的完整詞組，避免誤殺女優名字
    garbage_patterns = [
        r"アナウンサー",
        r"監督",
        r"禁欲生活",
        r"同人漫画",
        r"ド変態",
        r"コスプレ",
        r"デカチン",
        r"降臨",
        r"人気の",
        r"クラスで",
        r"カ月",
        r"ヵ月",
        r"止まらない",
        r"やめて",
        r"なまなかだし",
        r"イカせて",
        r"ネット局",
        r"ネットで",
        r"見つけた",
        r"ボデ",
        r"^元ネット",
        r"細くて$",
        r"みたいな",
        r"天性の",
    ]

    for pattern in garbage_patterns:
        if re.search(pattern, name):
            return False

    # 必須包含日文字符
    if not any(
        "\u3040" <= c <= "\u309f"  # 平假名
        or "\u30a0" <= c <= "\u30ff"  # 片假名
        or "\u4e00" <= c <= "\u9fff"  # 漢字
        for c in name
    ):
        return False

    # 排除關鍵詞
    exclude_keywords = [
        "作品",
        "出演",
        "番号",
        "タイトル",
        "メーカー",
        "レーベル",
        "シリーズ",
        "発売日",
        "収録時間",
        "ジャンル",
        "出演者",
        "監督",
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
        "エスワン",
        "アイデアポケット",
        "プレミアム",
        "ムーディーズ",
    ]

    return all(keyword not in name for keyword in exclude_keywords)


# 從分析結果中提取的垃圾文本樣本
garbage_samples = [
    "元ネット局アナウンサー",
    "同人漫画みたいなド変態なエッ",
    "ヵ月禁欲生活",
    "コスプレ",
    "ポが止まらないカ",
    "本のデカチンで純白ボデ",
    "なまなかだし瀧本雫葉",
    "天性のエロ女神がここに降臨",
    "クラスで人気の純",
    "くイカせてア",
    "やめて",
    "細くて",
    "ネットで",
    "＊＊＊",  # 特殊符號
    "(≥o≤)",  # 表情符號
    "宇野みれいエスワン",  # 片商名稱合併
]

# 包含 # 的合併名稱（現在應該通過驗證，因為這是多人共演標記）
merged_names = [
    "水卜さくら #音羽美鈴",
    "MINAMO #天宮花南",
    "柏木こなつ #胡桃さくら #高瀬りな",
]

# 正常的女優名稱
valid_names = [
    "水卜さくら",
    "石川澪",
    "宮下玲奈",
    "天宮花南",
    "柏木こなつ",
    "白上咲花",
    "瀬名ひかり",
    "高橋しょう子",
    "宇野みれい",  # 確認：正常女優名
    "純白彩永",  # 確認：正常女優名
    "女神ジュン",  # 確認：正常女優名
    "逢見リカ",  # 確認：正常女優名
    "臼井リカ",  # 確認：正常女優名
]

print("=" * 70)
print("垃圾文本過濾測試")
print("=" * 70)

print("\n1️⃣  垃圾文本樣本（應該全部被過濾）:")
garbage_filtered = 0
for name in garbage_samples:
    is_valid = is_valid_actress_name(name)
    status = "✗ 通過" if is_valid else "✓ 過濾"
    print(f"  {status}: {name}")
    if not is_valid:
        garbage_filtered += 1

print(
    f"\n  過濾率: {garbage_filtered}/{len(garbage_samples)} ({garbage_filtered / len(garbage_samples) * 100:.1f}%)"
)

print("\n2️⃣  包含 # 的合併名稱（應該全部通過 - 這是多人共演標記）:")
merged_passed = 0
for name in merged_names:
    is_valid = is_valid_actress_name(name)
    status = "✓ 通過" if is_valid else "✗ 過濾"
    print(f"  {status}: {name}")
    if is_valid:
        merged_passed += 1

print(
    f"\n  通過率: {merged_passed}/{len(merged_names)} ({merged_passed / len(merged_names) * 100:.1f}%)"
)

print("\n3️⃣  正常女優名稱（應該全部通過）:")
valid_passed = 0
for name in valid_names:
    is_valid = is_valid_actress_name(name)
    status = "✓ 通過" if is_valid else "✗ 過濾"
    print(f"  {status}: {name}")
    if is_valid:
        valid_passed += 1

print(
    f"\n  通過率: {valid_passed}/{len(valid_names)} ({valid_passed / len(valid_names) * 100:.1f}%)"
)

print("\n" + "=" * 70)
print("總結")
print("=" * 70)
total_tests = len(garbage_samples) + len(merged_names) + len(valid_names)
total_correct = garbage_filtered + merged_passed + valid_passed
print(f"總測試: {total_tests}")
print(f"正確: {total_correct} ({total_correct / total_tests * 100:.1f}%)")
print("\n📌 重要: # 符號是多人共演標記，由 classifier_core.py 處理分割")
