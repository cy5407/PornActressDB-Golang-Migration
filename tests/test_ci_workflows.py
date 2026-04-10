from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_python_test_workflow_builds_classifier_before_pytest():
    workflow = (ROOT_DIR / ".github" / "workflows" / "python-test.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: actions/setup-go@v5" in workflow
    assert "Build classifier CLI" in workflow
    assert "go build -o classifier.exe ./cmd/scanner" in workflow
    assert 'CLASSIFIER_EXE: ""' not in workflow


def test_dockerfile_copies_pkg_sources_for_source_regression_tests():
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    runtime_stage = dockerfile.split("FROM python:3.11-slim-bookworm AS runtime", 1)[1]

    assert "COPY pkg/ ./pkg/" in runtime_stage
    assert "COPY .github/ ./.github/" in runtime_stage


def test_go_lint_workflow_installs_linter_with_current_go_toolchain():
    workflow = (ROOT_DIR / ".github" / "workflows" / "go-lint.yml").read_text(
        encoding="utf-8"
    )

    assert "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest" in workflow
    assert "$(go env GOPATH)/bin/golangci-lint run --timeout=5m" in workflow
    assert "golangci/golangci-lint-action@v6" not in workflow
