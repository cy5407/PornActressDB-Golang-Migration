package studio

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// StudioIdentifier 片商識別器
type StudioIdentifier struct {
	// StudioPatterns 片商前綴對應表 (studio_name -> prefixes)
	StudioPatterns map[string][]string
	// CodeToStudio 番號前綴到片商的反向對應 (prefix -> studio_name)
	CodeToStudio map[string]string
	// StudioAliases 片商別名對照表
	StudioAliases map[string]string
}

// MajorStudios 大片商清單
var MajorStudios = map[string]bool{
	"S1":        true,
	"MOODYZ":    true,
	"PREMIUM":   true,
	"FALENO":    true,
	"KAWAII":    true,
	"ATTACKERS": true,
	"E-BODY":    true,
	"SOD":       true,
	"PRESTIGE":  true,
	"MADONNA":   true,
	"OPPAI":     true,
	"FITCH":     true,
	"WANZ":      true,
}

// NewStudioIdentifier 建立片商識別器
func NewStudioIdentifier(rulesFile string) (*StudioIdentifier, error) {
	si := &StudioIdentifier{
		StudioAliases: map[string]string{
			"MOODYZ DIVA":   "MOODYZ",
			"S1 NO.1 STYLE": "S1",
			"エスワン":          "S1",
			"FALENO star":   "FALENO",
			"FALENO TUBE":   "FALENO",
			"ファレノ":          "FALENO",
			"Premium":       "PREMIUM",
		},
	}

	// 載入 studios.json（即使失敗也繼續，使用預設規則）
	err := si.loadRules(rulesFile)

	// 建立反向對應表
	si.CodeToStudio = si.buildCodeToStudioMap()

	return si, err
}

// loadRules 載入片商規則檔案
func (si *StudioIdentifier) loadRules(rulesFile string) error {
	// 如果沒有指定檔案，使用預設路徑
	if rulesFile == "" {
		rulesFile = "studios.json"
	}

	// 嘗試從當前目錄或專案根目錄載入
	paths := []string{
		rulesFile,
		filepath.Join(".", rulesFile),
		filepath.Join("..", rulesFile),
		filepath.Join("..", "..", rulesFile),
	}

	var lastErr error
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			lastErr = err
			continue
		}

		// 成功讀取檔案
		if err := json.Unmarshal(data, &si.StudioPatterns); err != nil {
			return err
		}
		return nil
	}

	// 所有路徑都失敗，返回預設規則
	si.StudioPatterns = getDefaultRules()
	return lastErr
}

// getDefaultRules 取得預設片商規則
func getDefaultRules() map[string][]string {
	return map[string][]string{
		"S1":      {"SSIS", "SSNI", "SNIS", "SONE", "ONEZ", "OFJE", "SNOS"},
		"MOODYZ":  {"MIRD", "MIDD", "MIDV", "MIDE", "MIAB"},
		"PREMIUM": {"IPX", "IPZ", "IPZZ", "IDEA", "PRED"},
		"FALENO":  {"FSDSS", "FNS", "FADSS"},
		"KAWAII":  {"KAWD", "CAWD", "KWBD"},
	}
}

// buildCodeToStudioMap 建立番號前綴到片商的反向對應表
func (si *StudioIdentifier) buildCodeToStudioMap() map[string]string {
	mapping := make(map[string]string)
	for studio, prefixes := range si.StudioPatterns {
		for _, prefix := range prefixes {
			mapping[strings.ToUpper(prefix)] = studio
		}
	}
	return mapping
}

// IdentifyStudio 根據番號識別片商
func (si *StudioIdentifier) IdentifyStudio(code string) string {
	if code == "" {
		return "UNKNOWN"
	}

	// 提取番號前綴 (只取大寫字母部分)
	re := regexp.MustCompile(`^([A-Z]+)`)
	matches := re.FindStringSubmatch(strings.ToUpper(code))
	if len(matches) < 2 {
		return "UNKNOWN"
	}

	prefix := matches[1]
	if studio, ok := si.CodeToStudio[prefix]; ok {
		return studio
	}

	return "UNKNOWN"
}

// NormalizeStudioName 標準化片商名稱
func (si *StudioIdentifier) NormalizeStudioName(studioName string, videoCode string) string {
	// 優先使用番號判斷
	if videoCode != "" {
		studioFromCode := si.IdentifyStudio(videoCode)
		if studioFromCode != "UNKNOWN" {
			return studioFromCode
		}
	}

	if studioName == "" {
		return "UNKNOWN"
	}

	// 移除前後空白
	studioName = strings.TrimSpace(studioName)
	if studioName == "" {
		return "UNKNOWN"
	}

	// 檢查別名對照表（不區分大小寫）
	studioLower := strings.ToLower(studioName)
	for alias, canonical := range si.StudioAliases {
		if strings.ToLower(alias) == studioLower {
			return canonical
		}
	}

	// 檢查是否為片商代碼
	studioUpper := strings.ToUpper(studioName)
	if studio, ok := si.CodeToStudio[studioUpper]; ok {
		return studio
	}

	return studioName
}

// IsMajorStudio 判斷是否為大片商
func (si *StudioIdentifier) IsMajorStudio(studioName string) bool {
	return MajorStudios[studioName]
}

// GetAllStudios 取得所有片商名稱
func (si *StudioIdentifier) GetAllStudios() []string {
	studios := make([]string, 0, len(si.StudioPatterns))
	for studio := range si.StudioPatterns {
		studios = append(studios, studio)
	}
	return studios
}

// GetPrefixes 取得指定片商的所有前綴
func (si *StudioIdentifier) GetPrefixes(studioName string) []string {
	if prefixes, ok := si.StudioPatterns[studioName]; ok {
		return prefixes
	}
	return []string{}
}
