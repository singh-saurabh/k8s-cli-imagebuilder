#!/usr/bin/env python3
import unittest
import unittest.mock as mock
import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from kubernetes.client.rest import ApiException

# Add the parent directory to sys.path to import the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions from the main module
import importlib.util
main_module_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker-build-cli.py")
spec = importlib.util.spec_from_file_location("docker_build_cli", main_module_path)
docker_build_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_build_cli)

validate_image_name = docker_build_cli.validate_image_name
build_and_push = docker_build_cli.build_and_push


class TestImageNameValidation(unittest.TestCase):
    """Test cases for Docker image name validation."""
    
    def test_valid_image_names(self):
        """Test that valid image names pass validation."""
        valid_names = [
            "ubuntu:latest",
            "nginx:1.20",
            "myuser/myapp:v1.0",
            "registry.com/namespace/repo:tag",
            "localhost:5000/test:latest",
            "my-app_name.test:latest-2023",
            "simple",
            "a/b",
            "registry.io/user/app:v1.2.3-alpha"
        ]
        
        for name in valid_names:
            with self.subTest(name=name):
                try:
                    validate_image_name(name)
                except ValueError:
                    self.fail(f"Valid image name '{name}' was rejected")
    
    def test_invalid_image_names(self):
        """Test that invalid image names are rejected."""
        invalid_names = [
            "UPPERCASE/invalid",  # Uppercase not allowed
            "name with spaces",   # Spaces not allowed
            "name@with@ats",     # Multiple @ symbols
            "",                  # Empty string
            "a" * 300,          # Too long
            "../../../etc/passwd",  # Path traversal
            "test; echo injection",  # Command injection
            "test && rm -rf /",     # Command chaining
            "registry..com/repo",   # Double dots
            "-starting-with-dash",  # Invalid start character
            "ending-with-dash-",    # Invalid end character
        ]
        
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_image_name(name)
    
    def test_length_validation(self):
        """Test image name length limits."""
        # Test exactly at limit (should pass)
        max_length_name = "a" * 255
        try:
            validate_image_name(max_length_name)
        except ValueError:
            self.fail("Image name at max length (255) should be valid")
        
        # Test over limit (should fail)
        over_limit_name = "a" * 256
        with self.assertRaises(ValueError) as context:
            validate_image_name(over_limit_name)
        self.assertIn("too long", str(context.exception))


class TestKubernetesMocking(unittest.TestCase):
    """Test cases for Kubernetes API interactions using mocks."""
    
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.BatchV1Api')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.walk')
    @patch('builtins.open', new_callable=mock.mock_open, read_data="FROM alpine:latest")
    def test_successful_build_flow(self, mock_file, mock_walk, mock_getsize, mock_exists, 
                                   mock_batch_api, mock_core_api, mock_load_config):
        """Test successful build flow with mocked Kubernetes APIs."""
        
        # Setup mocks
        mock_exists.return_value = True  # Dockerfile exists
        mock_getsize.return_value = 1024  # Small file size
        mock_walk.return_value = [('.', [], ['Dockerfile'])]  # Simple file structure
        
        # Mock Kubernetes API responses
        mock_v1 = MagicMock()
        mock_batch_v1 = MagicMock()
        mock_core_api.return_value = mock_v1
        mock_batch_api.return_value = mock_batch_v1
        
        # Mock successful namespace creation
        mock_v1.create_namespace.return_value = None
        
        # Mock successful secret creation
        mock_v1.create_namespaced_secret.return_value = None
        
        # Mock successful configmap creation
        mock_v1.create_namespaced_config_map.return_value = None
        
        # Mock successful job creation
        mock_batch_v1.create_namespaced_job.return_value = None
        
        # Mock successful job completion
        mock_job_status = MagicMock()
        mock_job_status.status.succeeded = 1
        mock_job_status.status.failed = None
        mock_batch_v1.read_namespaced_job_status.return_value = mock_job_status
        
        # Test the build function
        try:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken", ".")
        except SystemExit as e:
            if e.code != 0:
                self.fail(f"Build failed with exit code {e.code}")
        
        # Verify API calls were made
        mock_load_config.assert_called_once()
        mock_v1.create_namespace.assert_called_once()
        mock_v1.create_namespaced_secret.assert_called_once()
        mock_v1.create_namespaced_config_map.assert_called_once()
        mock_batch_v1.create_namespaced_job.assert_called_once()
    
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.BatchV1Api')
    @patch('os.path.exists')
    def test_missing_dockerfile(self, mock_exists, mock_batch_api, mock_core_api, mock_load_config):
        """Test behavior when Dockerfile is missing."""
        
        # Mock missing Dockerfile
        mock_exists.return_value = False
        
        # Test should exit with error
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken", ".")
        
        # Should exit with code 1
        self.assertEqual(context.exception.code, 1)
        
        # Should not attempt to create Kubernetes resources
        mock_load_config.assert_not_called()
    
    @patch('kubernetes.config.load_kube_config')
    def test_kubernetes_config_failure(self, mock_load_config):
        """Test behavior when Kubernetes config loading fails."""
        
        # Mock config loading failure
        mock_load_config.side_effect = Exception("Config not found")
        
        # Test should exit with error
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken", ".")
        
        self.assertEqual(context.exception.code, 1)
    
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.client.BatchV1Api')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.walk')
    @patch('builtins.open', new_callable=mock.mock_open, read_data="FROM alpine:latest")
    def test_build_failure(self, mock_file, mock_walk, mock_getsize, mock_exists, 
                          mock_batch_api, mock_core_api, mock_load_config):
        """Test behavior when build job fails."""
        
        # Setup basic mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024  # Small file size
        mock_walk.return_value = [('.', [], ['Dockerfile'])]
        
        mock_v1 = MagicMock()
        mock_batch_v1 = MagicMock()
        mock_core_api.return_value = mock_v1
        mock_batch_api.return_value = mock_batch_v1
        
        # Mock successful setup
        mock_v1.create_namespace.return_value = None
        mock_v1.create_namespaced_secret.return_value = None
        mock_v1.create_namespaced_config_map.return_value = None
        mock_batch_v1.create_namespaced_job.return_value = None
        
        # Mock failed job
        mock_job_status = MagicMock()
        mock_job_status.status.succeeded = None
        mock_job_status.status.failed = 1
        mock_batch_v1.read_namespaced_job_status.return_value = mock_job_status
        
        # Mock pod logs for failed job
        mock_pod_list = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-pod"
        mock_pod_list.items = [mock_pod]
        mock_v1.list_namespaced_pod.return_value = mock_pod_list
        mock_v1.read_namespaced_pod_log.return_value = "Build failed: some error"
        
        # Test should exit with error
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken", ".")
        
        self.assertEqual(context.exception.code, 1)
        
        # Verify cleanup was called
        mock_v1.delete_namespaced_secret.assert_called()


class TestCredentialValidation(unittest.TestCase):
    """Test cases for credential validation."""
    
    def test_missing_username(self):
        """Test behavior when DockerHub username is missing."""
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", None, "testtoken", ".")
        
        self.assertEqual(context.exception.code, 1)
    
    def test_missing_token(self):
        """Test behavior when DockerHub token is missing."""
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", None, ".")
        
        self.assertEqual(context.exception.code, 1)


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)