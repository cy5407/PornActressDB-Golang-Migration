from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT_DIR / ".github" / "workflows"


def test_python_test_workflow_builds_classifier_before_pytest():
    workflow = (WORKFLOWS_DIR / "python-test.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: actions/setup-go@v6" in workflow
    assert "Build classifier CLI" in workflow
    assert "go build -o classifier ./cmd/scanner" in workflow
    assert 'CLASSIFIER_EXE: ""' not in workflow


def test_python_test_workflow_includes_windows_validation():
    workflow = (WORKFLOWS_DIR / "python-test.yml").read_text(
        encoding="utf-8"
    )

    assert "runs-on: windows-latest" in workflow
    assert "name: Python Unit Tests (Windows)" in workflow
    assert "go build -o classifier.exe .\\cmd\\scanner" in workflow


def test_go_lint_workflow_installs_linter_with_current_go_toolchain():
    workflow = (WORKFLOWS_DIR / "go-lint.yml").read_text(
        encoding="utf-8"
    )

    assert "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest" in workflow
    assert "$(go env GOPATH)/bin/golangci-lint run --timeout=5m" in workflow
    assert "golangci/golangci-lint-action@v6" not in workflow


def test_integration_workflow_includes_windows_validation():
    workflow = (WORKFLOWS_DIR / "integration-test.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Windows Validation" in workflow
    assert "runs-on: windows-latest" in workflow
    assert "go test .\\backend -v" in workflow
    assert "CLASSIFIER_EXE: ${{ github.workspace }}\\classifier.exe" in workflow


def test_portable_release_workflow_builds_and_smoke_tests_bundle():
    workflow = (WORKFLOWS_DIR / "portable-release.yml").read_text(
        encoding="utf-8"
    )

    assert "runs-on: windows-latest" in workflow
    assert "run: .\\setup.ps1" in workflow
    assert "dist\\portable\\Start-ActressClassifier.bat" in workflow
    assert "dist\\portable\\Setup-SearchRuntime.ps1" in workflow
    assert "dist\\portable\\src\\scrapers\\run_search.py" in workflow
    assert ".\\Setup-SearchRuntime.ps1" in workflow
    assert "dist/PornActressDB-windows-portable.zip" in workflow


def test_setup_ps1_packages_user_friendly_portable_launcher():
    setup_script = (ROOT_DIR / "setup.ps1").read_text(encoding="utf-8")

    assert "Start-ActressClassifier.bat" in setup_script
    assert "Setup-SearchRuntime.ps1" in setup_script
    assert "PornActressDB-windows-portable.zip" in setup_script
    assert "Compress-Archive" in setup_script


def test_workflows_do_not_use_node20_warned_action_versions():
    forbidden_versions = [
        "actions/checkout@v4",
        "actions/setup-go@v5",
        "actions/setup-python@v5",
        "actions/setup-node@v4",
        "codecov/codecov-action@v4",
    ]

    failures = []
    for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
        content = workflow_file.read_text(encoding="utf-8")
        for forbidden in forbidden_versions:
            if forbidden in content:
                failures.append(f"{workflow_file.name}: still uses {forbidden}")

    assert not failures, "\n".join(failures)
