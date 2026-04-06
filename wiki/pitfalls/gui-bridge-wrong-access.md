# Issue 13：GUI Bridge 取法錯誤 → Go CLI 不可用警告

**日期**：2026-04-06
**症狀**：點擊按鈕後跳出「Go CLI 不可用」，但 classifier.exe 實際存在
**根因**：`self.core.go_bridge` 不存在（UnifiedClassifierCore 沒有此屬性），永遠回傳 None

## 正確做法

```python
from services.go_bridge import get_bridge
bridge = get_bridge()
if not bridge.is_available:
    ...
```

見 [patterns/add-gui-button.md](../patterns/add-gui-button.md)
