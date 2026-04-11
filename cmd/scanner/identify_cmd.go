package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"actress-classifier/pkg/safefile"
	"actress-classifier/pkg/studio"
)

type identifyCommandOptions struct {
	batchFile    string
	rulesFile    string
	showPrefixes bool
	listStudios  bool
	checkMajor   bool
	jsonOutput   bool
}

func identifyCmd(args []string) {
	opts, remaining := parseIdentifyCommandOptions(args)
	identifier, err := studio.NewStudioIdentifier(opts.rulesFile)
	if err != nil {
		printWarning("無法載入片商規則檔案，使用預設規則: %v", err)
	}
	if handleIdentifyListing(opts, remaining, identifier) {
		return
	}
	if opts.batchFile != "" {
		runIdentifyBatch(opts, identifier)
		return
	}
	runIdentifySingle(opts, remaining, identifier)
}

func parseIdentifyCommandOptions(args []string) (identifyCommandOptions, []string) {
	fs := flag.NewFlagSet("identify", flag.ExitOnError)
	batchFile := fs.String("batch", "", "批次處理：從檔案讀取番號列表")
	rulesFile := fs.String("rules", "studios.json", "片商規則檔案路徑")
	showPrefixes := fs.Bool("prefixes", false, "顯示指定片商的所有前綴")
	listStudios := fs.Bool("list", false, "列出所有片商")
	checkMajor := fs.Bool("major", false, "檢查是否為大片商")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	parseFlagsOrExit(fs, args)
	return identifyCommandOptions{
		batchFile:    *batchFile,
		rulesFile:    *rulesFile,
		showPrefixes: *showPrefixes,
		listStudios:  *listStudios,
		checkMajor:   *checkMajor,
		jsonOutput:   *jsonOutput,
	}, fs.Args()
}

func handleIdentifyListing(opts identifyCommandOptions, remaining []string, identifier *studio.StudioIdentifier) bool {
	if opts.listStudios {
		outputStudios(opts, identifier)
		return true
	}
	if opts.showPrefixes {
		outputStudioPrefixes(opts, remaining, identifier)
		return true
	}
	return false
}

func outputStudios(opts identifyCommandOptions, identifier *studio.StudioIdentifier) {
	studios := identifier.GetAllStudios()
	if opts.jsonOutput {
		results := make([]map[string]any, 0, len(studios))
		for _, studioName := range studios {
			results = append(results, map[string]any{"studio": studioName, "is_major": identifier.IsMajorStudio(studioName)})
		}
		outputJSON(results)
		return
	}
	for _, studioName := range studios {
		isMajor := ""
		if identifier.IsMajorStudio(studioName) {
			isMajor = " (大片商)"
		}
		fmt.Printf("%s%s\n", studioName, isMajor)
	}
}

func outputStudioPrefixes(opts identifyCommandOptions, remaining []string, identifier *studio.StudioIdentifier) {
	if len(remaining) == 0 {
		printError("請指定片商名稱", "用法: classifier.exe identify -prefixes <片商名稱>")
		os.Exit(1)
	}
	studioName := remaining[0]
	prefixes := identifier.GetPrefixes(studioName)
	if opts.jsonOutput {
		outputJSON(map[string]any{"studio": studioName, "prefixes": prefixes})
		return
	}
	if len(prefixes) == 0 {
		fmt.Printf("片商 %s 沒有註冊的前綴\n", studioName)
		return
	}
	fmt.Printf("片商 %s 的前綴: %s\n", studioName, strings.Join(prefixes, ", "))
}

func runIdentifyBatch(opts identifyCommandOptions, identifier *studio.StudioIdentifier) {
	data, err := safefile.ReadFile(opts.batchFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "錯誤: 無法讀取批次檔案: %v\n", err)
		os.Exit(1)
	}
	outputJSON(buildIdentifyBatchResults(string(data), opts.checkMajor, identifier))
}

func buildIdentifyBatchResults(raw string, checkMajor bool, identifier *studio.StudioIdentifier) []map[string]string {
	results := make([]map[string]string, 0)
	for _, code := range strings.Split(raw, "\n") {
		trimmed := strings.TrimSpace(code)
		if trimmed == "" {
			continue
		}
		studioName := identifier.IdentifyStudio(trimmed)
		result := map[string]string{"code": trimmed, "studio": studioName}
		if checkMajor {
			result["is_major"] = fmt.Sprintf("%t", identifier.IsMajorStudio(studioName))
		}
		results = append(results, result)
	}
	return results
}

func runIdentifySingle(opts identifyCommandOptions, remaining []string, identifier *studio.StudioIdentifier) {
	if len(remaining) == 0 {
		printError("請指定番號", "用法: classifier.exe identify <番號>")
		os.Exit(1)
	}
	code := remaining[0]
	studioName := identifier.IdentifyStudio(code)
	result := map[string]any{"code": code, "studio": studioName}
	if opts.checkMajor {
		result["is_major"] = identifier.IsMajorStudio(studioName)
	}
	outputJSON(result)
}
