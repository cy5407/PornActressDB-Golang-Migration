import pytest
from unittest.mock import MagicMock, patch

from src.services.go_runner import (
    GoBridgeError,
    GoBridgeExecError,
    GoBridgeJSONError,
    GoBridgeNotFoundError,
    GoCommandRunner,
)


class TestGoBridgeErrorHierarchy:
    def test_exec_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeExecError, GoBridgeError)

    def test_not_found_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeNotFoundError, GoBridgeError)

    def test_json_error_is_go_bridge_error(self):
        assert issubclass(GoBridgeJSONError, GoBridgeError)


class TestGoCommandRunnerErrors:
    def test_nonzero_returncode_raises_exec_error(self):
        runner = GoCommandRunner("/fake/classifier.exe")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeExecError) as exc:
                runner.run(["db", "get", "FAKE"])
        assert exc.value.returncode == 1

    def test_not_found_in_stderr_raises_not_found_error(self):
        runner = GoCommandRunner("/fake/classifier.exe")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "video not found: FAKE-001"
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeNotFoundError):
                runner.run(["db", "get", "FAKE-001"])

    def test_invalid_json_raises_json_error(self):
        runner = GoCommandRunner("/fake/classifier.exe")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json {"
        mock_result.stderr = ""
        with patch("src.services.go_runner.run_subprocess", return_value=mock_result):
            with pytest.raises(GoBridgeJSONError):
                runner.run_json(["db", "list"])
