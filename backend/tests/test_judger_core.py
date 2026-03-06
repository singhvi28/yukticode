"""
Tests for worker/Judger/judger.py
All integrations mocked. File I/O uses tmp_path.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock


from worker.Judger.judger import SecurityViolationException, check_forbidden_patterns


def _make_mock_language(run_exit_code=0, compile_exit_code=0):
    lang = MagicMock()
    lang.compile.return_value = (compile_exit_code, "")
    lang.run.return_value = (run_exit_code, "")
    return lang


class TestRunJudger:
    def test_returns_ac_when_outputs_match(self):
        from worker.Judger.judger import run_judger
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract, \
             patch('worker.Judger.judger._collect_stats', return_value=0.0):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()

            # extract_file_from_container is called twice on successful run: expected then actual
            mock_extract.side_effect = ["42\n", "42\n"]

            result = run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "AC"
        assert "execution_time_ms" in result
        assert "peak_memory_mb" in result

    def test_returns_wa_when_outputs_differ(self):
        from worker.Judger.judger import run_judger
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract, \
             patch('worker.Judger.judger._collect_stats', return_value=0.0):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            # Expected "42", got "99"
            mock_extract.side_effect = ["42\n", "99\n"]

            result = run_judger('cpp', 2, 256, src_code='int main(){}', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "WA"

    def test_handles_compile_error(self):
        from worker.Judger.judger import run_judger
        # CE has exit code 1
        mock_lang = _make_mock_language(compile_exit_code=1)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "CE"

    def test_handles_runtime_exception(self):
        from worker.Judger.judger import run_judger
        mock_lang = MagicMock()
        mock_lang.compile.side_effect = RuntimeError("boom")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "SYSTEM_ERROR"


class TestCustomRun:
    def test_returns_ac_and_output_on_success(self):
        from worker.Judger.judger import custom_run
        mock_lang = _make_mock_language(run_exit_code=0)

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger.extract_file_from_container') as mock_extract:

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            mock_extract.return_value = "hello\n"

            result = custom_run('py', 2, 256, src_code='print("hello")', std_in='')

        assert result == ("AC", "hello\n")

    def test_handles_exception(self):
        from worker.Judger.judger import custom_run
        mock_lang = MagicMock()
        mock_lang.run.side_effect = RuntimeError("oops")

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = MagicMock()
            result = custom_run('py', 2, 256, src_code='x', std_in='')

        assert result == ("SYSTEM_ERROR", "")


class TestTLEHandling:
    def test_run_judger_returns_tle_when_timeout_raised(self):
        from worker.Judger.judger import run_judger
        from worker.Judger.languages.base import TLEException

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")
        mock_lang.run.side_effect = TLEException("Exceeded 2s")

        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'), \
             patch('worker.Judger.judger._collect_stats', return_value=0.0):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            result = run_judger('cpp', 2, 256, src_code='x', test_cases=[{"input": "", "expected_output": "42"}])

        assert result["verdict"] == "TLE"
        mock_container.stop.assert_called_once_with(timeout=2)

    def test_custom_run_returns_tle_when_timeout_raised(self):
        from worker.Judger.judger import custom_run
        from worker.Judger.languages.base import TLEException

        mock_lang = MagicMock()
        mock_lang.compile.return_value = (0, "")   # compile succeeds
        mock_lang.run.side_effect = TLEException("Exceeded 2s")

        mock_container = MagicMock()

        with patch('worker.Judger.judger.DockerManager') as mock_dm_cls, \
             patch('worker.Judger.judger.get_language_instance', return_value=mock_lang), \
             patch('worker.Judger.judger.put_files_to_container'):

            mock_dm_cls.return_value.start_container.return_value = mock_container
            result = custom_run('cpp', 2, 256, src_code='x', std_in='')

        assert result == ("TLE", "")
        mock_container.stop.assert_called_once_with(timeout=2)


class TestStaticAnalysis:
    def test_check_forbidden_patterns_python_safe(self):
        src = "print('hello world')\nimport math\nmath.sqrt(4)"
        check_forbidden_patterns("py", src)  # Should not raise

    def test_check_forbidden_patterns_python_os_system(self):
        src = "import os\nos.system('rm -rf /')"
        with pytest.raises(SecurityViolationException, match="os.system"):
            check_forbidden_patterns("py", src)

    def test_check_forbidden_patterns_python_subprocess(self):
        src = "import subprocess\nsubprocess.run(['ls'])"
        with pytest.raises(SecurityViolationException, match="subprocess"):
            check_forbidden_patterns("py", src)

    def test_check_forbidden_patterns_python_eval(self):
        src = "eval('1 + 1')"
        with pytest.raises(SecurityViolationException, match="eval"):
            check_forbidden_patterns("py", src)

    def test_check_forbidden_patterns_python_exec(self):
        src = "exec('x = 1')"
        with pytest.raises(SecurityViolationException, match="exec"):
            check_forbidden_patterns("py", src)

    def test_check_forbidden_patterns_python_import(self):
        src = "sys = ['__import__']('os')"
        with pytest.raises(SecurityViolationException, match="['__import__']"):
            check_forbidden_patterns("py", src)

    def test_check_forbidden_patterns_cpp_safe(self):
        src = "#include <iostream>\nint main() { return 0; }"
        check_forbidden_patterns("cpp", src)  # Should not raise

    def test_check_forbidden_patterns_cpp_cstdlib(self):
        src = "#include <cstdlib>\nint main() { return 0; }"
        with pytest.raises(SecurityViolationException, match="<cstdlib>"):
            check_forbidden_patterns("cpp", src)

    def test_check_forbidden_patterns_cpp_system(self):
        src = "int main() { system(\"ls\"); return 0; }"
        with pytest.raises(SecurityViolationException, match=r"system\("):
            check_forbidden_patterns("cpp", src)

    def test_check_forbidden_patterns_cpp_popen(self):
        src = "int main() { popen(\"ls\"); return 0; }"
        with pytest.raises(SecurityViolationException, match=r"popen\("):
            check_forbidden_patterns("cpp", src)

    def test_check_forbidden_patterns_cpp_fork(self):
        src = "int main() { fork(); return 0; }"
        with pytest.raises(SecurityViolationException, match=r"fork\("):
            check_forbidden_patterns("cpp", src)

    def test_run_judger_returns_ce_on_security_violation(self):
        from worker.Judger.judger import run_judger
        # No Docker mocks needed — static analysis fires before container is touched
        result = run_judger('py', 1, 128, src_code="import os\nos.system('ls')", test_cases=[{"input": "", "expected_output": ""}])
        assert result["verdict"] == "CE"

    def test_custom_run_returns_ce_on_security_violation(self):
        from worker.Judger.judger import custom_run
        result = custom_run('cpp', 1, 128, src_code="system('ls')", std_in='')
        assert result == ("CE", "")
