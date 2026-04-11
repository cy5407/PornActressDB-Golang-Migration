package main

import (
"fmt"
"os"
"strings"
)

const (
ansiReset  = "\033[0m"
ansiBold   = "\033[1m"
ansiDim    = "\033[2m"
ansiRed    = "\033[31m"
ansiGreen  = "\033[32m"
ansiYellow = "\033[33m"
ansiCyan   = "\033[36m"
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
func colorBold(s string) string    { return colorize(ansiBold, s) }
func colorDim(s string) string     { return colorize(ansiDim+ansiGray, s) }
func colorCyan(s string) string    { return colorize(ansiCyan, s) }

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

type ProgressBar struct {
total   int
current int
width   int
label   string
enabled bool
}

func NewProgressBar(total int, label string) *ProgressBar {
return &ProgressBar{
total:   total,
current: 0,
width:   30,
label:   label,
enabled: !noColor && isTerminalDevice(os.Stderr),
}
}

func (p *ProgressBar) Increment() {
p.current++
p.render()
}

func (p *ProgressBar) render() {
if !p.enabled {
return
}
var line string
if p.total > 0 {
pct := float64(p.current) / float64(p.total)
if pct > 1 {
pct = 1
}
filled := int(pct * float64(p.width))
empty := p.width - filled
bar := strings.Repeat("=", filled)
if filled < p.width {
bar += ">"
empty--
}
bar += strings.Repeat(" ", empty)
line = fmt.Sprintf("\r%s [%s] %d/%d",
colorCyan(p.label), colorCyan(bar), p.current, p.total)
} else {
line = fmt.Sprintf("\r%s %s 個檔案",
colorCyan(p.label), colorBold(fmt.Sprintf("%d", p.current)))
}
fmt.Fprint(os.Stderr, line)
}

func (p *ProgressBar) Finish() {
if !p.enabled {
return
}
fmt.Fprintln(os.Stderr)
}