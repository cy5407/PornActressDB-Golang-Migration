#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Wails backend integration test"
if ! command -v go >/dev/null 2>&1; then
  echo "go is required" >&2
  exit 1
fi

if [ ! -f "backend/integration_test.go" ]; then
  echo "backend/integration_test.go not found" >&2
  exit 1
fi

echo "Step 0: Generate fixtures (if not already present)"
FIXTURE_VIDEOS_DIR="e2e/fixtures/videos"
if [ ! -d "$FIXTURE_VIDEOS_DIR" ] || [ -z "$(find "$FIXTURE_VIDEOS_DIR" -maxdepth 1 -type f | head -n 1)" ]; then
  python3 e2e/fixtures/gen_fixtures.py
fi

TEST_OUTPUT="$(go test ./backend -run 'TestIntegration|TestBackendSmoke' -v 2>&1)"
STATUS=$?
printf '%s\n' "$TEST_OUTPUT"

SUCCESS_COUNT="$(printf '%s\n' "$TEST_OUTPUT" | grep -c '--- PASS:' || true)"
FAIL_COUNT="$(printf '%s\n' "$TEST_OUTPUT" | grep -c '--- FAIL:' || true)"

cat <<EOF

==> Summary
Passed test blocks : ${SUCCESS_COUNT}
Failed test blocks : ${FAIL_COUNT}
Exit code          : ${STATUS}
EOF

exit "$STATUS"
