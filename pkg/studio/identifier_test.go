package studio

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNewStudioIdentifier(t *testing.T) {
	// 測試使用預設規則（檔案不存在時）
	si, err := NewStudioIdentifier("nonexistent.json")
	// 即使檔案不存在，也應該返回有效的識別器（使用預設規則）
	if si == nil {
		t.Fatal("Expected StudioIdentifier instance even when file doesn't exist")
	}
	// 應該有錯誤（檔案不存在），但識別器仍應可用
	if err == nil {
		t.Error("Expected error when file doesn't exist")
	}

	// 檢查預設規則是否被載入
	if len(si.StudioPatterns) == 0 {
		t.Error("Expected default rules to be loaded")
	}
}

func TestIdentifyStudio(t *testing.T) {
	si, _ := NewStudioIdentifier("")

	tests := []struct {
		name     string
		code     string
		expected string
	}{
		{"S1 番號 - SONE", "SONE-123", "S1"},
		{"S1 番號 - SSIS", "SSIS-001", "S1"},
		{"S1 番號 - SSNI", "SSNI-789", "S1"},
		{"MOODYZ 番號 - MIDV", "MIDV-456", "MOODYZ"},
		{"MOODYZ 番號 - MIDE", "MIDE-999", "MOODYZ"},
		{"PREMIUM 番號 - IPX", "IPX-123", "PREMIUM"},
		{"PREMIUM 番號 - IPZZ", "IPZZ-001", "PREMIUM"},
		{"FALENO 番號 - FSDSS", "FSDSS-789", "FALENO"},
		{"KAWAII 番號 - CAWD", "CAWD-456", "KAWAII"},
		{"未知番號", "XYZ-123", "UNKNOWN"},
		{"空字串", "", "UNKNOWN"},
		{"無效格式", "123456", "UNKNOWN"},
		{"小寫前綴", "sone-123", "S1"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := si.IdentifyStudio(tt.code)
			if result != tt.expected {
				t.Errorf("IdentifyStudio(%s) = %s, want %s", tt.code, result, tt.expected)
			}
		})
	}
}

func TestNormalizeStudioName(t *testing.T) {
	si, _ := NewStudioIdentifier("")

	tests := []struct {
		name       string
		studioName string
		videoCode  string
		expected   string
	}{
		{"使用番號優先判斷 - S1", "MOODYZ", "SONE-123", "S1"},
		{"使用番號優先判斷 - MOODYZ", "S1", "MIDV-456", "MOODYZ"},
		{"別名對照 - S1 NO.1 STYLE", "S1 NO.1 STYLE", "", "S1"},
		{"別名對照 - MOODYZ DIVA", "MOODYZ DIVA", "", "MOODYZ"},
		{"別名對照 - Premium", "Premium", "", "PREMIUM"},
		{"別名對照 - 日文 S1", "エスワン", "", "S1"},
		{"別名對照 - 日文 FALENO", "ファレノ", "", "FALENO"},
		{"大小寫不敏感", "premium", "", "PREMIUM"},
		{"片商代碼轉換", "SONE", "", "S1"},
		{"片商代碼轉換", "MIDV", "", "MOODYZ"},
		{"空字串", "", "", "UNKNOWN"},
		{"空白字串", "   ", "", "UNKNOWN"},
		{"移除前後空白", "  S1  ", "", "S1"},
		{"保持原名（非別名）", "MADONNA", "", "MADONNA"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := si.NormalizeStudioName(tt.studioName, tt.videoCode)
			if result != tt.expected {
				t.Errorf("NormalizeStudioName(%s, %s) = %s, want %s",
					tt.studioName, tt.videoCode, result, tt.expected)
			}
		})
	}
}

func TestIsMajorStudio(t *testing.T) {
	si, _ := NewStudioIdentifier("")

	tests := []struct {
		name       string
		studioName string
		expected   bool
	}{
		{"S1 是大片商", "S1", true},
		{"MOODYZ 是大片商", "MOODYZ", true},
		{"PREMIUM 是大片商", "PREMIUM", true},
		{"FALENO 是大片商", "FALENO", true},
		{"KAWAII 是大片商", "KAWAII", true},
		{"未知片商不是大片商", "UNKNOWN", false},
		{"小片商", "ABC", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := si.IsMajorStudio(tt.studioName)
			if result != tt.expected {
				t.Errorf("IsMajorStudio(%s) = %v, want %v", tt.studioName, result, tt.expected)
			}
		})
	}
}

func TestGetAllStudios(t *testing.T) {
	si, _ := NewStudioIdentifier("")
	studios := si.GetAllStudios()

	if len(studios) == 0 {
		t.Error("Expected non-empty studios list")
	}

	// 檢查是否包含主要片商
	expectedStudios := []string{"S1", "MOODYZ", "PREMIUM", "FALENO", "KAWAII"}
	found := make(map[string]bool)

	for _, studio := range studios {
		found[studio] = true
	}

	for _, expected := range expectedStudios {
		if !found[expected] {
			t.Errorf("Expected studio %s not found in list", expected)
		}
	}
}

func TestGetPrefixes(t *testing.T) {
	si, _ := NewStudioIdentifier("")

	tests := []struct {
		name       string
		studioName string
		minCount   int
	}{
		{"S1 前綴", "S1", 3},
		{"MOODYZ 前綴", "MOODYZ", 3},
		{"PREMIUM 前綴", "PREMIUM", 3},
		{"未知片商", "UNKNOWN_STUDIO", 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			prefixes := si.GetPrefixes(tt.studioName)
			if len(prefixes) < tt.minCount {
				t.Errorf("GetPrefixes(%s) returned %d prefixes, want at least %d",
					tt.studioName, len(prefixes), tt.minCount)
			}
		})
	}
}

func TestLoadRulesFromFile(t *testing.T) {
	// 建立臨時測試檔案
	tmpDir := t.TempDir()
	testFile := filepath.Join(tmpDir, "test_studios.json")

	testData := `{
	"TEST_STUDIO": ["TEST", "TESTA"],
	"ANOTHER_STUDIO": ["ANO", "ANOB"]
}`

	if err := os.WriteFile(testFile, []byte(testData), 0644); err != nil {
		t.Fatal(err)
	}

	si, err := NewStudioIdentifier(testFile)
	if err != nil {
		t.Fatalf("Failed to load test file: %v", err)
	}

	// 測試是否正確載入
	if len(si.StudioPatterns) != 2 {
		t.Errorf("Expected 2 studios, got %d", len(si.StudioPatterns))
	}

	// 測試反向對應表是否正確建立
	if len(si.CodeToStudio) == 0 {
		t.Error("CodeToStudio map is empty")
	}

	// 調試：輸出反向對應表
	t.Logf("CodeToStudio map: %v", si.CodeToStudio)
	t.Logf("StudioPatterns: %v", si.StudioPatterns)

	// 測試番號識別
	if result := si.IdentifyStudio("TEST-123"); result != "TEST_STUDIO" {
		t.Errorf("IdentifyStudio(TEST-123) = %s, want TEST_STUDIO", result)
		t.Logf("Available prefixes in map: %v", si.CodeToStudio)
	}

	if result := si.IdentifyStudio("ANOB-456"); result != "ANOTHER_STUDIO" {
		t.Errorf("IdentifyStudio(ANOB-456) = %s, want ANOTHER_STUDIO", result)
	}
}

func TestBuildCodeToStudioMap(t *testing.T) {
	si, _ := NewStudioIdentifier("")

	// 檢查反向對應表是否正確建立
	if len(si.CodeToStudio) == 0 {
		t.Error("Expected non-empty CodeToStudio map")
	}

	// 測試特定對應
	tests := []struct {
		prefix   string
		expected string
	}{
		{"SONE", "S1"},
		{"SSIS", "S1"},
		{"MIDV", "MOODYZ"},
		{"IPX", "PREMIUM"},
		{"FSDSS", "FALENO"},
	}

	for _, tt := range tests {
		t.Run(tt.prefix, func(t *testing.T) {
			if studio, ok := si.CodeToStudio[tt.prefix]; !ok {
				t.Errorf("Expected prefix %s to be in map", tt.prefix)
			} else if studio != tt.expected {
				t.Errorf("CodeToStudio[%s] = %s, want %s", tt.prefix, studio, tt.expected)
			}
		})
	}
}
