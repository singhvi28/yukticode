"""
Tests for worker/Judger/judger.py
All integrations mocked. File I/O uses tmp_path.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock


from worker.Judger.judger import run_judger, custom_run, compare_outputs


def _make_mock_language(run_exit_code=0, compile_exit_code=0):
    lang = MagicMock()
    lang.compile.return_value = (compile_exit_code, "")
    # run() returns: (exit_code, stdout, isolate_time, isolate_mem, stderr)
    lang.run.return_value = (run_exit_code, "", 100.0, 15.5, "")
    return lang


class TestRunJudger:
    def test_returns_ac_when_outputs_match(self):
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract:

            mock_dm_cls.return_value.start_container.return_value = MagicMock()

            # extract_file_from_container is now called ONCE per test case (only actual_op.txt)
            # Expected output is kept in memory, never extracted from container
            mock_extract.side_effect = ["42\n"]

            result = run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "AC"
        assert "execution_time_ms" in result
        assert "peak_memory_mb" in result

    def test_returns_wa_when_outputs_differ(self):
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract:

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            # Actual output is "99", expected is "42" (kept in test_cases, not from container)
            mock_extract.side_effect = ["99\n"]

            result = run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "WA"

    def test_handles_compile_error(self):
        # CE has exit code 1
        mock_lang = _make_mock_language(compile_exit_code=1)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "CE"

    def test_handles_runtime_exception(self):
        mock_lang = MagicMock()
        mock_lang.compile.side_effect = RuntimeError("boom")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "SYSTEM_ERROR"

    def test_handles_docker_exception(self):
        import docker.errors

        # Simulate docker.from_env() crashing with PermissionError (DockerException)
        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls:
            mock_dm_cls.side_effect = docker.errors.DockerException("Connection aborted: Permission denied")
            result = run_judger('py', 2, 256, src_code='print(1)', test_cases=[{"input": "", "expected_output": "1"}])

        assert result["verdict"] == "SYSTEM_ERROR"

    def test_container_is_removed_after_judging(self):
        """Zombie container fix: container.remove(force=True) must be called in finally."""
        mock_lang = _make_mock_language(run_exit_code=0)
        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container', return_value="42\n"):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        mock_container.remove.assert_called_once_with(force=True)

    def test_expected_output_not_extracted_from_container(self):
        """Security fix: extract_file_from_container must only be called once (actual_op.txt only)."""
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container', return_value="42\n") as mock_extract:

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        # Must be called exactly once per test case — only actual_op.txt, never expected_op.txt
        assert mock_extract.call_count == 1
        call_args = mock_extract.call_args[0]
        assert "actual_op.txt" in call_args[1]
        assert "expected_op.txt" not in call_args[1]


class TestCustomRun:
    def test_returns_ac_and_output_on_success(self):
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract:

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            mock_extract.return_value = "hello\n"

            result = custom_run('py', 2, 256, src_code='print("hello")', std_in='')

        assert result["verdict"] == "AC"
        assert result["output"] == "hello\n"

    def test_handles_exception(self):
        mock_lang = MagicMock()
        mock_lang.run.side_effect = RuntimeError("oops")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = custom_run('py', 2, 256, src_code='x', std_in='')

        assert result["verdict"] == "SYSTEM_ERROR"

    def test_container_is_removed_after_custom_run(self):
        """Zombie container fix: container.remove(force=True) must be called in finally."""
        mock_lang = _make_mock_language(run_exit_code=0)
        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container', return_value="hello\n"):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            custom_run('py', 2, 256, src_code='print("hello")', std_in='')

        mock_container.remove.assert_called_once_with(force=True)


class TestTLEHandling:
    def test_run_judger_returns_tle_when_timeout_raised(self):
        from worker.Judger.languages.base import TLEException

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.side_effect = TLEException("Exceeded 2s")

        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "TLE"
        mock_container.stop.assert_called_once_with(timeout=1)
        mock_container.remove.assert_called_once_with(force=True)

    def test_custom_run_returns_tle_when_timeout_raised(self):
        from worker.Judger.languages.base import TLEException

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.side_effect = TLEException("Exceeded 2s")

        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            result = custom_run('cpp', 2, 256, src_code='x', std_in='')

        assert result["verdict"] == "TLE"
        mock_container.stop.assert_called_once_with(timeout=1)
        mock_container.remove.assert_called_once_with(force=True)


class TestCompareOutputs:
    def test_exact_match(self):
        assert compare_outputs("42\n", "42\n") is True

    def test_trailing_whitespace_ignored(self):
        assert compare_outputs("42  \n", "42\n") is True

    def test_leading_blank_lines_ignored(self):
        assert compare_outputs("\n42\n", "42\n") is True

    def test_trailing_blank_lines_ignored(self):
        assert compare_outputs("42\n\n", "42\n") is True

    def test_different_values_returns_false(self):
        assert compare_outputs("42\n", "99\n") is False

    def test_empty_vs_empty(self):
        assert compare_outputs("", "") is True

    def test_oom_guard_returns_false_on_oversized_output(self):
        from worker.Judger.judger import MAX_READ_BYTES
        huge = "x" * (MAX_READ_BYTES + 1)
        assert compare_outputs(huge, "x") is False


class TestSandboxErrorHandling:
    def test_run_judger_returns_system_error_on_sandbox_fault(self):
        from worker.Judger.languages.base import SandboxError
        from worker.Judger.judger import run_judger

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.side_effect = SandboxError("missing /usr/bin/time")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = run_judger('cpp', 2000, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "SYSTEM_ERROR"
        assert "missing /usr/bin/time" in result["message"]

    def test_custom_run_returns_mle_on_mle_exception(self):
        from worker.Judger.languages.base import MLEException
        from worker.Judger.judger import custom_run

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.side_effect = MLEException("over", peak_memory_mb=300.0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = custom_run('py', 2000, 256, src_code='x', std_in='')

        assert result["verdict"] == "MLE"
        assert result["peak_memory_mb"] == 300.0


class TestCustomRunBatch:
    def test_compiles_once_and_runs_each_test(self):
        from worker.Judger.judger import custom_run_batch

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.return_value = (0, "", 50.0, 10.0, "")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container', side_effect=["1\n", "2\n"]):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            results = list(custom_run_batch(
                'cpp', 2000, 256,
                src_code='int main(){}',
                tests=[{"input": "1"}, {"input": "2"}],
            ))

        assert mock_lang.compile.call_count == 1
        assert mock_lang.run.call_count == 2
        assert mock_dm_cls.return_value.start_container.call_count == 1
        assert [r["verdict"] for r in results] == ["AC", "AC"]
        assert results[0]["output"] == "1\n"

    def test_ce_short_circuits_all_tests(self):
        from worker.Judger.judger import custom_run_batch

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (1, "error: boom")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            results = list(custom_run_batch(
                'cpp', 2000, 256,
                src_code='bad',
                tests=[{"input": "1"}, {"input": "2"}, {"input": "3"}],
            ))

        assert mock_lang.run.call_count == 0
        assert len(results) == 3
        assert all(r["verdict"] == "CE" for r in results)
