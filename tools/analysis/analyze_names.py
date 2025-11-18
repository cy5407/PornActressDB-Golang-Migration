#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
詳細分析為什麼某些名稱被過濾
"""

import re

def analyze_name(name: str):
    """詳細分析名稱"""
    print(f"\n分析: {name}")
    print(f"長度: {len(name)}")
    
    # 1. 基本檢查
    if not name or len(name) < 2:
        print("  ✗ 長度 < 2")
        return False
    
    if len(name) > 50:
        print("  ✗ 長度 > 50")
        return False
    
    # 2. 垃圾文本模式
    garbage_patterns = [
        r'アナウンサー', r'監督', r'禁欲', r'同人', r'漫画',
        r'変態', r'コスプ', r'デカチン', r'純白', r'エロ',
        r'女神', r'降臨', r'クラス', r'人気', r'イカせ',
        r'やめて', r'細くて', r'ネット', r'ボデ', r'なまなか',
        r'止まらない', r'本の', r'みたいな', r'ヵ月',
        r'生活', r'天性', r'ド', r'エッ', r'カ$', r'ポ',
    ]
    
    matched_patterns = []
    for pattern in garbage_patterns:
        if re.search(pattern, name):
            matched_patterns.append(pattern)
    
    if matched_patterns:
        print(f"  ✗ 匹配垃圾模式: {matched_patterns}")
        return False
    else:
        print(f"  ✓ 未匹配垃圾模式")
    
    # 3. 排除關鍵詞
    exclude_keywords = [
        'ありません', 'ありませんでした', 'いない', 'ない', 'ません',
        'です', 'ます', 'ました', 'Menu', 'star', 'SOKMIL', 'actress',
    ]
    
    matched_keywords = [kw for kw in exclude_keywords if kw in name]
    if matched_keywords:
        print(f"  ✗ 包含排除關鍵詞: {matched_keywords}")
        return False
    else:
        print(f"  ✓ 未包含排除關鍵詞")
    
    # 4. 數字檢查
    digit_count = len(re.findall(r'\d', name))
    if re.match(r'^\d+$', name):
        print(f"  ✗ 全部是數字")
        return False
    elif digit_count > len(name) // 2:
        print(f"  ✗ 數字過多: {digit_count}/{len(name)}")
        return False
    else:
        print(f"  ✓ 數字檢查通過: {digit_count}/{len(name)}")
    
    # 5. 日文字符檢查
    has_japanese = re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', name)
    if has_japanese:
        print(f"  ✓ 包含日文字符")
        return True
    else:
        print(f"  ✗ 不包含日文字符")
        return False

# 測試名稱
test_names = [
    '逢見リカ',
    '臼井リカ',
    '宇野みれいエスワン',
    '宇野みれい',
    '＊＊＊',
]

print("=" * 70)
print("詳細名稱分析")
print("=" * 70)

for name in test_names:
    result = analyze_name(name)
    print(f"  結果: {'✓ 通過' if result else '✗ 過濾'}")

# 檢查 リカ 是否有問題
print("\n" + "=" * 70)
print("特殊檢查: 'リカ' 字符")
print("=" * 70)

for name in ['逢見リカ', '臼井リカ']:
    print(f"\n{name}:")
    for char in name:
        code = ord(char)
        print(f"  '{char}' - Unicode: U+{code:04X} ({code})")
        if '\u30A0' <= char <= '\u30FF':
            print(f"    → 片假名")
        elif '\u3040' <= char <= '\u309F':
            print(f"    → 平假名")
        elif '\u4E00' <= char <= '\u9FAF':
            print(f"    → 漢字")
