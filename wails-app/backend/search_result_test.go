package backend

import (
	"encoding/json"
	"testing"
)

// 鎖定 D4-1 修正：Python 搜尋入口輸出 "search_method" 鍵，Go 必須能讀到它。
func TestSearchResultUnmarshalAcceptsSearchMethodKey(t *testing.T) {
	var r SearchResult
	if err := json.Unmarshal([]byte(`{"code":"ABC-123","search_method":"AV-WIKI"}`), &r); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if r.Method != "AV-WIKI" {
		t.Fatalf("expected Method=AV-WIKI from search_method key, got %q", r.Method)
	}
}

func TestSearchResultUnmarshalStillAcceptsMethodKey(t *testing.T) {
	var r SearchResult
	if err := json.Unmarshal([]byte(`{"code":"ABC-123","method":"JAVDB"}`), &r); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if r.Method != "JAVDB" {
		t.Fatalf("expected Method=JAVDB from method key, got %q", r.Method)
	}
}

// marshal 仍輸出 "method"，前端 SearchResultDialog.tsx 讀 result.method 不受影響。
func TestSearchResultMarshalEmitsMethodKey(t *testing.T) {
	b, err := json.Marshal(SearchResult{Method: "AV-WIKI"})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("re-unmarshal: %v", err)
	}
	if _, ok := m["method"]; !ok {
		t.Fatalf("marshal should emit 'method' key for frontend, got %s", b)
	}
	if _, ok := m["search_method"]; ok {
		t.Fatalf("marshal should NOT emit 'search_method', got %s", b)
	}
}
