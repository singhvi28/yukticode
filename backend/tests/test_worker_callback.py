"""
Tests for worker/grpc_client.py — verdict reporting helpers.
gRPC channel/stub are fully mocked; no network required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'worker'))

from unittest.mock import patch, MagicMock


class TestReportSubmitVerdict:
    def test_builds_request_and_calls_stub(self):
        mock_stub = MagicMock()
        mock_channel = MagicMock()
        mock_channel.__enter__ = MagicMock(return_value=mock_channel)
        mock_channel.__exit__ = MagicMock(return_value=False)

        with patch('grpc_client.grpc.insecure_channel', return_value=mock_channel), \
             patch('grpc_client.judger_pb2_grpc.JudgeCoordinatorStub', return_value=mock_stub), \
             patch('grpc_client.judger_pb2') as mock_pb2:
            mock_pb2.SubmitVerdictRequest.return_value = MagicMock(name='req')

            from grpc_client import report_submit_verdict
            report_submit_verdict(submission_id=42, status="AC", time_ms=12.5, mem_mb=8.0)

        mock_pb2.SubmitVerdictRequest.assert_called_once_with(
            submission_id="42",
            status="AC",
            execution_time_ms=12.5,
            peak_memory_mb=8.0,
        )
        mock_stub.ReportSubmitVerdict.assert_called_once()


class TestReportRunVerdict:
    def test_builds_request_and_calls_stub(self):
        mock_stub = MagicMock()
        mock_channel = MagicMock()
        mock_channel.__enter__ = MagicMock(return_value=mock_channel)
        mock_channel.__exit__ = MagicMock(return_value=False)

        with patch('grpc_client.grpc.insecure_channel', return_value=mock_channel), \
             patch('grpc_client.judger_pb2_grpc.JudgeCoordinatorStub', return_value=mock_stub), \
             patch('grpc_client.judger_pb2') as mock_pb2:
            mock_pb2.RunVerdictRequest.return_value = MagicMock(name='req')

            from grpc_client import report_run_verdict
            report_run_verdict(
                run_id="abc", status="AC", std_out="1\n",
                time_ms=3.0, mem_mb=1.5, test_index=0,
            )

        mock_pb2.RunVerdictRequest.assert_called_once_with(
            run_id="abc",
            status="AC",
            std_out="1\n",
            execution_time_ms=3.0,
            peak_memory_mb=1.5,
            test_index=0,
        )
        mock_stub.ReportRunVerdict.assert_called_once()


class TestStreamBatchVerdicts:
    def test_streams_all_results(self):
        mock_stub = MagicMock()
        mock_channel = MagicMock()
        mock_channel.__enter__ = MagicMock(return_value=mock_channel)
        mock_channel.__exit__ = MagicMock(return_value=False)

        captured = []

        def _capture(gen):
            captured.extend(list(gen))
            return MagicMock()

        mock_stub.StreamBatchRunVerdict.side_effect = _capture

        with patch('grpc_client.grpc.insecure_channel', return_value=mock_channel), \
             patch('grpc_client.judger_pb2_grpc.JudgeCoordinatorStub', return_value=mock_stub), \
             patch('grpc_client.judger_pb2') as mock_pb2:
            mock_pb2.RunVerdictRequest.side_effect = lambda **kw: kw

            from grpc_client import stream_batch_verdicts
            stream_batch_verdicts("batch-1", iter([
                {"test_index": 0, "status": "AC", "std_out": "1", "time_ms": 1.0, "mem_mb": 2.0},
                {"test_index": 1, "status": "WA", "std_out": "0", "time_ms": 2.0, "mem_mb": 3.0},
            ]))

        assert len(captured) == 2
        assert captured[0]["run_id"] == "batch-1"
        assert captured[1]["status"] == "WA"
        mock_stub.StreamBatchRunVerdict.assert_called_once()
