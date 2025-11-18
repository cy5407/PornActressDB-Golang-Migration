package extractor

import (
	"path/filepath"
	"regexp"
	"strings"
)

// CodeExtractor handles video code extraction from filenames
type CodeExtractor struct {
	supportedFormats []string
	codePatterns     []codePattern
	validPatterns    []*regexp.Regexp
	skipPatterns     []*regexp.Regexp
}

type codePattern struct {
	regex      *regexp.Regexp
	formatName string
}

// NewCodeExtractor creates a new extractor instance
func NewCodeExtractor() *CodeExtractor {
	e := &CodeExtractor{
		supportedFormats: []string{".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".m2ts"},
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
	cleaned := e.cleanFilename(baseName)

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
	bracketRe := regexp.MustCompile(`\[.*?\]|\(.*?\)|\{.*?\}`)
	name = bracketRe.ReplaceAllString(name, "")

	// Remove quality/encoding markers
	qualityRe := regexp.MustCompile(`(?i)[-_]?[CHch]\d*$`)
	name = qualityRe.ReplaceAllString(name, "")

	h265Re := regexp.MustCompile(`(?i)\.H265$`)
	name = h265Re.ReplaceAllString(name, "")

	resolutionRe := regexp.MustCompile(`(?i)[-_]?(1080p|720p|4K|HDR|HEVC|AVC|X264|X265)`)
	name = resolutionRe.ReplaceAllString(name, "")

	// Remove version markers
	versionRe := regexp.MustCompile(`(?i)[-_ ]?c\d*$`)
	name = versionRe.ReplaceAllString(name, "")

	// Remove site markers
	siteRe := regexp.MustCompile(`(?i)^(hhd800\.com@|xxx\.com-)`)
	name = siteRe.ReplaceAllString(name, "")

	// Clean whitespace and hyphens
	spaceRe := regexp.MustCompile(`\s+`)
	name = spaceRe.ReplaceAllString(name, " ")
	name = strings.TrimSpace(name)

	hyphenRe := regexp.MustCompile(`-+`)
	name = hyphenRe.ReplaceAllString(name, "-")

	return name
}

// normalizeCode standardizes code format
func (e *CodeExtractor) normalizeCode(code string) string {
	// Replace . or _ with -
	code = strings.ReplaceAll(code, ".", "-")
	code = strings.ReplaceAll(code, "_", "-")

	// Add hyphen if missing (e.g., STARS707 -> STARS-707)
	if !strings.Contains(code, "-") {
		letterRe := regexp.MustCompile(`[A-Z]+`)
		digitRe := regexp.MustCompile(`\d+`)

		letters := letterRe.FindString(code)
		digits := digitRe.FindString(code)

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
	hasLetter := regexp.MustCompile(`[A-Z]`).MatchString(code)
	hasNumber := regexp.MustCompile(`\d`).MatchString(code)

	if !hasLetter || !hasNumber {
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
