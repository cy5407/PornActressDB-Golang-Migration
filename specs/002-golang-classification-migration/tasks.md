---
description: "Task breakdown for Golang classification migration"
---

# Tasks: 分類功能 Golang 遷移

**Feature**: 002-golang-classification-migration  
**Input**: spec.md, plan.md, research.md, data-model.md, contracts/  
**Date**: 2025-10-18

---

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create golang/ project structure per plan.md: cmd/, internal/, pkg/proto/
- [ ] T002 Initialize Go module with `go mod init` and add dependencies (grpc, cobra, zap, protobuf)
- [ ] T003 [P] Create Makefile with build, test, lint, proto-gen targets
- [ ] T004 [P] Setup .gitignore for Go binaries and generated protobuf files
- [ ] T005 Install protoc compiler and Go plugins (protoc-gen-go, protoc-gen-go-grpc)

**Checkpoint**: Project structure ready for implementation

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 [P] Implement VideoFile model in golang/internal/models/video_file.go
- [ ] T007 [P] Implement VideoCode model in golang/internal/models/video_code.go
- [ ] T008 [P] Implement Actress model in golang/internal/models/actress.go
- [ ] T009 [P] Implement Studio model in golang/internal/models/studio.go
- [ ] T010 [P] Implement ScanResult model in golang/internal/models/scan_result.go
- [ ] T011 [P] Implement ClassificationOperation model in golang/internal/models/classification_operation.go
- [ ] T012 [P] Implement StudioStatistics model in golang/internal/models/studio_statistics.go
- [ ] T013 Create JSON database interface in golang/internal/database/interface.go (Read, Write, Lock, Unlock)
- [ ] T014 Implement JSON file reader in golang/internal/database/json_reader.go with atomic read + file locking
- [ ] T015 Implement JSON file writer in golang/internal/database/json_writer.go with atomic write + file locking
- [ ] T016 [P] Create structured logger wrapper in golang/internal/logger/logger.go (using zap)
- [ ] T017 [P] Create error types in golang/internal/errors/errors.go (FileError, DatabaseError, ValidationError)
- [ ] T018 [P] Implement cross-platform path utilities in golang/internal/fileops/path.go (filepath.FromSlash, Clean)
- [ ] T019 Create Cobra CLI entry point in golang/cmd/classifier/main.go with root command
- [ ] T020 Generate protobuf code: `protoc --go_out=. --go-grpc_out=. contracts/classifier.proto`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 檔案掃描與番號提取 (Priority: P1) 🎯 MVP

**Goal**: 掃描指定資料夾中的影片檔案，提取番號，生成統計報告

**Independent Test**: 掃描包含 10,000 個影片檔案的資料夾，30 秒內完成，成功率 ≥ 99%

### Implementation for User Story 1

- [ ] T021 [P] [US1] Implement file scanner in golang/internal/scanner/file_scanner.go
  - WalkDir recursively with filepath.WalkDir
  - Filter by extensions (mp4, mkv, avi, mov, wmv)
  - Return channel of VideoFile structs
  
- [ ] T022 [P] [US1] Implement code extractor in golang/internal/scanner/code_extractor.go
  - Regex patterns for video codes (e.g., SONE-123, STARS-456, FC2-PPV-12345)
  - Normalize codes (uppercase, standard format)
  - Handle edge cases (FC2, PPV, multiple codes)
  
- [ ] T023 [US1] Implement goroutine pool in golang/internal/scanner/worker_pool.go (depends on T021, T022)
  - Semaphore pattern for worker limit (default: CPU cores, max: 8)
  - Process files concurrently with code extraction
  - Collect results via channel
  
- [ ] T024 [US1] Implement scan command in golang/cmd/classifier/scan.go (depends on T023)
  - Add scan subcommand to Cobra CLI
  - Parse flags (--folder, --recursive, --format, --extensions, --workers, --output)
  - Call scanner with goroutine pool
  - Output JSON/JSONL format to stdout or file
  
- [ ] T025 [US1] Add validation and error handling for scan command
  - Validate folder path exists and readable
  - Handle permission errors, symlink errors
  - Log errors to stderr, structured JSON to stdout
  
- [ ] T026 [US1] Add progress reporting for scan command
  - Calculate percentage completion
  - Estimate remaining time (ETA)
  - Output progress to stderr (if --verbose)
  
- [ ] T027 [US1] Add logging for scan operations
  - Log start/end timestamps
  - Log file counts, success/failure rates
  - Log performance metrics (files/second, total duration)

**Checkpoint**: `classifier scan` command fully functional and testable independently

---

## Phase 4: User Story 2 - 女優資料夾分類 (Priority: P2)

**Goal**: 根據影片中的女優資訊，將影片移動到對應的女優資料夾

**Independent Test**: 
- 準備 1,000 個影片檔案 (70% 單女優, 30% 多女優共演)
- 執行 `classify-actress` 命令 (auto mode)
- 驗證 70% 單女優影片正確分類，30% 多女優影片被跳過

### Implementation for User Story 2

- [ ] T028 [P] [US2] Implement actress database reader in golang/internal/database/actress_reader.go
  - Load actress.json into memory
  - Provide Actress lookup by name
  - Cache Actress records for performance
  
- [ ] T029 [P] [US2] Implement actress classifier in golang/internal/classifier/actress_classifier.go
  - Match VideoFile.ActressNames to Actress records
  - Determine target folder (single vs. multi actress)
  - Apply mode filter (auto = single only, all = all)
  
- [ ] T030 [P] [US2] Implement file mover in golang/internal/fileops/file_mover.go
  - Atomic file move (os.Rename with fallback to copy+delete)
  - Create target directory if not exists
  - Preserve file metadata (timestamps, permissions)
  
- [ ] T031 [P] [US2] Implement conflict resolver in golang/internal/fileops/conflict_resolver.go
  - Detect conflicts (file already exists in target)
  - Apply strategy (skip, overwrite, rename, ask)
  - Generate unique filename for rename strategy
  
- [ ] T032 [US2] Implement classify-actress command in golang/cmd/classifier/classify_actress.go (depends on T028-T031)
  - Add classify-actress subcommand to Cobra CLI
  - Parse flags (--folder, --target, --mode, --conflict-strategy, --database, --workers)
  - Call actress classifier with goroutine pool
  - Output JSON results to stdout
  
- [ ] T033 [US2] Add validation and error handling for classify-actress command
  - Validate source/target folders exist
  - Validate database file exists and readable
  - Handle move errors (permission, disk full, cross-device)
  
- [ ] T034 [US2] Add progress reporting for classify-actress command
  - Report move operations (moved, skipped, failed)
  - Calculate percentage completion
  - Log summary statistics
  
- [ ] T035 [US2] Implement gRPC ClassifyActress service in golang/internal/grpc/classify_actress_service.go (depends on T032)
  - Implement bidirectional streaming RPC
  - Handle StartClassificationRequest, UserChoiceRequest, CancelRequest
  - Send ProgressUpdate, ActressChoicePrompt, OperationComplete, ErrorResponse
  
- [ ] T036 [US2] Implement interactive mode for multi-actress videos in golang/internal/classifier/interactive_classifier.go
  - Prompt user to choose actress for multi-actress videos
  - Support "remember choice" for future files
  - Integrate with gRPC bidirectional streaming
  
- [ ] T037 [US2] Implement gRPC server in golang/cmd/classifier-server/main.go (depends on T035)
  - Initialize gRPC server on port 50051
  - Register ClassifierService
  - Handle graceful shutdown (SIGINT, SIGTERM)
  
- [ ] T038 [US2] Add logging for classify-actress operations
  - Log each file move operation
  - Log conflict resolution decisions
  - Log interactive user choices (if applicable)

**Checkpoint**: `classifier classify-actress` command and gRPC interactive mode fully functional

---

## Phase 5: User Story 3 - 片商資料夾分類 (Priority: P3)

**Goal**: 分析女優資料夾中的影片，統計片商分佈，將女優資料夾移動到主要片商資料夾

**Independent Test**:
- 準備 100 個女優資料夾，每個包含 5-20 個影片
- 執行 `classify-studio` 命令
- 驗證主要片商識別正確率 ≥ 90%，置信度 ≥ 70% 的女優資料夾被正確分類

### Implementation for User Story 3

- [ ] T039 [P] [US3] Implement studio database reader in golang/internal/database/studio_reader.go
  - Load studios.json into memory
  - Provide Studio lookup by name/prefix
  - Cache Studio records for performance
  
- [ ] T040 [P] [US3] Implement studio statistics calculator in golang/internal/classifier/studio_statistics.go
  - Count videos per studio for an actress
  - Calculate primary studio (highest count)
  - Calculate confidence (primary count / total count)
  
- [ ] T041 [P] [US3] Implement studio classifier in golang/internal/classifier/studio_classifier.go
  - Scan actress folder for video files
  - Extract video codes and match to studios
  - Calculate StudioStatistics
  - Determine if confidence ≥ threshold (default: 0.7)
  
- [ ] T042 [US3] Implement classify-studio command in golang/cmd/classifier/classify_studio.go (depends on T039-T041)
  - Add classify-studio subcommand to Cobra CLI
  - Parse flags (--folder, --target, --confidence, --database, --workers, --dry-run)
  - Call studio classifier with goroutine pool
  - Move actress folders to studio folders
  - Output JSON results to stdout
  
- [ ] T043 [US3] Add validation and error handling for classify-studio command
  - Validate source folder exists and contains actress folders
  - Validate target folder exists or can be created
  - Handle folder move errors (permission, disk full)
  
- [ ] T044 [US3] Add progress reporting for classify-studio command
  - Report folder processing (analyzed, moved, skipped)
  - Show studio distribution for each actress
  - Log summary statistics (total folders, success rate)
  
- [ ] T045 [US3] Add dry-run mode for classify-studio command
  - Flag: --dry-run (show what would be done without making changes)
  - Output planned moves with confidence scores
  - Allow user to review before executing
  
- [ ] T046 [US3] Implement gRPC ClassifyStudio service in golang/internal/grpc/classify_studio_service.go (depends on T042)
  - Implement server streaming RPC
  - Send ClassifyStudioProgress updates
  - Handle cancellation gracefully
  
- [ ] T047 [US3] Add logging for classify-studio operations
  - Log each folder analysis result
  - Log studio distribution calculations
  - Log folder move operations with confidence scores

**Checkpoint**: `classifier classify-studio` command fully functional

---

## Phase 6: Test Data Generation (Testing Infrastructure)

**Purpose**: 產生模擬測試資料集，確保在沒有真實影片檔案的情況下仍可驗證程式功能

**⚠️ CRITICAL**: 所有效能測試和整合測試都依賴這個階段產生的測試資料

- [ ] T048 [P] Create test data generator in tests/testdata/generator.go
  - Generate empty files with correct naming patterns (SONE-123.mp4, STARS-456.mkv, etc.)
  - Support different file sizes (use sparse files or truncate to avoid disk space issues)
  - Support batch generation (10, 100, 1,000, 10,000 files)
  
- [ ] T049 [P] Create mock video file factory in tests/testdata/video_factory.go
  - Factory pattern to create VideoFile structs with realistic data
  - Generate files with various naming patterns:
    * Standard: `SONE-123.mp4`, `STARS-456.mkv`
    * With prefix: `hhd800.com@ABC-789.mp4`
    * With suffix: `SONE-123-女優名.mp4`
    * FC2: `FC2-PPV-1234567.mp4`
  - Generate files with invalid names (no code)
  
- [ ] T050 [P] Create mock actress database in tests/testdata/mock_actress.json
  - Generate 100+ mock actress records with:
    * Realistic names (女優A, 女優B, ... or use placeholder names)
    * Video counts (5-100 videos per actress)
    * Studio distributions (e.g., 70% S1, 20% Prestige, 10% Others)
  - Include edge cases: single-studio actresses, multi-studio actresses
  
- [ ] T051 [P] Create mock studio database in tests/testdata/mock_studios.json
  - Generate realistic studio records with:
    * Studio names (S1, Prestige, MOODYZ, etc.)
    * Code prefixes (SONE, STARS, MIAA, etc.)
    * Multiple prefixes per studio
  - Match real-world studio patterns from existing `studios.json`
  
- [ ] T052 [P] Create test folder structure generator in tests/testdata/folder_generator.go
  - Generate folder structures for US2 testing:
    * 1,000 video files in flat structure (70% single actress, 30% multi-actress)
    * Pre-classified actress folders with 5-20 videos each
  - Generate folder structures for US3 testing:
    * 100 actress folders with video files
    * Each folder has dominant studio (70-90% confidence)
  
- [ ] T053 Create CLI tool for test data generation in cmd/testdata-gen/main.go
  - Command: `testdata-gen --preset small|medium|large --output ./testdata`
  - Presets:
    * small: 10 files, 5 actresses, 3 studios (for quick unit tests)
    * medium: 1,000 files, 50 actresses, 10 studios (for integration tests)
    * large: 10,000 files, 100 actresses, 20 studios (for performance tests)
  - Include cleanup command: `testdata-gen --clean ./testdata`
  
- [ ] T054 [P] Add test data validation in tests/testdata/validator_test.go
  - Verify generated files have correct extensions
  - Verify file names match expected patterns
  - Verify mock databases are valid JSON
  - Verify folder structures are correct

**Checkpoint**: Test data generation complete - can now run all tests without real video files

---

## Phase 7: Polish (Integration & Documentation)

**Purpose**: Python integration, testing, performance optimization, documentation

- [ ] T055 [P] Create Python CLI wrapper in src/golang_integration/cli_wrapper.py
  - Wrapper for `classifier scan`, `classifier classify-actress`, `classifier classify-studio`
  - Use subprocess.run with proper encoding (UTF-8)
  - Parse JSON output and return Python objects
  
- [ ] T056 [P] Create Python gRPC client in src/golang_integration/grpc_client.py
  - Connect to gRPC server on localhost:50051
  - Implement ClassifyActress bidirectional streaming
  - Handle reconnection and error recovery
  
- [ ] T057 [P] Create Python server manager in src/golang_integration/server_manager.py
  - Start/stop gRPC server (classifier-server)
  - Health check endpoint
  - Automatic restart on crash
  
- [ ] T058 [P] Add integration tests in tests/integration/test_golang_classifier.py (depends on T048-T054)
  - **Use generated test data from Phase 6**
  - Test CLI wrapper with small preset (10 files)
  - Test gRPC client with mock server
  - Test Python-Go bidirectional communication
  - Verify JSON parsing and error handling
  
- [ ] T059 [P] Add unit tests for scanner in golang/internal/scanner/file_scanner_test.go (depends on T049)
  - **Use mock video factory to generate test files**
  - Test file scanning with various folder structures
  - Test extension filtering
  - Test recursive vs. non-recursive modes
  - Clean up test files after tests complete
  
- [ ] T060 [P] Add unit tests for code extractor in golang/internal/scanner/code_extractor_test.go (depends on T049)
  - **Use mock video factory for file names**
  - Test regex patterns with valid/invalid codes
  - Test normalization (uppercase, format)
  - Test edge cases (FC2, PPV, multi-code filenames)
  - Include at least 50+ test cases covering all patterns
  
- [ ] T061 [P] Add unit tests for actress classifier in golang/internal/classifier/actress_classifier_test.go (depends on T050)
  - **Use mock actress database**
  - Test single actress matching
  - Test multi-actress filtering
  - Test mode logic (auto vs. all)
  - Test database lookup performance
  
- [ ] T062 [P] Add unit tests for studio classifier in golang/internal/classifier/studio_classifier_test.go (depends on T051)
  - **Use mock studio database**
  - Test studio statistics calculation
  - Test confidence threshold logic
  - Test edge cases (no videos, all unknown studios)
  - Verify confidence calculation accuracy
  
- [ ] T063 [P] Add unit tests for file operations in golang/internal/fileops/file_mover_test.go (depends on T048)
  - **Use test data generator for files**
  - Test file move (same device, cross-device)
  - Test conflict resolution strategies
  - Test permission errors (use temp directories)
  - Verify atomic operations
  
- [ ] T064 [P] Add unit tests for JSON database in golang/internal/database/json_reader_test.go (depends on T050, T051)
  - **Use mock JSON databases**
  - Test JSON parsing with valid/invalid data
  - Test file locking (concurrent access)
  - Test corrupted file handling
  - Test atomic read/write operations
  
- [ ] T065 Performance benchmark for scan command (depends on T048, T052)
  - **Use large preset: 10,000 generated files**
  - Measure scan time with different worker counts (1, 2, 4, 8)
  - Ensure ≤ 30 seconds for 10,000 files
  - Generate performance report with charts
  - Verify success rate ≥ 99%
  
- [ ] T066 Performance benchmark for classify-actress command (depends on T052)
  - **Use medium preset: 1,000 files (70% single, 30% multi)**
  - Measure classification time
  - Ensure ≤ 1 minute for 1,000 files
  - Verify correct classification of single-actress files
  - Verify multi-actress files are handled correctly
  
- [ ] T067 Performance benchmark for classify-studio command (depends on T052)
  - **Use 100 actress folders from generated data**
  - Measure analysis time
  - Ensure ≤ 30 seconds for 100 folders
  - Verify confidence calculation accuracy
  - Verify correct folder moves for high-confidence cases
  
- [ ] T068 Memory profiling (depends on T065-T067)
  - Run pprof on all commands with large datasets
  - Ensure memory usage ≤ 500 MB
  - Identify memory leaks or excessive allocations
  - Optimize if necessary (streaming, batch processing, goroutine limits)
  
- [ ] T069 [P] Write CLI usage documentation in specs/002-golang-classification-migration/cli-usage.md
  - Document all commands with examples
  - Include test data generation examples
  - Document common workflows
  - Document troubleshooting tips
  
- [ ] T070 [P] Write Python integration guide in specs/002-golang-classification-migration/python-integration.md
  - Document how to call Go CLI from Python
  - Document gRPC client usage
  - Document error handling patterns
  - Include example code snippets
  
- [ ] T071 [P] Write testing guide in specs/002-golang-classification-migration/testing-guide.md
  - Document how to generate test data
  - Document how to run unit tests
  - Document how to run performance benchmarks
  - Document how to interpret test results
  
- [ ] T072 [P] Update README.md with Golang migration information
  - Add build instructions
  - Add usage examples with test data
  - Add performance benchmarks
  - Add testing instructions

**Checkpoint**: Full feature complete, tested, documented, ready for production

---

## Dependencies

### Critical Path
```
Setup (T001-T005) 
  → Foundational (T006-T020)
    → US1 (T021-T027) 
      → US2 (T028-T038) 
        → US3 (T039-T047)
          → Test Data Generation (T048-T054) ⚠️ REQUIRED FOR ALL TESTING
            → Polish (T055-T072)
```

### Parallel Tracks (Can work independently)
- **Models** (T006-T012): All parallelizable
- **Database** (T013-T015): Sequential (interface → reader → writer)
- **Utilities** (T016-T018): All parallelizable
- **US1 Implementation** (T021, T022): Parallelizable until T023
- **US2 Implementation** (T028-T031): Parallelizable until T032
- **US3 Implementation** (T039-T041): Parallelizable until T042
- **Test Data Generation** (T048-T052, T054): All parallelizable (except T053 depends on all)
- **Unit Tests** (T059-T064): All parallelizable AFTER test data generation complete
- **Performance Tests** (T065-T068): Sequential (depends on test data)
- **Documentation** (T069-T072): All parallelizable

---

## Verification Criteria

### User Story 1 (US1) ✅
- [ ] Independent test: Scan 10,000 files in ≤ 30 seconds
- [ ] Success rate: ≥ 99%
- [ ] Output: Valid JSON with correct statistics
- [ ] Error handling: Failed files listed with reasons

### User Story 2 (US2) ✅
- [ ] Independent test: Classify 1,000 files (70% single, 30% multi)
- [ ] Auto mode: 70% moved, 30% skipped
- [ ] All mode: 100% processed (interactive or auto-assigned)
- [ ] Conflict handling: No data loss, all strategies work
- [ ] gRPC: Interactive mode functional

### User Story 3 (US3) ✅
- [ ] Independent test: Analyze 100 actress folders in ≤ 30 seconds
- [ ] Accuracy: ≥ 90% primary studio identification
- [ ] Confidence: Only move folders with ≥ 70% confidence
- [ ] Dry-run: Shows planned moves without executing

### Performance ✅
- [ ] Scan: 10,000 files ≤ 30s
- [ ] Classify actress: 1,000 files ≤ 1min
- [ ] Classify studio: 100 folders ≤ 30s
- [ ] Memory: ≤ 500 MB for all operations

### Integration ✅
- [ ] Python CLI wrapper: All 3 commands callable from Python
- [ ] Python gRPC client: Interactive mode works end-to-end
- [ ] Server manager: Auto-start, health check, graceful shutdown

---

## Estimated Effort

| Phase | Tasks | Estimated Days | Critical? |
|-------|-------|----------------|-----------|
| Phase 1: Setup | T001-T005 | 0.5 days | ✅ |
| Phase 2: Foundational | T006-T020 | 3 days | ✅ |
| Phase 3: US1 | T021-T027 | 2 days | ✅ (MVP) |
| Phase 4: US2 | T028-T038 | 4 days | ⚠️ (Complex) |
| Phase 5: US3 | T039-T047 | 2 days | - |
| Phase 6: Test Data Gen | T048-T054 | 2 days | ✅ (Testing) |
| Phase 7: Polish | T055-T072 | 5 days | - |
| **Total** | **72 tasks** | **18.5 days** | |

**Note**: Days are estimated for a single developer. Phases 3-5 can be parallelized with multiple developers after Phase 2 completes. Phase 6 (Test Data Generation) is CRITICAL and must be completed before any testing can occur.

---

## Next Steps

1. **Review Tasks**: Ensure all tasks align with spec.md and plan.md
2. **Assign Priorities**: Confirm P1 (US1) → P2 (US2) → P3 (US3) order
3. **Setup Environment**: Complete Phase 1 (Setup) tasks
4. **Build Foundation**: Complete Phase 2 (Foundational) tasks - CRITICAL BLOCKER
5. **Implement User Stories**: Work through Phases 3-5 in priority order
6. **Generate Test Data**: Complete Phase 6 (Test Data Generation) - REQUIRED FOR VERIFICATION
7. **Test & Polish**: Complete Phase 7 (Polish) for production readiness

**Recommended Start**: T001 (Create project structure)  
**Critical for Testing**: T048-T054 (Test data generation must be completed before any tests can run)

---

## Testing Strategy Summary

### How to Verify Without Real Video Files ✅

**Phase 6 (Test Data Generation)** solves this problem by creating:

1. **Empty Mock Files** (T048-T049):
   - Generate files with correct naming patterns (SONE-123.mp4, etc.)
   - Use sparse files or truncate to create 0-byte or small files
   - No actual video content needed - only filenames matter for classification

2. **Mock Databases** (T050-T051):
   - Realistic actress.json with 100+ records
   - Realistic studios.json matching real-world patterns
   - Include edge cases for thorough testing

3. **Test Folder Structures** (T052):
   - Realistic folder hierarchies for US2/US3 testing
   - 70%/30% single/multi-actress distribution
   - 100 actress folders with varying studio distributions

4. **CLI Tool for Quick Setup** (T053):
   ```bash
   # Generate small test dataset (10 files, 5 actresses)
   testdata-gen --preset small --output ./testdata
   
   # Generate large dataset for performance testing (10,000 files)
   testdata-gen --preset large --output ./testdata
   
   # Clean up after testing
   testdata-gen --clean ./testdata
   ```

5. **All Tests Use Generated Data** (T058-T068):
   - Unit tests use mock factories
   - Integration tests use small preset
   - Performance tests use large preset
   - Memory profiling uses large preset
   - **No real video files required at any point**

### Verification Workflow

```bash
# Step 1: Generate test data
cd golang
make testdata-gen-small  # or medium, large

# Step 2: Run unit tests
make test

# Step 3: Run performance benchmarks
make bench

# Step 4: Run integration tests
cd ../src
pytest tests/integration/

# Step 5: Clean up
cd golang
make testdata-clean
```

**Result**: Complete verification without storing or using any actual video files ✅
