package main

import "testing"

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
