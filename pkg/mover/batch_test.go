package mover

import (
	"context"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// TestBatchMove_SerialExecutionInvariant 鎖住 BatchMove 嚴格序列執行語意。
//
// 背景：
//   - pkg/mover/batch.go:22 目前實作為 `for i, item := range items` 單迴圈，
//     每筆呼叫一次 MoveFile，無 goroutine pool。
//   - implementation-notes.md open question 3 曾擔心：若改為並行，兩個 worker
//     可能同時對相同 destination 做 os.Stat 都看不到對方，造成 race（dest 撞名
//     後者覆蓋前者）。實測下並無此問題，但若未來有人為了吞吐量改為並行而沒
//     人擋，就會重新引入這個 race。
//
// 此測試由兩層 invariant 組成：
//
//  1. **AST/static guard**：直接 parse `pkg/mover/batch.go`，檢查
//     `batchMoveWithType` 函式內：
//     (a) 整段 function body 不得出現 `go` 語句（`*ast.GoStmt`）
//     (b) `for ... := range items` 迴圈必須直接同步呼叫 `m.MoveFile(...)`，
//     不得透過 goroutine / errgroup / channel 異步分派
//     這層 guard 不依賴執行時行為，任何把 MoveFile 包進 goroutine 的改動都會
//     在 compile 後立刻被測試擋下。
//
//  2. **Runtime behaviour guard**：observer goroutine 偵測「每筆 item 的 source
//     何時消失」（os.Rename 或 copyFile+recycleFile 完成後 source 不再存在）。
//     嚴格序列下：
//     (a) `result.Results` 順序必與 items 相同
//     (b) source 消失時間 `completions[k]` 必早於或同步於 `completions[k+1]`
//     即使有人刻意以 channel 維持 Results 順序的並行化（繞過 static guard），
//     仍會在 `completions` 單調性上現形。
func TestBatchMove_SerialExecutionInvariant(t *testing.T) {
	assertBatchMoveStaticallySerial(t)

	tempDir, cleanup := setupTestEnv(t)
	defer cleanup()

	const N = 10
	items := make([]MoveItem, N)
	for i := 0; i < N; i++ {
		src := filepath.Join(tempDir, "src", fmt.Sprintf("file_%02d.txt", i))
		dst := filepath.Join(tempDir, "dst", fmt.Sprintf("file_%02d.txt", i))
		createTestFile(t, src, fmt.Sprintf("content-%02d", i))
		items[i] = MoveItem{Source: src, Destination: dst}
	}

	completions := make([]time.Time, N)
	done := make([]chan struct{}, N)
	for i := 0; i < N; i++ {
		done[i] = make(chan struct{})
	}

	observerCtx, cancelObservers := context.WithCancel(context.Background())
	defer cancelObservers()

	for i := 0; i < N; i++ {
		idx := i
		go func() {
			defer close(done[idx])
			for {
				if observerCtx.Err() != nil {
					return
				}
				if _, err := os.Stat(items[idx].Source); os.IsNotExist(err) {
					completions[idx] = time.Now()
					return
				}
			}
		}()
	}

	m := NewMover(tempDir)
	result := m.BatchMove(context.Background(), items)

	for i := 0; i < N; i++ {
		select {
		case <-done[i]:
		case <-time.After(5 * time.Second):
			cancelObservers()
			t.Fatalf("observer for items[%d].Source=%s 未在期限內偵測到 source 消失", i, items[i].Source)
		}
	}

	if result.SuccessCount != N {
		t.Fatalf("expected %d successes, got success=%d failed=%d skipped=%d",
			N, result.SuccessCount, result.FailedCount, result.SkippedCount)
	}
	if len(result.Results) != N {
		t.Fatalf("expected %d results, got %d", N, len(result.Results))
	}

	// Invariant 1: result.Results 必與 input 同順序。
	// 任何 naive 並行（goroutine pool）即使搭配 channel/index 排序，
	// 最常見的破壞點就是這裡。
	for i, r := range result.Results {
		if r.Source != items[i].Source {
			t.Errorf("Results[%d].Source = %s, want %s — BatchMove 必須維持 input 順序", i, r.Source, items[i].Source)
		}
	}

	// Invariant 2: source 消失時間必單調非遞減（第 k+1 筆完成時間 ≥ 第 k 筆）。
	// 此 invariant 直接對應 implementation-notes.md open question 3 所要求的
	// 「第 k+1 筆開始時間 ≥ 第 k 筆結束時間」。
	for k := 0; k+1 < N; k++ {
		if completions[k+1].Before(completions[k]) {
			t.Errorf("completions[%d]=%s 早於 completions[%d]=%s；BatchMove 必須序列執行 "+
				"(見 pkg/mover/batch.go:22 與 docs/茶包射手/scan-multi-part-and-same-name-cross-dir.md)",
				k+1, completions[k+1].Format(time.RFC3339Nano),
				k, completions[k].Format(time.RFC3339Nano))
		}
	}
}

// assertBatchMoveStaticallySerial parse pkg/mover/batch.go，靜態驗證
// `batchMoveWithType` 函式內不得出現 goroutine 分派，且 `range items` 迴圈
// 必須直接同步呼叫 `m.MoveFile(...)`。任何把 MoveFile 包進 `go func() { ... }()`
// 或丟給 errgroup / channel worker 的改動都會在此 fatal，不需執行 runtime 路徑。
func assertBatchMoveStaticallySerial(t *testing.T) {
	t.Helper()

	const target = "batch.go"
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, target, nil, parser.AllErrors)
	if err != nil {
		t.Fatalf("parser.ParseFile(%s): %v", target, err)
	}

	var fn *ast.FuncDecl
	for _, decl := range file.Decls {
		fd, ok := decl.(*ast.FuncDecl)
		if !ok {
			continue
		}
		if fd.Name.Name == "batchMoveWithType" && fd.Recv != nil {
			fn = fd
			break
		}
	}
	if fn == nil || fn.Body == nil {
		t.Fatalf("static guard: 找不到 (*Mover).batchMoveWithType 函式定義於 %s", target)
	}

	// (a) 整段 body 不得出現 `go` 語句
	ast.Inspect(fn.Body, func(n ast.Node) bool {
		if gs, ok := n.(*ast.GoStmt); ok {
			pos := fset.Position(gs.Pos())
			t.Errorf("static guard: batchMoveWithType 內偵測到 `go` 語句 (%s:%d:%d)；"+
				"BatchMove 必須維持序列執行 — 詳見 docs/sqlite-migration-tail-tasks.md T1",
				pos.Filename, pos.Line, pos.Column)
		}
		return true
	})

	// (b) `for ... := range items` 迴圈 body 必須直接同步呼叫 m.MoveFile(...)
	var rangeOverItems *ast.RangeStmt
	ast.Inspect(fn.Body, func(n ast.Node) bool {
		rs, ok := n.(*ast.RangeStmt)
		if !ok {
			return true
		}
		ident, ok := rs.X.(*ast.Ident)
		if !ok || ident.Name != "items" {
			return true
		}
		rangeOverItems = rs
		return false
	})
	if rangeOverItems == nil {
		t.Fatalf("static guard: batchMoveWithType 內找不到 `for ... := range items` 迴圈；" +
			"BatchMove 對 items 的序列消費 invariant 已失效（見 docs/sqlite-migration-tail-tasks.md T1）")
	}

	// 在迴圈 body 中尋找 m.MoveFile 呼叫；不得位於任何 *ast.GoStmt 之下（前一段已涵蓋）
	var foundMoveFileCall bool
	ast.Inspect(rangeOverItems.Body, func(n ast.Node) bool {
		ce, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		sel, ok := ce.Fun.(*ast.SelectorExpr)
		if !ok || sel.Sel.Name != "MoveFile" {
			return true
		}
		recv, ok := sel.X.(*ast.Ident)
		if !ok || recv.Name != "m" {
			return true
		}
		foundMoveFileCall = true
		return false
	})
	if !foundMoveFileCall {
		t.Errorf("static guard: range items 迴圈內找不到同步的 m.MoveFile 呼叫；" +
			"items 必須由主 goroutine 逐筆同步處理 — 任何 channel / worker pool 拆解都會破壞 T1 序列 invariant")
	}
}
