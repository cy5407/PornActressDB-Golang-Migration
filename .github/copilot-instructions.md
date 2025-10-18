# PornActressDB-Golang-Migration Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-18

## Active Technologies
- Go 1.22+ + gRPC, Protocol Buffers, Cobra CLI (002-golang-classification-migration)
- Python 3.8+ + subprocess, grpcio (integration layer)

## Project Structure
```
golang/
  cmd/
    classifier/        # CLI tool
    classifier-server/ # gRPC server
  internal/
    scanner/          # File scanning & code extraction
    classifier/       # Classification logic
    database/         # JSON database access
    fileops/          # File operations
    models/           # Data models
    grpc/             # gRPC implementation
  pkg/
    proto/            # Generated Protocol Buffers code
src/
  golang_integration/ # Python-Go integration layer
tests/
  integration/        # Python-Go integration tests
specs/
  002-golang-classification-migration/
    plan.md
    research.md
    data-model.md
    quickstart.md
    contracts/
```

## Commands
# Golang
cd golang; make build; make test; make lint

# Python integration
cd src; pytest tests/integration/

## Code Style
Go 1.22+: Follow Effective Go, golangci-lint, ≤15 cognitive complexity
Python 3.8+: Black formatter, type hints

## Recent Changes
- 002-golang-classification-migration: Added Go 1.22+ + gRPC, Protocol Buffers, Cobra CLI (Phase 0 & 1 complete: research, data model, contracts, quickstart)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->