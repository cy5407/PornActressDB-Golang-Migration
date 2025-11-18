"""顯示需要重新搜尋的番號列表"""
import json
import sys
from pathlib import Path

def show_research_needed(db_path: str):
    """顯示需要重新搜尋的番號"""
    
    with open(db_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    videos = data.get('videos', {})
    
    # 分類統計
    research_needed = {
        'search_error': [],        # 搜尋錯誤（超過10位女優）
        'no_actress_found': [],    # 未找到女優
        'empty_actresses': [],     # 女優列表為空
        'searched_multiple': [],   # 找到4-10位女優（可能是合集）
    }
    
    for code, info in videos.items():
        status = info.get('search_status')
        actresses = info.get('actresses', [])
        
        if status == 'search_error':
            research_needed['search_error'].append({
                'code': code,
                'file': info.get('file_path', 'N/A'),
                'reason': info.get('search_error_reason', 'Unknown'),
                'original_count': info.get('original_actress_count', 0)
            })
        elif status == 'no_actress_found':
            research_needed['no_actress_found'].append({
                'code': code,
                'file': info.get('file_path', 'N/A')
            })
        elif not actresses:
            research_needed['empty_actresses'].append({
                'code': code,
                'file': info.get('file_path', 'N/A'),
                'status': status or 'unknown'
            })
        elif status == 'searched_multiple':
            research_needed['searched_multiple'].append({
                'code': code,
                'file': info.get('file_path', 'N/A'),
                'count': len(actresses),
                'actresses': actresses[:5]
            })
    
    # 顯示報告
    print("=" * 80)
    print("🔍 需要重新搜尋的番號分析")
    print("=" * 80)
    
    total_research = sum(len(v) for v in research_needed.values())
    print(f"\n總計需要重新搜尋: {total_research} 個番號\n")
    
    # 1. 搜尋錯誤（最優先）
    if research_needed['search_error']:
        print(f"\n1️⃣  搜尋錯誤（上次解析失敗）: {len(research_needed['search_error'])} 個")
        print("=" * 80)
        for i, video in enumerate(research_needed['search_error'][:10], 1):
            print(f"\n{i}. 番號: {video['code']}")
            print(f"   檔案: {video['file']}")
            print(f"   原因: {video['reason']}")
            if video['original_count'] > 0:
                print(f"   原錯誤數量: {video['original_count']} 位")
        
        if len(research_needed['search_error']) > 10:
            print(f"\n   ... 還有 {len(research_needed['search_error']) - 10} 個番號")
    
    # 2. 未找到女優
    if research_needed['no_actress_found']:
        print(f"\n2️⃣  未找到女優: {len(research_needed['no_actress_found'])} 個")
        print("=" * 80)
        for i, video in enumerate(research_needed['no_actress_found'][:10], 1):
            print(f"{i}. {video['code']} - {video['file']}")
        
        if len(research_needed['no_actress_found']) > 10:
            print(f"   ... 還有 {len(research_needed['no_actress_found']) - 10} 個番號")
    
    # 3. 女優列表為空
    if research_needed['empty_actresses']:
        print(f"\n3️⃣  女優列表為空: {len(research_needed['empty_actresses'])} 個")
        print("=" * 80)
        for i, video in enumerate(research_needed['empty_actresses'][:10], 1):
            print(f"{i}. {video['code']} (狀態: {video['status']}) - {video['file']}")
        
        if len(research_needed['empty_actresses']) > 10:
            print(f"   ... 還有 {len(research_needed['empty_actresses']) - 10} 個番號")
    
    # 4. 多位女優（需確認）
    if research_needed['searched_multiple']:
        print(f"\n4️⃣  多位女優（可能是合集，需確認）: {len(research_needed['searched_multiple'])} 個")
        print("=" * 80)
        for i, video in enumerate(research_needed['searched_multiple'][:5], 1):
            print(f"\n{i}. 番號: {video['code']}")
            print(f"   女優數: {video['count']}")
            print(f"   女優: {', '.join(video['actresses'])}")
            print(f"   檔案: {video['file']}")
        
        if len(research_needed['searched_multiple']) > 5:
            print(f"\n   ... 還有 {len(research_needed['searched_multiple']) - 5} 個番號")
    
    print("\n" + "=" * 80)
    print("💡 建議")
    print("=" * 80)
    
    if research_needed['search_error']:
        print(f"\n✅ 最優先: 重新搜尋 {len(research_needed['search_error'])} 個 'search_error' 番號")
        print("   這些番號上次搜尋失敗（超過 10 位女優），已清空結果")
        print("   建議使用其他網站（如 JAVDB）搜尋")
    
    if research_needed['no_actress_found'] or research_needed['empty_actresses']:
        total_empty = len(research_needed['no_actress_found']) + len(research_needed['empty_actresses'])
        print(f"\n⚠️  次優先: 重新搜尋 {total_empty} 個無女優資料的番號")
        print("   可能原因：網站暫時問題、VR/無碼片、冷門番號")
    
    if research_needed['searched_multiple']:
        print(f"\n🤔 需確認: {len(research_needed['searched_multiple'])} 個多位女優番號")
        print("   這些可能是合集片，建議人工確認")
    
    print("\n" + "=" * 80)
    
    return research_needed

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='顯示需要重新搜尋的番號')
    parser.add_argument('--db', default='data/json_db/data.json', help='資料庫檔案路徑')
    parser.add_argument('--export', help='匯出番號列表到檔案（每行一個番號）')
    
    args = parser.parse_args()
    
    research_needed = show_research_needed(args.db)
    
    # 匯出選項
    if args.export:
        all_codes = []
        for category in ['search_error', 'no_actress_found', 'empty_actresses']:
            all_codes.extend([v['code'] for v in research_needed[category]])
        
        with open(args.export, 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_codes))
        
        print(f"\n📝 已匯出 {len(all_codes)} 個番號到: {args.export}")
