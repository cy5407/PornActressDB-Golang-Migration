package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"actress-classifier/pkg/safefile"
	"actress-classifier/pkg/studio"
)

func identifyCmd(args []string) {
	fs := flag.NewFlagSet("identify", flag.ExitOnError)
	batchFile := fs.String("batch", "", "批次處理：從檔案讀取番號列表")
	rulesFile := fs.String("rules", "studios.json", "片商規則檔案路徑")
	showPrefixes := fs.Bool("prefixes", false, "顯示指定片商的所有前綴")
	listStudios := fs.Bool("list", false, "列出所有片商")
	checkMajor := fs.Bool("major", false, "檢查是否為大片商")
	jsonOutput := fs.Bool("json", false, "以 JSON 格式輸出")
	parseFlagsOrExit(fs, args)

	identifier, err := studio.NewStudioIdentifier(*rulesFile)
	if err != nil {
		printWarning("無法載入片商規則檔案，使用預設規則: %v", err)
	}

	if *listStudios {
		studios := identifier.GetAllStudios()
		if *jsonOutput {
			results := make([]map[string]any, 0, len(studios))
			for _, s := range studios {
				results = append(results, map[string]any{"studio": s, "is_major": identifier.IsMajorStudio(s)})
			}
			outputJSON(results)
			return
		}
		for _, s := range studios {
			isMajor := ""
			if identifier.IsMajorStudio(s) {
				isMajor = " (大片商)"
			}
			fmt.Printf("%s%s\n", s, isMajor)
		}
		return
	}

	if *showPrefixes {
		if len(fs.Args()) == 0 {
			printError("請指定片商名稱", "用法: classifier.exe identify -prefixes <片商名稱>")
			os.Exit(1)
		}
		studioName := fs.Args()[0]
		prefixes := identifier.GetPrefixes(studioName)
		if *jsonOutput {
			outputJSON(map[string]any{"studio": studioName, "prefixes": prefixes})
			return
		}
		if len(prefixes) == 0 {
			fmt.Printf("片商 %s 沒有註冊的前綴\n", studioName)
		} else {
			fmt.Printf("片商 %s 的前綴: %s\n", studioName, strings.Join(prefixes, ", "))
		}
		return
	}

	if *batchFile != "" {
		data, err := safefile.ReadFile(*batchFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "錯誤: 無法讀取批次檔案: %v\n", err)
			os.Exit(1)
		}
		codes := strings.Split(string(data), "\n")
		results := make([]map[string]string, 0)
		for _, code := range codes {
			code = strings.TrimSpace(code)
			if code == "" {
				continue
			}
			studioName := identifier.IdentifyStudio(code)
			result := map[string]string{"code": code, "studio": studioName}
			if *checkMajor {
				result["is_major"] = fmt.Sprintf("%t", identifier.IsMajorStudio(studioName))
			}
			results = append(results, result)
		}
		outputJSON(results)
		return
	}

	if len(fs.Args()) == 0 {
		printError("請指定番號", "用法: classifier.exe identify <番號>")
		os.Exit(1)
	}
	code := fs.Args()[0]
	studioName := identifier.IdentifyStudio(code)
	result := map[string]any{"code": code, "studio": studioName}
	if *checkMajor {
		result["is_major"] = identifier.IsMajorStudio(studioName)
	}
	outputJSON(result)
}
