import sys
import os
import tarfile
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock
from worker.Judger.file_utils import put_files_to_container, extract_file_from_container


def test_put_files_streams_tar_to_container():
    print("STARTING test_put_files_streams_tar_to_container")
    mock_container = MagicMock()
    
    put_files_to_container(mock_container, "py", "print(1)", "input_val", "expected_val")
    
    # Verify put_archive was called with the right path
    mock_container.put_archive.assert_called_once()
    args, _ = mock_container.put_archive.call_args
    assert args[0] == "/workspace"
    
    # Read the tar stream passed in
    tar_stream = args[1]
    tar_stream.seek(0)
    
    # Extract the tar in-memory to verify contents
    with tarfile.open(fileobj=tar_stream, mode='r') as tar:
        members = tar.getnames()
        assert "main.py" in members
        assert "input.txt" in members
        assert "expected_op.txt" in members
        
        main_py = tar.extractfile("main.py").read().decode('utf-8')
        assert main_py == "print(1)"
        
        input_txt = tar.extractfile("input.txt").read().decode('utf-8')
        assert input_txt == "input_val"
        
        expected_op = tar.extractfile("expected_op.txt").read().decode('utf-8')
        assert expected_op == "expected_val"


def test_extract_file_reads_from_stream():
    print("STARTING test_extract_file_reads_from_stream")
    mock_container = MagicMock()
    
    # Create an in-memory tarball matching what Docker's get_archive returns
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
        content_bytes = "42".encode('utf-8')
        tarinfo = tarfile.TarInfo(name="actual_op.txt")
        tarinfo.size = len(content_bytes)
        tar.addfile(tarinfo, io.BytesIO(content_bytes))
    
    # get_archive returns (stream, stat)
    # The stream is typically a socket-like object that yields chunks. Look at how Extract works: 
    # it expects an iterable of bytes.
    tar_stream.seek(0)
    mock_container.get_archive.return_value = ([tar_stream.read()], {"name": "actual_op.txt"})
    
    output = extract_file_from_container(mock_container, "/workspace/actual_op.txt")
    assert output == "42"


def test_extract_file_handles_failure():
    print("STARTING test_extract_file_handles_failure")
    mock_container = MagicMock()
    mock_container.get_archive.side_effect = Exception("Docker engine died")
    
    output = extract_file_from_container(mock_container, "/workspace/actual_op.txt")
    assert output == ""
