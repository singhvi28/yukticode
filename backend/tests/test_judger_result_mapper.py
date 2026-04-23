"""
Tests for worker/Judger/result_mapper.py — map_exit_code().
These are pure-function tests with no external dependencies.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from worker.Judger.result_mapper import map_exit_code


class TestMapExitCode:
    def test_zero_is_accepted(self):
        assert map_exit_code(0) == "AC"

    def test_one_is_runtime_error(self):
        assert map_exit_code(1) == "RE"

    def test_143_is_tle(self):
        assert map_exit_code(143) == "TLE"

    def test_137_is_mle(self):
        assert map_exit_code(137) == "MLE"

    def test_unmapped_exit_code_is_re(self):
        assert map_exit_code(99) == "RE"

    def test_negative_exit_code_is_re(self):
        assert map_exit_code(-1) == "RE"

    def test_command_not_found_is_system_error(self):
        assert map_exit_code(127) == "SYSTEM_ERROR"
        assert map_exit_code(126) == "SYSTEM_ERROR"

    def test_segfault_is_re(self):
        assert map_exit_code(139) == "RE"
        assert map_exit_code(134) == "RE"

    def test_return_type_is_always_str(self):
        for code in [0, 1, 137, 143, 999]:
            result = map_exit_code(code)
            assert isinstance(result, str), f"Expected str for code {code}, got {type(result)}"

    @pytest.mark.parametrize("code,expected", [
        (0,   "AC"),
        (1,   "RE"),
        (143, "TLE"),
        (137, "MLE"),
        (2,   "RE"),
        (126, "SYSTEM_ERROR"),
        (127, "SYSTEM_ERROR"),
        (139, "RE"),
        (255, "RE"),
    ])
    def test_all_known_codes(self, code, expected):
        assert map_exit_code(code) == expected
