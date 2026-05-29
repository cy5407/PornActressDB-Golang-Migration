package extractor

import "testing"

func TestExtractCode(t *testing.T) {
	extractor := NewCodeExtractor()

	tests := []struct {
		filename string
		expected string
	}{
		{"STARS-707.mp4", "STARS-707"},
		{"ssis-020-4k.mp4", "SSIS-020"},
		{"ipx_123.mp4", "IPX-123"},
		{"SONE-240-60FPS.mp4", "SONE-240"},
		{"SONE-24060FPS.mp4", "SONE-240"},
		{"SONE-240-2160P.mp4", "SONE-240"},
		{"MIFD-0702160p.mp4", "MIFD-070"},
		{"FWAY-03160FPS.mp4", "FWAY-031"},
		{"SIRO-1234.mp4", "SIRO-1234"},
		{"STARS707.mp4", "STARS-707"},
		{"200GANA-3376.mp4", "200GANA-3376"},
		{"259LUXU-1880.mp4", "259LUXU-1880"},
		{"300MIUM-1357.mp4", "300MIUM-1357"},
		{"SSIS-999[H265].mp4", "SSIS-999"},
		{"IPX-123 (1080p).mp4", "IPX-123"},
		{"MIDV-456-C.mp4", "MIDV-456"},
		{"JUL-789.H265.mp4", "JUL-789"},
		{"CAWD_123.mp4", "CAWD-123"},
		{"CAWD.456.mp4", "CAWD-456"},
		{"SONE-123CH.mp4", "SONE-123"},
		{"STARS-707CH.mp4", "STARS-707"},
		{"MIDV-123A.mp4", "MIDV-123"},
		{"hhd800.com@MIAB-789.mp4", "MIAB-789"},
		{"489155.com@MIMK-273.mp4", "MIMK-273"},
		{"489155.com@NIMA-077-C.mp4", "NIMA-077"},
		{"abc123.com@STARS-001.mp4", "STARS-001"},
		{"FC2-PPV-123456.mp4", ""},
		{"FC2PPV-999999.mp4", ""},
		{"PPV-555555.mp4", ""},         // 6位數 PPV → FC2-PPV 業餘，skip
		{"PPV-32184.mp4", "PPV-32184"}, // 5位數 PPV → 片商番號，不 skip
		{"", ""},
	}

	for _, tt := range tests {
		result := extractor.ExtractCode(tt.filename)
		if result != tt.expected {
			t.Errorf("ExtractCode(%q) = %q; want %q", tt.filename, result, tt.expected)
		}
	}
}

func TestShouldSkip(t *testing.T) {
	extractor := NewCodeExtractor()

	tests := []struct {
		filename   string
		shouldSkip bool
	}{
		{"FC2-PPV-123456", true},
		{"FC2PPV-999999", true},
		{"FC2_PPV_888888", true},
		{"FC2-123456", true},  // FC2 開頭全 skip
		{"FC2ANYTHING", true}, // FC2 開頭全 skip
		{"PPV-777777", true},  // 6位數 → skip
		{"PPV-32184", false},  // 5位數 → 片商番號，不 skip
		{"STARS-707", false},
		{"SSIS-999", false},
	}

	for _, tt := range tests {
		result := extractor.shouldSkip(tt.filename)
		if result != tt.shouldSkip {
			t.Errorf("shouldSkip(%q) = %v; want %v", tt.filename, result, tt.shouldSkip)
		}
	}
}

func TestNormalizeCode(t *testing.T) {
	extractor := NewCodeExtractor()

	tests := []struct {
		input    string
		expected string
	}{
		{"STARS707", "STARS-707"},
		{"STARS.707", "STARS-707"},
		{"STARS_707", "STARS-707"},
		{"STARS-707", "STARS-707"},
	}

	for _, tt := range tests {
		result := extractor.normalizeCode(tt.input)
		if result != tt.expected {
			t.Errorf("normalizeCode(%q) = %q; want %q", tt.input, result, tt.expected)
		}
	}
}

func TestExtractCode_BracketPath(t *testing.T) {
	e := NewCodeExtractor()
	cases := map[string]string{
		"(STARS-707).mp4": "STARS-707",
		"[IPX-123].mp4":   "IPX-123",
		"（MIDV-456）.mp4":  "MIDV-456",
	}
	for in, want := range cases {
		if got := e.ExtractCode(in); got != want {
			t.Errorf("ExtractCode(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestValidateCode_RejectsBadLengths(t *testing.T) {
	e := NewCodeExtractor()
	for _, bad := range []string{"AB1", "X", "TOOLONGLONGCODE-99999"} {
		if e.validateCode(bad) {
			t.Errorf("validateCode(%q) = true, want false (length)", bad)
		}
	}
}

func TestValidateCode_RejectsLettersOnlyOrDigitsOnly(t *testing.T) {
	e := NewCodeExtractor()
	for _, bad := range []string{"ABCDEFG", "1234567"} {
		if e.validateCode(bad) {
			t.Errorf("validateCode(%q) = true, want false (no letter or no digit)", bad)
		}
	}
}

func TestValidateCode_RejectsUnknownShape(t *testing.T) {
	e := NewCodeExtractor()
	// Length OK, has letters+digits, but no validPattern matches.
	if e.validateCode("A1B2C3") {
		t.Error(`validateCode("A1B2C3") = true, want false (no shape match)`)
	}
}

func TestShouldSkip_FC2MarkerInsideName(t *testing.T) {
	e := NewCodeExtractor()
	// Does not start with FC2/PPV so skipPatterns miss; markers loop fires.
	if !e.shouldSkip("prefix_FC2_PPV_x") {
		t.Error(`shouldSkip("prefix_FC2_PPV_x") = false, want true (marker)`)
	}
	if !e.shouldSkip("foo-FC2PPV-bar") {
		t.Error(`shouldSkip("foo-FC2PPV-bar") = false, want true (marker)`)
	}
	if !e.shouldSkip("baz_FC2-PPV_qux") {
		t.Error(`shouldSkip("baz_FC2-PPV_qux") = false, want true (marker)`)
	}
}
