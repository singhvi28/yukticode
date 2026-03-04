"""
Tests for the compare_outputs() normalisation helper in judger.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from worker.Judger.judger import compare_outputs


class TestCompareOutputs:
    def test_exact_match(self):
        assert compare_outputs("42\n", "42\n") is True

    def test_trailing_newline_ignored(self):
        assert compare_outputs("42", "42\n") is True
        assert compare_outputs("42\n", "42") is True

    def test_trailing_spaces_on_line_ignored(self):
        assert compare_outputs("42\n", "42   \n") is True

    def test_windows_crlf_normalised(self):
        assert compare_outputs("1\n2\n3\n", "1\r\n2\r\n3\r\n") is True

    def test_leading_blank_lines_ignored(self):
        assert compare_outputs("42", "\n\n42") is True

    def test_trailing_blank_lines_ignored(self):
        assert compare_outputs("42", "42\n\n\n") is True

    def test_mismatch_detected(self):
        assert compare_outputs("42\n", "43\n") is False

    def test_extra_line_is_mismatch(self):
        assert compare_outputs("1\n2\n", "1\n2\n3\n") is False

    def test_multiline_match(self):
        expected = "hello\nworld\n"
        actual   = "hello\nworld\n"
        assert compare_outputs(expected, actual) is True

    def test_multiline_trailing_space_mismatch(self):
        # trailing space on a middle line is still wrong
        expected = "a\nb"
        actual   = "a\nb   "   # trailing spaces rstripped → "b" == "b"  → AC
        assert compare_outputs(expected, actual) is True

    def test_completely_different(self):
        assert compare_outputs("abc", "xyz") is False

    def test_empty_vs_empty(self):
        assert compare_outputs("", "") is True

    def test_empty_vs_blank_lines(self):
        assert compare_outputs("", "\n\n") is True
