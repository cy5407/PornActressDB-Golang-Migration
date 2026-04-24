// Package services provides shared business logic for the Wails backend.
package services

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// Preferences holds all application settings persisted in config.ini.
type Preferences struct {
	// [database]
	JSONDataDir string `json:"json_data_dir"`
	// [paths]
	DefaultInputDir string `json:"default_input_dir"`
	// [search]
	BatchSize               int     `json:"batch_size"`
	ThreadCount             int     `json:"thread_count"`
	BatchDelay              float64 `json:"batch_delay"`
	RequestTimeout          int     `json:"request_timeout"`
	AvwikiConcurrentEnabled bool    `json:"avwiki_concurrent_enabled"`
	AvwikiMaxConcurrent     int     `json:"avwiki_max_concurrent"`
	PythonExePath           string  `json:"python_exe_path"`
	// [classification]
	Mode                 string `json:"mode"`
	AutoApplyPreferences bool   `json:"auto_apply_preferences"`
	// [cache]
	CacheTTLDays         int  `json:"cache_ttl_days"`
	CacheMaxSizeMB       int  `json:"cache_max_size_mb"`
	CacheAutoCleanOnExit bool `json:"cache_auto_cleanup_on_exit"`
	// [go_integration]
	GoEnabled            bool   `json:"go_enabled"`
	GoExePath            string `json:"go_exe_path"`
	ScanWorkers          int    `json:"scan_workers"`
	MoveConflictStrategy string `json:"move_conflict_strategy"`
	EnableOperationLog   bool   `json:"enable_operation_log"`
	LogDir               string `json:"log_dir"`
}

// DefaultPreferences returns the built-in default settings.
func DefaultPreferences() Preferences {
	return Preferences{
		JSONDataDir:             "data/json_db",
		DefaultInputDir:         "",
		BatchSize:               10,
		ThreadCount:             5,
		BatchDelay:              2.0,
		RequestTimeout:          20,
		AvwikiConcurrentEnabled: true,
		AvwikiMaxConcurrent:     15,
		PythonExePath:           "",
		Mode:                    "interactive",
		AutoApplyPreferences:    true,
		CacheTTLDays:            7,
		CacheMaxSizeMB:          500,
		CacheAutoCleanOnExit:    true,
		GoEnabled:               true,
		GoExePath:               "",
		ScanWorkers:             10,
		MoveConflictStrategy:    "skip",
		EnableOperationLog:      true,
		LogDir:                  "logs",
	}
}

// ConfigService centralises config.ini reading and writing.
type ConfigService struct {
	cfgPath string
}

// NewConfigService creates a ConfigService backed by the given config file path.
func NewConfigService(cfgPath string) *ConfigService {
	return &ConfigService{cfgPath: cfgPath}
}

// CfgPath returns the resolved path to config.ini.
func (c *ConfigService) CfgPath() string {
	return c.cfgPath
}

// Load reads preferences from config.ini; returns defaults on file-not-found.
func (c *ConfigService) Load() (Preferences, error) {
	prefs := DefaultPreferences()
	data, err := os.ReadFile(c.cfgPath)
	if err != nil {
		return prefs, nil // defaults on missing file
	}
	parseIni(string(data), &prefs)
	return prefs, nil
}

// Save writes preferences to config.ini, overwriting any existing content.
func (c *ConfigService) Save(prefs Preferences) error {
	content := buildIni(prefs)
	return os.WriteFile(c.cfgPath, []byte(content), 0600)
}

// Reset writes the built-in defaults to config.ini.
func (c *ConfigService) Reset() error {
	return c.Save(DefaultPreferences())
}

// ============================================================================
// INI parser / writer
// ============================================================================

// ParseIni parses ini content into the Preferences struct pointed to by p.
func ParseIni(content string, p *Preferences) {
	parseIni(content, p)
}

// BuildIni serialises a Preferences struct into an ini-formatted string.
func BuildIni(p Preferences) string {
	return buildIni(p)
}

func parseIni(content string, p *Preferences) {
	var section string
	scanner := bufio.NewScanner(strings.NewReader(content))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, ";") || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = line[1 : len(line)-1]
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		k, v := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
		setField(p, section, k, v)
	}
}

func setField(p *Preferences, section, key, value string) {
	boolVal := func(s string) bool {
		s = strings.ToLower(s)
		return s == "true" || s == "1" || s == "yes"
	}
	intVal := func(s string) int {
		var n int
		fmt.Sscanf(s, "%d", &n)
		return n
	}
	floatVal := func(s string) float64 {
		var f float64
		fmt.Sscanf(s, "%f", &f)
		return f
	}

	switch section + "." + key {
	case "database.json_data_dir":
		p.JSONDataDir = value
	case "paths.default_input_dir":
		p.DefaultInputDir = value
	case "search.batch_size":
		p.BatchSize = intVal(value)
	case "search.thread_count":
		p.ThreadCount = intVal(value)
	case "search.batch_delay":
		p.BatchDelay = floatVal(value)
	case "search.request_timeout":
		p.RequestTimeout = intVal(value)
	case "search.avwiki_concurrent_enabled":
		p.AvwikiConcurrentEnabled = boolVal(value)
	case "search.avwiki_max_concurrent":
		p.AvwikiMaxConcurrent = intVal(value)
	case "search.python_exe_path":
		p.PythonExePath = value
	case "classification.mode":
		p.Mode = value
	case "classification.auto_apply_preferences":
		p.AutoApplyPreferences = boolVal(value)
	case "cache.ttl_days":
		p.CacheTTLDays = intVal(value)
	case "cache.max_size_mb":
		p.CacheMaxSizeMB = intVal(value)
	case "cache.auto_cleanup_on_exit":
		p.CacheAutoCleanOnExit = boolVal(value)
	case "go_integration.enabled":
		p.GoEnabled = boolVal(value)
	case "go_integration.exe_path":
		p.GoExePath = value
	case "go_integration.scan_workers":
		p.ScanWorkers = intVal(value)
	case "go_integration.move_conflict_strategy":
		p.MoveConflictStrategy = value
	case "go_integration.enable_operation_log":
		p.EnableOperationLog = boolVal(value)
	case "go_integration.log_dir":
		p.LogDir = value
	}
}

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

func buildIni(p Preferences) string {
	var sb strings.Builder
	sb.WriteString("[database]\n")
	sb.WriteString("json_data_dir = " + p.JSONDataDir + "\n\n")

	sb.WriteString("[paths]\n")
	sb.WriteString("default_input_dir = " + p.DefaultInputDir + "\n\n")

	sb.WriteString("[search]\n")
	sb.WriteString(fmt.Sprintf("batch_size = %d\n", p.BatchSize))
	sb.WriteString(fmt.Sprintf("thread_count = %d\n", p.ThreadCount))
	sb.WriteString(fmt.Sprintf("batch_delay = %.1f\n", p.BatchDelay))
	sb.WriteString(fmt.Sprintf("request_timeout = %d\n", p.RequestTimeout))
	sb.WriteString("avwiki_concurrent_enabled = " + boolStr(p.AvwikiConcurrentEnabled) + "\n")
	sb.WriteString(fmt.Sprintf("avwiki_max_concurrent = %d\n", p.AvwikiMaxConcurrent))
	sb.WriteString("python_exe_path = " + p.PythonExePath + "\n\n")

	sb.WriteString("[classification]\n")
	sb.WriteString("mode = " + p.Mode + "\n")
	sb.WriteString("auto_apply_preferences = " + boolStr(p.AutoApplyPreferences) + "\n\n")

	sb.WriteString("[cache]\n")
	sb.WriteString(fmt.Sprintf("ttl_days = %d\n", p.CacheTTLDays))
	sb.WriteString(fmt.Sprintf("max_size_mb = %d\n", p.CacheMaxSizeMB))
	sb.WriteString("auto_cleanup_on_exit = " + boolStr(p.CacheAutoCleanOnExit) + "\n\n")

	sb.WriteString("[go_integration]\n")
	sb.WriteString("enabled = " + boolStr(p.GoEnabled) + "\n")
	sb.WriteString("exe_path = " + p.GoExePath + "\n")
	sb.WriteString(fmt.Sprintf("scan_workers = %d\n", p.ScanWorkers))
	sb.WriteString("move_conflict_strategy = " + p.MoveConflictStrategy + "\n")
	sb.WriteString("enable_operation_log = " + boolStr(p.EnableOperationLog) + "\n")
	sb.WriteString("log_dir = " + p.LogDir + "\n")

	return sb.String()
}
