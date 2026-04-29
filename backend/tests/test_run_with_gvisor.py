"""
Unit tests for BaseLanguage.run_with_gvisor sandbox/metrics behaviour.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock

from worker.Judger.languages.base import BaseLanguage, SandboxError, MLEException, TLEException


class _FakeLang(BaseLanguage):
    def __init__(self, container):
        self.container = container

    def compile(self, submission_id):
        return 0, ""

    def run(self, submission_id):
        return self.run_with_gvisor("/workspace/UserProgram", 2000, 256)


def _container_with_exec(side_effects):
    """
    side_effects: list of (exit_code, bytes|None) for successive exec_run calls.
    Order: clear outputs, run_cmd, cat time.txt, [optional cat error_log].
    """
    container = MagicMock()
    container.exec_run.side_effect = side_effects
    return container


class TestRunWithGvisor:
    def test_exit_127_raises_sandbox_error(self):
        container = _container_with_exec([
            (0, b""),          # rm
            (127, b""),        # run_cmd — /usr/bin/time missing
        ])
        lang = _FakeLang(container)
        with pytest.raises(SandboxError, match="exit code 127"):
            lang.run("id")

    def test_missing_metrics_raises_sandbox_error(self):
        container = _container_with_exec([
            (0, b""),          # rm
            (0, b""),          # run succeeded
            (1, b""),          # cat time.txt failed
        ])
        lang = _FakeLang(container)
        with pytest.raises(SandboxError, match="Failed to collect execution metrics"):
            lang.run("id")

    def test_peak_memory_over_limit_raises_mle(self):
        # 300MB peak > 256MB limit  (300 * 1024 = 307200 KB)
        metrics = b"MEM:307200 CPU:0.010+0.010"
        container = _container_with_exec([
            (0, b""),
            (0, b""),
            (0, metrics),
        ])
        lang = _FakeLang(container)
        with pytest.raises(MLEException):
            lang.run("id")

    def test_success_returns_metrics(self):
        metrics = b"MEM:10240 CPU:0.050+0.010"
        container = _container_with_exec([
            (0, b""),
            (0, b""),
            (0, metrics),
            (0, b""),  # stderr
        ])
        lang = _FakeLang(container)
        exit_code, _, time_ms, mem_mb, _ = lang.run("id")
        assert exit_code == 0
        assert abs(mem_mb - 10.0) < 0.01
        assert abs(time_ms - 60.0) < 0.1
