import json
from collections import Counter

with open("data/json_db/data.json", encoding="utf-8") as f:
    data = json.load(f)

# 從影片中提取所有女優名稱（包含重複）
all_actresses = []
for video in data.get("videos", {}).values():
    for actress in video.get("actresses", []):
        if actress:
            all_actresses.append(actress)

# 統計出現次數
actress_counts = Counter(all_actresses)

print(f"總女優出現次數: {len(all_actresses)}")
print(f"去重後女優數: {len(actress_counts)}")
print("\n出現次數最多的前 20 位女優:")
for actress, count in actress_counts.most_common(20):
    print(f"  {actress}: {count} 部")

# 檢查是否有異常的女優名稱
print("\n異常的女優名稱（包含特殊字符）:")
abnormal = []
for actress in actress_counts.keys():
    if "#" in actress or len(actress) > 20 or len(actress) < 2:
        abnormal.append(actress)
        print(f"  - {actress}")

if abnormal:
    print(f"\n發現 {len(abnormal)} 個異常女優名稱")
else:
    print("\n未發現異常女優名稱")

# 檢查 actresses 字段中的女優
actresses_in_db = set(data.get("actresses", {}).keys())
actresses_in_videos = set(actress_counts.keys())

print(
    f"\n在 actresses 字段中但不在影片中的女優: {len(actresses_in_db - actresses_in_videos)}"
)
print(
    f"在影片中但不在 actresses 字段中的女優: {len(actresses_in_videos - actresses_in_db)}"
)

if len(actresses_in_videos - actresses_in_db) > 0:
    print("\n前 20 個缺失的女優:")
    for i, actress in enumerate(list(actresses_in_videos - actresses_in_db)[:20], 1):
        print(f"  {i}. {actress}")
