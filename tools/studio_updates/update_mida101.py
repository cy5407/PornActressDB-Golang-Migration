import sys
sys.path.insert(0, 'src')

from models.incremental_json_database import IncrementalJSONDB
from models.config import ConfigManager
from services.web_searcher import WebSearcher
import threading

db = IncrementalJSONDB()
config = ConfigManager()
searcher = WebSearcher(config)
stop_event = threading.Event()

print("正在搜尋 MIDA-101...")
result = searcher._search_av_wiki('MIDA-101', stop_event)

if result:
    print(f"\n✅ AV-WIKI 搜尋成功")
    print(f"女優: {result['actresses']}")
    print(f"片商: {result['studio']}")
    
    # 更新資料庫
    db.add_or_update_video('MIDA-101', {
        'actresses': result['actresses'],
        'studio': result['studio'],
        'search_status': 'searched_found',
        'search_method': 'AV-WIKI'
    })
    
    print(f"\n✅ 已更新資料庫")
    
    # 驗證
    updated = db.get_video_info('MIDA-101')
    print(f"\n驗證結果:")
    print(f"  女優: {updated['actresses']}")
    print(f"  片商: {updated['studio']}")
    print(f"  搜尋狀態: {updated['search_status']}")
else:
    print("❌ 未找到資料")
