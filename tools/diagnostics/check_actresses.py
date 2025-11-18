import json

with open('data/json_db/data.json', encoding='utf-8') as f:
    data = json.load(f)

actresses_count = len(data.get('actresses', {}))
print(f"actresses 字段數量: {actresses_count}")

if actresses_count > 0:
    print(f"\n前 20 個女優:")
    for i, actress_name in enumerate(list(data.get('actresses', {}).keys())[:20], 1):
        print(f"  {i}. {actress_name}")

# 從影片中提取實際的女優名稱（去重）
actual_actresses = set()
for video in data.get('videos', {}).values():
    for actress in video.get('actresses', []):
        if actress:
            actual_actresses.add(actress)

print(f"\n從影片中統計的實際女優數: {len(actual_actresses)}")
print(f"\n差異: {actresses_count - len(actual_actresses)}")
