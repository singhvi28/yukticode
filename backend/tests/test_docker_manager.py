"""
Tests for worker/Judger/docker_manager.py
The docker SDK is fully mocked.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
import docker


def _make_dm(submission_id="test-123", **kwargs):
    from worker.Judger.docker_manager import DockerManager
    return DockerManager(submission_id=submission_id, time_limit=2, memory_limit=256, **kwargs)


class TestDockerManagerStartContainer:
    def test_creates_ephemeral_container_with_auto_remove(self):
        with patch('worker.Judger.docker_manager.docker') as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.ImageNotFound = docker.errors.ImageNotFound
            
            # Pretend image exists
            mock_image = MagicMock()
            mock_client.images.get.return_value = mock_image
            
            dm = _make_dm(submission_id="abc-456")
            dm.start_container()

            mock_client.containers.run.assert_called_once()
            _, kwargs = mock_client.containers.run.call_args
            
            assert kwargs['name'] == "judger-abc-456"
            assert kwargs['auto_remove'] is True
            assert kwargs['mem_limit'] == '256m'
            assert kwargs['network_disabled'] is True

    def test_builds_image_if_not_found(self):
        with patch('worker.Judger.docker_manager.docker') as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            mock_docker.errors.ImageNotFound = docker.errors.ImageNotFound

            # Image missing
            mock_client.images.get.side_effect = docker.errors.ImageNotFound('not found')
            
            mock_image = MagicMock()
            mock_image.id = 'sha256:new'
            mock_client.images.build.return_value = (mock_image, [])

            dm = _make_dm(submission_id="test-build")
            dm.start_container()

            mock_client.images.build.assert_called_once()
            _, kwargs = mock_client.images.build.call_args
            assert kwargs['forcerm'] is True
            
            mock_client.containers.run.assert_called_once()
