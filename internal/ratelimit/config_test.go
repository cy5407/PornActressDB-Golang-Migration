package ratelimit_test

import (
	"os"
	"path/filepath"
	"testing"

	"actress-classifier/internal/ratelimit"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLimitConfig_Validate(t *testing.T) {
	tests := []struct {
		name    string
		config  ratelimit.LimitConfig
		wantErr bool
	}{
		{
			name: "合法配置",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 1.0,
				BurstCapacity:     1,
			},
			wantErr: false,
		},
		{
			name: "合法配置 - 小數速率",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 0.5,
				BurstCapacity:     1,
			},
			wantErr: false,
		},
		{
			name: "合法配置 - 高速率",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 10.0,
				BurstCapacity:     20,
			},
			wantErr: false,
		},
		{
			name: "非法配置 - RPS 為 0",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 0,
				BurstCapacity:     1,
			},
			wantErr: true,
		},
		{
			name: "非法配置 - RPS 為負數",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: -1.0,
				BurstCapacity:     1,
			},
			wantErr: true,
		},
		{
			name: "非法配置 - Burst 為 0",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 1.0,
				BurstCapacity:     0,
			},
			wantErr: true,
		},
		{
			name: "非法配置 - Burst 為負數",
			config: ratelimit.LimitConfig{
				RequestsPerSecond: 1.0,
				BurstCapacity:     -1,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.config.Validate()
			if tt.wantErr {
				assert.Error(t, err, "預期驗證失敗")
			} else {
				assert.NoError(t, err, "預期驗證成功")
			}
		})
	}
}

func TestDefaultConfig(t *testing.T) {
	// 驗證預設配置合法
	err := ratelimit.DefaultConfig.Validate()
	assert.NoError(t, err, "預設配置應該合法")

	// 驗證預設配置值
	assert.Equal(t, 1.0, ratelimit.DefaultConfig.RequestsPerSecond)
	assert.Equal(t, 1, ratelimit.DefaultConfig.BurstCapacity)
}

func TestPresetConfigs(t *testing.T) {
	// 驗證所有預設配置都合法
	for domain, config := range ratelimit.PresetConfigs {
		t.Run(domain, func(t *testing.T) {
			err := config.Validate()
			assert.NoError(t, err, "預設網域配置 %s 應該合法", domain)
		})
	}

	// 驗證預期的網域存在
	expectedDomains := []string{"javdb.com", "av-wiki.net", "chiba-f.com"}
	for _, domain := range expectedDomains {
		_, exists := ratelimit.PresetConfigs[domain]
		assert.True(t, exists, "預期網域 %s 應該存在", domain)
	}
}

func TestLoadConfigFromJSON(t *testing.T) {
	tests := []struct {
		name    string
		json    string
		wantErr bool
		check   func(t *testing.T, cfg *ratelimit.ConfigFile)
	}{
		{
			name: "合法 JSON",
			json: `{
				"version": "1.0",
				"default_config": {
					"requests_per_second": 1.0,
					"burst_capacity": 1
				},
				"domains": {
					"javdb.com": {
						"requests_per_second": 1.0,
						"burst_capacity": 1
					},
					"av-wiki.net": {
						"requests_per_second": 2.0,
						"burst_capacity": 2
					}
				}
			}`,
			wantErr: false,
			check: func(t *testing.T, cfg *ratelimit.ConfigFile) {
				assert.Equal(t, "1.0", cfg.Version)
				assert.Equal(t, 2, len(cfg.Domains))
			},
		},
		{
			name: "缺少 version",
			json: `{
				"default_config": {
					"requests_per_second": 1.0,
					"burst_capacity": 1
				},
				"domains": {}
			}`,
			wantErr: true,
		},
		{
			name:    "非法 JSON 格式",
			json:    `{invalid json}`,
			wantErr: true,
		},
		{
			name: "預設配置無效",
			json: `{
				"version": "1.0",
				"default_config": {
					"requests_per_second": 0,
					"burst_capacity": 1
				},
				"domains": {}
			}`,
			wantErr: true,
		},
		{
			name: "網域配置無效",
			json: `{
				"version": "1.0",
				"default_config": {
					"requests_per_second": 1.0,
					"burst_capacity": 1
				},
				"domains": {
					"test.com": {
						"requests_per_second": -1.0,
						"burst_capacity": 1
					}
				}
			}`,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg, err := ratelimit.LoadConfigFromJSON([]byte(tt.json))
			if tt.wantErr {
				assert.Error(t, err)
				assert.Nil(t, cfg)
			} else {
				assert.NoError(t, err)
				require.NotNil(t, cfg)
				if tt.check != nil {
					tt.check(t, cfg)
				}
			}
		})
	}
}

func TestLoadConfigFromFile(t *testing.T) {
	// 建立臨時配置檔案
	tmpDir := t.TempDir()
	configPath := filepath.Join(tmpDir, "config.json")

	validJSON := `{
		"version": "1.0",
		"default_config": {
			"requests_per_second": 1.0,
			"burst_capacity": 1
		},
		"domains": {
			"javdb.com": {
				"requests_per_second": 1.0,
				"burst_capacity": 1
			}
		}
	}`

	err := os.WriteFile(configPath, []byte(validJSON), 0644)
	require.NoError(t, err)

	// 測試載入合法檔案
	t.Run("載入合法配置檔案", func(t *testing.T) {
		cfg, err := ratelimit.LoadConfigFromFile(configPath)
		assert.NoError(t, err)
		require.NotNil(t, cfg)
		assert.Equal(t, "1.0", cfg.Version)
		assert.Equal(t, 1, len(cfg.Domains))
	})

	// 測試檔案不存在
	t.Run("檔案不存在", func(t *testing.T) {
		cfg, err := ratelimit.LoadConfigFromFile(filepath.Join(tmpDir, "notexist.json"))
		assert.Error(t, err)
		assert.Nil(t, cfg)
	})

	// 測試非法 JSON 檔案
	t.Run("非法 JSON 檔案", func(t *testing.T) {
		invalidPath := filepath.Join(tmpDir, "invalid.json")
		err := os.WriteFile(invalidPath, []byte("{invalid}"), 0644)
		require.NoError(t, err)

		cfg, err := ratelimit.LoadConfigFromFile(invalidPath)
		assert.Error(t, err)
		assert.Nil(t, cfg)
	})
}
