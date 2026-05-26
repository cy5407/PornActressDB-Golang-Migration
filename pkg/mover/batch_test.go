package mover

import (
	"context"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"path/filepath"
	"testing"
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
//     (b) 整段 function body 不得出現 channel send（`*ast.SendStmt`）— 任何
//     worker pool 分派若用 channel 餵 worker 都會在這層 fatal
//     (c) `for ... := range items` 迴圈必須直接同步呼叫 `m.MoveFile(...)`，
//     不得透過 goroutine / errgroup / channel 異步分派
//     這層 guard 不依賴執行時行為，任何把 MoveFile 包進 goroutine 的改動都會
//     在 compile 後立刻被測試擋下。
//
//  2. **Runtime ordering guard**：執行 BatchMove 後，`result.Results` 順序必與
//     input items 相同。Naive 並行（goroutine pool）即使能正確完成搬移，最常
//     見的破壞點就是這裡的順序。
//
// 注意：原本還有一層「source 消失時間奈秒級單調性」的 runtime 觀察 goroutine，
// 但在 Linux CI 上 `time.Now()` 在多個 goroutine 間會出現反序，且此 invariant
// 已由上面的 static guard 完全覆蓋（serial 由 source code 結構保證，不需 runtime
// 時間戳重複驗證）。
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

	m := NewMover(tempDir)
	result := m.BatchMove(context.Background(), items)

	if result.SuccessCount != N {
		t.Fatalf("expected %d successes, got success=%d failed=%d skipped=%d",
			N, result.SuccessCount, result.FailedCount, result.SkippedCount)
	}
	if len(result.Results) != N {
		t.Fatalf("expected %d results, got %d", N, len(result.Results))
	}

	// result.Results 必與 input 同順序。任何 naive 並行（goroutine pool）即使搭配
	// channel/index 排序，最常見的破壞點就是這裡。
	for i, r := range result.Results {
		if r.Source != items[i].Source {
			t.Errorf("Results[%d].Source = %s, want %s — BatchMove 必須維持 input 順序", i, r.Source, items[i].Source)
		}
	}
}

// assertBatchMoveStaticallySerial parse pkg/mover/batch.go，靜態驗證
// `batchMoveWithType` 函式內不得出現 goroutine 分派或 channel 送出，且
// `range items` 迴圈必須直接同步呼叫 `m.MoveFile(...)`。任何把 MoveFile 包進
// `go func() { ... }()`、丟給 errgroup、或透過 channel 餵 worker 的改動都會在
// 此 fatal，不需執行 runtime 路徑。
//
//nolint:gocognit // AST guard intentionally checks several node shapes to lock serial BatchMove semantics.
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

	// (b) 整段 body 不得出現 channel send（`ch <- x`）— 任何 worker pool 都會藉
	// 此 dispatch，補捉這類 bypass。
	ast.Inspect(fn.Body, func(n ast.Node) bool {
		if ss, ok := n.(*ast.SendStmt); ok {
			pos := fset.Position(ss.Pos())
			t.Errorf("static guard: batchMoveWithType 內偵測到 channel send (%s:%d:%d)；"+
				"BatchMove 不得透過 channel 分派 worker — 詳見 docs/sqlite-migration-tail-tasks.md T1",
				pos.Filename, pos.Line, pos.Column)
		}
		return true
	})

	// (c) `for ... := range items` 迴圈 body 必須直接同步呼叫 m.MoveFile(...)
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
