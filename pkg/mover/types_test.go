package mover

import (
	"encoding/json"
	"testing"
)

// TestMergeResult_JSONShapeIncludesFilesSkipped 鎖住 MergeResult 序列化後一定
// 含有 files_skipped 欄位。
//
// 歷史背景: 在 contracts.MergeResult 還存在的時代,mergeResultToContract
// 曾經漏抄 FilesSkipped 欄位 (D2-1 regression);收斂 DTO 後該轉換函式被刪,
// 此 regression guard 從 pkg/app/error_paths_test.go (TestMergeResultToContract_CopiesEveryField)
// 搬到本檔,改以「直接 JSON 序列化 mover.MergeResult」的方式保證形狀不變。
// Python wrapper (tests/test_go_cli_contracts.py) 也鎖住相同 key,雙重保險。
func TestMergeResult_JSONShapeIncludesFilesSkipped(t *testing.T) {
	res := MergeResult{
		SourceDir:    "src",
		DestDir:      "dst",
		FilesMoved:   7,
		FilesSkipped: 4,
		FilesTotal:   11,
		Success:      true,
	}
	data, err := json.Marshal(res)
	if err != nil {
		t.Fatalf("json.Marshal failed: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal failed: %v", err)
	}
	requiredKeys := []string{
		"source_dir",
		"dest_dir",
		"files_moved",
		"files_skipped",
		"files_total",
		"success",
		"deleted_src",
	}
	for _, key := range requiredKeys {
		if _, ok := decoded[key]; !ok {
			t.Errorf("MergeResult JSON missing key %q (got: %s)", key, string(data))
		}
	}
	if got := decoded["files_skipped"]; got != float64(4) {
		t.Errorf("files_skipped = %v, want 4 (must not be zeroed)", got)
	}
}
