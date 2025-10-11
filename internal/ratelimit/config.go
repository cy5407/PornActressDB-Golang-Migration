package ratelimit

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
)

// LimitConfig 定義單一網域的限流配置
type LimitConfig struct {
	// RequestsPerSecond 每秒允許的請求數
	// 必須大於 0。可以是小數（如 0.5 表示每 2 秒 1 個請求）
	RequestsPerSecond float64 `json:"requests_per_second"`

	// BurstCapacity burst 容量（可累積的 token 數）
	// 必須至少為 1
	BurstCapacity int `json:"burst_capacity"`
}

// Validate 驗證配置參數的合法性
func (c LimitConfig) Validate() error {
	if c.RequestsPerSecond <= 0 {
		return fmt.Errorf("%w: RequestsPerSecond 必須大於 0，當前值: %.2f", ErrInvalidConfig, c.RequestsPerSecond)
	}
	if c.BurstCapacity < 1 {
		return fmt.Errorf("%w: BurstCapacity 必須至少為 1，當前值: %d", ErrInvalidConfig, c.BurstCapacity)
	}
	return nil
}

// DefaultConfig 預設限流配置（保守設定：1 請求/秒）
var DefaultConfig = LimitConfig{
	RequestsPerSecond: 1.0,
	BurstCapacity:     1,
}

// PresetConfigs 預設的網域限流配置
var PresetConfigs = map[string]LimitConfig{
	"javdb.com":   {RequestsPerSecond: 1.0, BurstCapacity: 1},
	"av-wiki.net": {RequestsPerSecond: 2.0, BurstCapacity: 2},
	"chiba-f.com": {RequestsPerSecond: 1.0, BurstCapacity: 1},
}

// ConfigFile 配置檔案結構
type ConfigFile struct {
	Version       string                 `json:"version"`
	DefaultConfig LimitConfig            `json:"default_config"`
	Domains       map[string]LimitConfig `json:"domains"`
}

// LoadConfigFromFile 從檔案載入配置
func LoadConfigFromFile(path string) (*ConfigFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("讀取配置檔案失敗: %w", err)
	}

	return LoadConfigFromJSON(data)
}

// LoadConfigFromJSON 從 JSON 資料載入配置
func LoadConfigFromJSON(data []byte) (*ConfigFile, error) {
	var config ConfigFile
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("解析 JSON 配置失敗: %w", err)
	}

	// 驗證必填欄位
	if config.Version == "" {
		return nil, errors.New("配置檔案缺少 version 欄位")
	}

	// 驗證預設配置
	if err := config.DefaultConfig.Validate(); err != nil {
		return nil, fmt.Errorf("預設配置無效: %w", err)
	}

	// 驗證所有網域配置
	for domain, cfg := range config.Domains {
		if err := cfg.Validate(); err != nil {
			return nil, fmt.Errorf("網域 %s 的配置無效: %w", domain, err)
		}
	}

	return &config, nil
}
