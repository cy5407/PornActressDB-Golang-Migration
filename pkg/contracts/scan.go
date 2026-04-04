package contracts

// ScanResult 定義 scan CLI 的 JSON 輸出 DTO。
type ScanResult struct {
	Path string `json:"path"`
	Code string `json:"code"`
}
