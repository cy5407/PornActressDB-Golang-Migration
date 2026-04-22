package main

import (
	"fmt"
	"os"
)

const (
	ansiReset  = "\033[0m"
	ansiDim    = "\033[2m"
	ansiRed    = "\033[31m"
	ansiGreen  = "\033[32m"
	ansiYellow = "\033[33m"
	ansiGray   = "\033[90m"
)

var noColor = func() bool {
	if _, ok := os.LookupEnv("NO_COLOR"); ok {
		return true
	}
	return !isTerminalDevice(os.Stderr)
}()

func isTerminalDevice(f *os.File) bool {
	fi, err := f.Stat()
	if err != nil {
		return false
	}
	return (fi.Mode() & os.ModeCharDevice) != 0
}

func colorize(code, s string) string {
	if noColor {
		return s
	}
	return code + s + ansiReset
}

func colorSuccess(s string) string { return colorize(ansiGreen, s) }
func colorErr(s string) string     { return colorize(ansiRed, s) }
func colorWarn(s string) string    { return colorize(ansiYellow, s) }
func colorDim(s string) string { return colorize(ansiDim+ansiGray, s) }

func printSuccess(format string, args ...any) {
	fmt.Fprintln(os.Stderr, colorSuccess("✅ "+fmt.Sprintf(format, args...)))
}

func printError(msg string, hint ...string) {
	fmt.Fprintln(os.Stderr, colorErr("❌ 錯誤: ")+msg)
	for _, h := range hint {
		fmt.Fprintln(os.Stderr, colorDim("   提示: "+h))
	}
}

func printWarning(format string, args ...any) {
	fmt.Fprintln(os.Stderr, colorWarn("⚠️  警告: ")+fmt.Sprintf(format, args...))
}
