package main

import (
	"testing"

	"actress-classifier/pkg/database"
)

func TestParseHistoryCommandOptions_PreservesRollbackLast(t *testing.T) {
	opts, remaining := parseHistoryCommandOptions("rollback", []string{"--last", "-log-dir", "custom-logs", "-json"})

	if opts.logDir != "custom-logs" {
		t.Fatalf("logDir = %q, want custom-logs", opts.logDir)
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "--last" {
		t.Fatalf("remaining = %#v, want [\"--last\"]", remaining)
	}
}

func TestParseDBCommandOptions_ParsesFlagsAndRemainingArgs(t *testing.T) {
	opts, remaining := parseDBCommandOptions("list", []string{"-data-dir", "custom-db", "-json", "-full", "CODE-001"})

	if opts.dataDir != "custom-db" {
		t.Fatalf("dataDir = %q, want custom-db", opts.dataDir)
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if !opts.fullOutput {
		t.Fatal("fullOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "CODE-001" {
		t.Fatalf("remaining = %#v, want [\"CODE-001\"]", remaining)
	}
}

func TestParseMoveCommandOptions_ParsesBatchAndStrategy(t *testing.T) {
	opts := parseMoveCommandOptions([]string{"-batch", "moves.json", "-strategy", "rename", "-dry-run", "-log-dir", "custom-logs"})

	if opts.batch != "moves.json" {
		t.Fatalf("batch = %q, want moves.json", opts.batch)
	}
	if opts.strategy != "rename" {
		t.Fatalf("strategy = %q, want rename", opts.strategy)
	}
	if !opts.dryRun {
		t.Fatal("dryRun should be true")
	}
	if opts.logDir != "custom-logs" {
		t.Fatalf("logDir = %q, want custom-logs", opts.logDir)
	}
}

func TestParseIdentifyCommandOptions_ParsesFlagsAndArgs(t *testing.T) {
	opts, remaining := parseIdentifyCommandOptions([]string{"-rules", "custom.json", "-major", "-json", "STARS-001"})

	if opts.rulesFile != "custom.json" {
		t.Fatalf("rulesFile = %q, want custom.json", opts.rulesFile)
	}
	if !opts.checkMajor {
		t.Fatal("checkMajor should be true")
	}
	if !opts.jsonOutput {
		t.Fatal("jsonOutput should be true")
	}
	if len(remaining) != 1 || remaining[0] != "STARS-001" {
		t.Fatalf("remaining = %#v, want [\"STARS-001\"]", remaining)
	}
}

func TestParseIdentifyCommandOptions_ParsesNormalizeFlags(t *testing.T) {
	opts, remaining := parseIdentifyCommandOptions([]string{
		"-normalize",
		"-studio", "MOODYZ DIVA",
		"-code", "SSIS-123",
		"-rules", "custom.json",
	})

	if !opts.normalizeStudio {
		t.Fatal("normalizeStudio should be true")
	}
	if opts.normalizeInput != "MOODYZ DIVA" {
		t.Fatalf("normalizeInput = %q, want MOODYZ DIVA", opts.normalizeInput)
	}
	if opts.normalizeCode != "SSIS-123" {
		t.Fatalf("normalizeCode = %q, want SSIS-123", opts.normalizeCode)
	}
	if opts.rulesFile != "custom.json" {
		t.Fatalf("rulesFile = %q, want custom.json", opts.rulesFile)
	}
	if len(remaining) != 0 {
		t.Fatalf("remaining = %#v, want empty", remaining)
	}
}

func TestBuildStudioFixPlan_RequiresForceForKnownStudio(t *testing.T) {
	video := database.NewVideo("STARS-001")
	video.Studio = "S1"

	plan := buildStudioFixPlan(video, "MOODYZ", false)
	if plan.status != studioFixAlreadyCorrect {
		t.Fatalf("status = %q, want %q", plan.status, studioFixAlreadyCorrect)
	}
}

func TestBuildStudioFixPlan_UpdatesUnknownStudio(t *testing.T) {
	video := database.NewVideo("SSIS-001")
	video.Studio = "UNKNOWN"

	plan := buildStudioFixPlan(video, "S1", false)
	if plan.status != studioFixUpdate {
		t.Fatalf("status = %q, want %q", plan.status, studioFixUpdate)
	}
	if plan.change.From != "UNKNOWN" || plan.change.To != "S1" {
		t.Fatalf("change = %#v, want UNKNOWN -> S1", plan.change)
	}
}
