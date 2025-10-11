# Actress Classifier System Constitution

## Core Principles

### I. Communication Standards
**AI Agent Language Requirements**

- AI agents MUST communicate with users in Traditional Chinese (繁體中文)
- Code comments MUST be written in Traditional Chinese
- Exception: Technical terms and programming keywords remain in English
- Git commit messages: English (following Conventional Commits)
- Documentation: Traditional Chinese for user-facing content, English for technical specifications
- This ensures clear communication while maintaining international code standards

### II. Progressive Migration Strategy
**Python 3.8+ → Go 1.22+ Three-Phase Refactoring**

- Phase 1 (2-3 weeks): Backend core logic (scraper engine, data processing, encoding handling)
- Phase 2 (1-2 weeks): CLI tools with Cobra framework
- Phase 3 (2-4 weeks): GUI development (Fyne/Wails/Hybrid architecture)
- MUST complete each phase before proceeding to next
- Each phase MUST achieve ≥70% test coverage
- Integration tests required between phases

### III. Code Quality Standards (NON-NEGOTIABLE)
**Strict Type Safety and Error Handling**

- Go 1.22+ required (or latest stable version) with all features leveraging standard library first
- Follow official Go coding standards (Effective Go)
- Follow Clean Code principles: functions should be short, names should be clear, avoid duplication
- Function cognitive complexity MUST NOT exceed 15 (per SonarQube RSPEC-3776)
- Use `golangci-lint` with `gocognit` linter to check cognitive complexity
- Use `gofmt` and `golangci-lint` to ensure consistent code style
- Static type checking mandatory - no interface{} abuse
- Error handling: MUST NOT use panic() except for unrecoverable errors
- All errors MUST be wrapped with context using fmt.Errorf() or errors.Wrap()
- Logging: structured logging with go.uber.org/zap (levels: Debug, Info, Warn, Error)
- Leverage Go's concurrency features (goroutines and channels) but manage concurrency count properly
- Test coverage: ≥70% unit tests, ≥50% integration tests
- Code review: All PRs require at least one approval

### IV. Web Scraping Best Practices
**Ethical and Reliable Crawling**

- MUST respect robots.txt for all domains
- Per-domain rate limiting: Independent configuration for each source
  - JAVDB: 1 request/second
  - AV-WIKI: 2 requests/second
  - chiba-f: 1 request/second
- User-Agent rotation: Maintain pool of ≥3 realistic user agents
- Retry strategy:
  - Transient errors (timeout, network): Exponential backoff, max 3 retries
  - Permanent errors (404, 403): No retry, log and skip
- Cache strategy: Memory cache (1 hour TTL) + file cache (24 hour TTL)
- Encoding handling: Auto-detect UTF-8, Shift-JIS, EUC-JP for Japanese sites

### V. Concurrency and Performance
**Goroutines and Channels Pattern**

- Concurrent crawling: Support ≥10 domains simultaneously using goroutines
- Concurrency control: Use semaphore pattern (buffered channel) for connection pooling
- Error group: Use golang.org/x/sync/errgroup for coordinated goroutine management
- Graceful shutdown: Context-based cancellation for all long-running operations
- Performance targets:
  - Memory usage: ≤200MB peak
  - Startup time: <1 second
  - API response: P95 <200ms
  - Cache hit rate: ≥50%

### VI. Data Storage - JSON File Database
**Zero External Dependencies**

- MUST NOT use SQLite or any database requiring cgo
- Use JSON file-based database with structure:
  ```
  data/
  ├── actresses/
  │   ├── index.json          # Fast lookup index
  │   ├── a-e.json            # Sharded by first letter
  │   ├── f-j.json
  │   └── ...
  ├── studios/
  │   └── studios.json
  └── metadata.json           # Database version and stats
  ```
- Atomic writes: Use temp file + rename pattern
- Validation: JSON schema validation on read/write
- Backup: Auto-backup before major writes
- Indexing: In-memory index for fast lookups
- Applicable for <100,000 records; migrate to embedded DB if exceeded

### VII. GUI Development Strategy
**Four Options with Decision Tree**

Option 1 - **Fyne** (Pure Go, Material Design):
- Pros: Cross-platform, simple API, no web knowledge required
- Cons: Limited customization
- Use when: Standard UI requirements, team has no frontend experience

Option 2 - **Wails** (Go + Web Tech):
- Pros: Modern UI, supports Vue/React, rich ecosystem
- Cons: Requires frontend knowledge, larger binary size
- Use when: Complex UI needs, team has frontend skills

Option 3 - **Gio** (Pure Go, Low-level):
- Pros: Extreme performance, lightweight
- Cons: Low-level API, steep learning curve
- Use when: Performance-critical applications

Option 4 - **Hybrid Architecture** (Python GUI + Go API):
- Pros: Lowest migration risk, incremental approach
- Cons: Maintain two languages
- Use when: Quick migration needed, preserve existing GUI investment

Decision tree:
```
Need immediate GUI migration?
├─ No  → Use Hybrid (Python GUI + Go REST API)
└─ Yes → Does team have frontend experience?
    ├─ Yes → Use Wails (modern UI)
    └─ No  → Use Fyne (pure Go, simple)
```

### VIII. Dependency Management
**Minimal External Dependencies**

Core dependencies (MUST have):
- `github.com/PuerkitoBio/goquery` - HTML parsing
- `golang.org/x/text/encoding` - Japanese encoding
- `golang.org/x/time/rate` - Rate limiting
- `go.uber.org/zap` - Structured logging

Test dependencies:
- `github.com/stretchr/testify` - Testing utilities

GUI dependencies (phase 3 only):
- `fyne.io/fyne/v2` (if Fyne chosen)
- `github.com/wailsapp/wails/v2` (if Wails chosen)

CLI dependencies (phase 2):
- `github.com/spf13/cobra` - CLI framework
- `github.com/spf13/viper` - Configuration

All dependencies MUST:
- Have active maintenance (commit within last 6 months)
- Support Go 1.22+
- Have ≥1000 GitHub stars OR be from trusted organization
- Not require cgo (except GUI frameworks)

## Technical Standards

### Error Handling
- MUST wrap all errors with context
- Use custom error types for domain-specific errors
- Log errors at appropriate levels
- Return errors, don't panic (except unrecoverable states)
- Example:
  ```go
  if err != nil {
      return fmt.Errorf("failed to fetch actress data from %s: %w", source, err)
  }
  ```

### Logging
- Use structured logging (zap.Logger)
- Include context fields: request_id, domain, operation
- Levels: Debug (dev only), Info (normal ops), Warn (degraded), Error (failures)
- Rotate logs daily, keep 7 days
- MUST NOT log sensitive data (passwords, tokens)

### Testing
- Unit tests: Test individual functions, mock external dependencies
- Integration tests: Test component interactions with real dependencies
- Table-driven tests preferred for multiple scenarios
- Use testdata/ for test fixtures
- Coverage: Run `go test -cover` and ensure ≥70%

### Documentation
- Every public function/type MUST have godoc comment
- Complex logic MUST have inline comments explaining "why"
- Update README.md and docs/ for user-facing changes
- Architecture decision records (ADR) for major decisions

## Development Workflow

### Git Workflow
- Branching: `feature/xxx`, `bugfix/xxx`, `refactor/xxx`
- Commit messages: Follow [Conventional Commits](https://www.conventionalcommits.org/)
  - `feat:` new features
  - `fix:` bug fixes
  - `refactor:` code refactoring
  - `test:` test additions/changes
  - `docs:` documentation changes
- Pull Requests: All changes via PR, no direct commits to main
- Required checks: Tests pass, linter pass, coverage maintained

### Code Review
- Every PR requires ≥1 approval
- Reviewer checklist:
  - [ ] Tests cover new code
  - [ ] Error handling appropriate
  - [ ] No performance regressions
  - [ ] Documentation updated
  - [ ] Follows Constitution principles
- Response time: <24 hours for initial review
- Use GitHub suggestions for minor changes

### CI/CD Pipeline
Phase 1 (Immediate):
- Run tests on every PR
- Run linter (golangci-lint)
- Check test coverage (fail if drops >5%)

Phase 2 (After phase 2 complete):
- Build binaries for Windows/macOS/Linux
- Run integration tests
- Generate coverage report

Phase 3 (Production ready):
- Automated releases via GitHub Actions
- Version tagging (semantic versioning)
- Release notes generation

### Quality Gates
Before merging to main:
1. ✅ All tests pass
2. ✅ Test coverage ≥70%
3. ✅ Linter passes with zero warnings
4. ✅ Documentation updated
5. ✅ At least one approving review
6. ✅ No merge conflicts

Before releasing:
1. ✅ Integration tests pass
2. ✅ Performance benchmarks meet targets
3. ✅ Security scan clean (gosec)
4. ✅ User-facing documentation complete
5. ✅ CHANGELOG.md updated

## Monitoring and Security

### Observability
- Metrics: Track crawl success rate, cache hit rate, memory usage
- Alerts: Set up for repeated failures (>5 in 1 hour)
- Health checks: /health endpoint in API mode

### Security
- Input validation: Sanitize all user inputs
- Path traversal protection: Validate file paths before operations
- Rate limiting: Prevent abuse in API mode
- Secrets management: Never commit secrets, use environment variables
- Dependencies: Regular security audits with `go list -m all | nancy sleuth`

## Governance

**Constitution Authority**: This document is the supreme governing policy for the Actress Classifier System project. All development decisions, code reviews, and technical choices MUST align with these principles.

**Amendment Process**:
1. Propose change via GitHub Issue with "constitution" label
2. Discuss with team (minimum 3 days for feedback)
3. Require 75% team approval for changes
4. Document rationale in commit message
5. Update version number (MAJOR for breaking changes)
6. Communicate to all stakeholders

**Conflict Resolution**:
- Constitution supersedes all other guidelines
- When in doubt, prioritize: Safety > Correctness > Performance > Convenience
- For ambiguous cases, consult tech lead or hold team discussion

**Compliance Review**:
- Monthly Constitution audit during sprint retrospectives
- Identify violations and create remediation tasks
- Update Constitution if principles are consistently violated (indicates misalignment)

**Living Document**: This Constitution is a living document. As the project evolves and the team learns, we will update these principles to reflect our collective wisdom. See `docs/go-重構指南.md` for implementation guidance and `docs/快速開始-Go版本.md` for getting started.

**Version**: 2.0.0 | **Ratified**: 2025-10-12 | **Last Amended**: 2025-10-12