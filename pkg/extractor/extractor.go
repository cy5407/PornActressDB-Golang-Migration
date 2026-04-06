package extractor

import (
	"path/filepath"
	"regexp"
	"strings"
)

// SupportedFormats は対応している動画ファイル拡張子の一覧（main.go との重複を避けるための exported 定数）
var SupportedFormats = []string{".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"}

// CodeExtractor handles video code extraction from filenames
type CodeExtractor struct {
	supportedFormats []string
	codePatterns     []codePattern
	validPatterns    []*regexp.Regexp
	skipPatterns     []*regexp.Regexp

	// cleanFilename 用正規表達式（預編譯，避免重複編譯）
	bracketRe    *regexp.Regexp
	qualityRe    *regexp.Regexp
	h265Re       *regexp.Regexp
	resolutionRe *regexp.Regexp
	techSuffixRe *regexp.Regexp
	versionRe    *regexp.Regexp
	siteRe       *regexp.Regexp
	spaceRe      *regexp.Regexp
	hyphenRe     *regexp.Regexp

	// normalizeCode 用正規表達式
	letterRe *regexp.Regexp
	digitRe  *regexp.Regexp

	// validateCode 用正規表達式
	hasLetterRe *regexp.Regexp
	hasNumberRe *regexp.Regexp
}

type codePattern struct {
	regex      *regexp.Regexp
	formatName string
}

// NewCodeExtractor creates a new extractor instance
func NewCodeExtractor() *CodeExtractor {
	e := &CodeExtractor{
		supportedFormats: SupportedFormats,

		// cleanFilename 用正規表達式
		bracketRe:    regexp.MustCompile(`\[.*?\]|\(.*?\)|\{.*?\}`),
		qualityRe:    regexp.MustCompile(`(?i)[-_]?[CHch]\d*$`),
		h265Re:       regexp.MustCompile(`(?i)\.H265$`),
		resolutionRe: regexp.MustCompile(`(?i)[-_]?(1080p|720p|4K|HDR|HEVC|AVC|X264|X265)`),
		techSuffixRe: regexp.MustCompile(`(?i)(?:[-_ ]?(?:30FPS|60FPS|120FPS|2160P|1080P|720P))+$`),
		versionRe:    regexp.MustCompile(`(?i)[-_ ]?c\d*$`),
		siteRe:       regexp.MustCompile(`(?i)^([a-z0-9.-]+\.com[@-])`),
		spaceRe:      regexp.MustCompile(`\s+`),
		hyphenRe:     regexp.MustCompile(`-+`),

		// normalizeCode 用正規表達式
		letterRe: regexp.MustCompile(`[A-Z]+`),
		digitRe:  regexp.MustCompile(`\d+`),

		// validateCode 用正規表達式
		hasLetterRe: regexp.MustCompile(`[A-Z]`),
		hasNumberRe: regexp.MustCompile(`\d`),
	}

	// Code patterns (in priority order)
	e.codePatterns = []codePattern{
		{regexp.MustCompile(`([A-Z]{2,6}-\d{3,5})`), "標準格式"},
		{regexp.MustCompile(`([A-Z]{2,6}-\d{3,5})[A-Z]*`), "標準格式帶後綴"},
		{regexp.MustCompile(`([A-Z]{2,6}\d{3,5})`), "無橫槓格式"},
		{regexp.MustCompile(`([A-Z]{2,6}[._]\d{3,5})`), "特殊分隔符格式"},
		{regexp.MustCompile(`(\d{6}[-_]\d{3})`), "數字格式"},
	}

	// Validation patterns
	e.validPatterns = []*regexp.Regexp{
		regexp.MustCompile(`^[A-Z]{2,6}-\d{3,5}$`),
		regexp.MustCompile(`^[A-Z]{2,6}\d{3,5}$`),
		regexp.MustCompile(`^\d{6}-\d{3}$`),
	}

	// Skip patterns for FC2/PPV files
	e.skipPatterns = []*regexp.Regexp{
		regexp.MustCompile(`^FC2[-_]`),
		regexp.MustCompile(`^FC2PPV[-_]`),
		regexp.MustCompile(`^FC2\d`),
		regexp.MustCompile(`^PPV[-_]\d`),
		regexp.MustCompile(`^PPV\d`),
	}

	return e
}

// ExtractCode extracts video code from filename
func (e *CodeExtractor) ExtractCode(filename string) string {
	baseName := filepath.Base(filename)
	baseName = strings.TrimSuffix(baseName, filepath.Ext(baseName))

	// Skip FC2/PPV files
	if e.shouldSkip(baseName) {
		return ""
	}

	// Clean filename
	cleaned := strings.ToUpper(e.cleanFilename(baseName))

	// Try each pattern
	for _, pattern := range e.codePatterns {
		if match := pattern.regex.FindStringSubmatch(cleaned); match != nil {
			code := strings.ToUpper(match[1])
			code = e.normalizeCode(code)

			if e.validateCode(code) {
				return code
			}
		}
	}

	return ""
}

// cleanFilename removes noise from filename
func (e *CodeExtractor) cleanFilename(name string) string {
	// Remove brackets content [H265], (1080p), {字幕組}
	name = e.bracketRe.ReplaceAllString(name, "")

	// 移除尾端完整技術標籤，避免把 60FPS / 2160P 併入番號
	name = e.techSuffixRe.ReplaceAllString(name, "")

	// Remove quality/encoding markers
	name = e.qualityRe.ReplaceAllString(name, "")
	name = e.h265Re.ReplaceAllString(name, "")
	name = e.resolutionRe.ReplaceAllString(name, "")

	// Remove version markers
	name = e.versionRe.ReplaceAllString(name, "")

	// Remove site markers
	name = e.siteRe.ReplaceAllString(name, "")

	// Clean whitespace and hyphens
	name = e.spaceRe.ReplaceAllString(name, " ")
	name = strings.TrimSpace(name)
	name = e.hyphenRe.ReplaceAllString(name, "-")

	return name
}

// normalizeCode standardizes code format
func (e *CodeExtractor) normalizeCode(code string) string {
	// Replace . or _ with -
	code = strings.ReplaceAll(code, ".", "-")
	code = strings.ReplaceAll(code, "_", "-")

	// Add hyphen if missing (e.g., STARS707 -> STARS-707)
	if !strings.Contains(code, "-") {
		letters := e.letterRe.FindString(code)
		digits := e.digitRe.FindString(code)

		if letters != "" && digits != "" {
			code = letters + "-" + digits
		}
	}

	return code
}

// validateCode checks if code format is valid
func (e *CodeExtractor) validateCode(code string) bool {
	if len(code) < 4 || len(code) > 15 {
		return false
	}

	// Must contain both letters and numbers
	if !e.hasLetterRe.MatchString(code) || !e.hasNumberRe.MatchString(code) {
		return false
	}

	// Check against valid patterns
	for _, pattern := range e.validPatterns {
		if pattern.MatchString(code) {
			return true
		}
	}

	return false
}

// shouldSkip checks if file should be skipped (FC2/PPV)
func (e *CodeExtractor) shouldSkip(baseName string) bool {
	upper := strings.ToUpper(baseName)

	// Check skip patterns
	for _, pattern := range e.skipPatterns {
		if pattern.MatchString(upper) {
			return true
		}
	}

	// Check for FC2/PPV markers
	markers := []string{"FC2PPV", "FC2-PPV", "FC2_PPV"}
	for _, marker := range markers {
		if strings.Contains(upper, marker) {
			return true
		}
	}

	return false
}
