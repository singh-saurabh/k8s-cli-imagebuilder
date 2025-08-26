#!/usr/bin/env python3
import unittest
import unittest.mock as mock
import pytest
import os
import sys
import subprocess
from unittest.mock import patch, MagicMock, mock_open
from kubernetes.client.rest import ApiException

# Add the parent directory to sys.path to import the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions from the main module
import importlib.util
main_module_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker-build-cli.py")
spec = importlib.util.spec_from_file_location("docker_build_cli", main_module_path)
docker_build_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_build_cli)

# Import available functions from the current module
build_and_push = docker_build_cli.build_and_push
validate_dockerfile = docker_build_cli.validate_dockerfile
load_kubernetes_config = docker_build_cli.load_kubernetes_config
wait_for_pod_ready = docker_build_cli.wait_for_pod_ready
upload_build_context = docker_build_cli.upload_build_context
trigger_build = docker_build_cli.trigger_build
load_pod_yaml_template = docker_build_cli.load_pod_yaml_template
wait_for_pod_deletion = docker_build_cli.wait_for_pod_deletion
load_dockerignore = docker_build_cli.load_dockerignore
should_ignore_path = docker_build_cli.should_ignore_path
create_filtered_build_context = docker_build_cli.create_filtered_build_context


class TestDockerfileValidation(unittest.TestCase):
    """Test cases for Dockerfile validation."""
    
    @patch('os.path.exists')
    def test_dockerfile_exists(self, mock_exists):
        """Test Dockerfile validation when file exists."""
        mock_exists.return_value = True
        
        try:
            validate_dockerfile()
        except SystemExit:
            self.fail("validate_dockerfile should not exit when Dockerfile exists")
    
    @patch('os.path.exists')
    def test_dockerfile_missing(self, mock_exists):
        """Test Dockerfile validation when file is missing."""
        mock_exists.return_value = False
        
        with self.assertRaises(SystemExit) as context:
            validate_dockerfile()
        
        self.assertEqual(context.exception.code, 1)


class TestYAMLTemplateLoading(unittest.TestCase):
    """Test cases for YAML template loading."""
    
    @patch('builtins.open', mock_open(read_data="apiVersion: v1\nkind: Pod"))
    @patch('os.path.dirname')
    @patch('os.path.abspath')
    @patch('os.path.join')
    def test_yaml_template_loading(self, mock_join, mock_abspath, mock_dirname):
        """Test successful YAML template loading."""
        mock_dirname.return_value = "/test/dir"
        mock_abspath.return_value = "/test/dir/docker-build-cli.py"
        mock_join.return_value = "/test/dir/buildkit-pod.yaml"
        
        result = load_pod_yaml_template()
        
        self.assertEqual(result, "apiVersion: v1\nkind: Pod")
    
    @patch('builtins.open', side_effect=FileNotFoundError())
    @patch('os.path.dirname')
    @patch('os.path.abspath')  
    @patch('os.path.join')
    def test_yaml_template_missing(self, mock_join, mock_abspath, mock_dirname, mock_file):
        """Test YAML template loading when file is missing."""
        mock_dirname.return_value = "/test/dir"
        mock_abspath.return_value = "/test/dir/docker-build-cli.py"
        mock_join.return_value = "/test/dir/buildkit-pod.yaml"
        
        with self.assertRaises(SystemExit) as context:
            load_pod_yaml_template()
        
        self.assertEqual(context.exception.code, 1)


class TestKubectlOperations(unittest.TestCase):
    """Test cases for kubectl operations."""
    
    @patch('subprocess.run')
    def test_upload_build_context_success(self, mock_run):
        """Test successful build context upload."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        try:
            upload_build_context("test-namespace", "test-pod")
        except SystemExit:
            self.fail("upload_build_context should not exit on success")
        
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("kubectl cp", args)
        self.assertIn("test-namespace", args)
        self.assertIn("test-pod", args)
    
    @patch('subprocess.run')
    def test_upload_build_context_failure(self, mock_run):
        """Test build context upload failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Connection failed"
        mock_run.return_value = mock_result
        
        with self.assertRaises(SystemExit) as context:
            upload_build_context("test-namespace", "test-pod")
        
        self.assertEqual(context.exception.code, 1)
    
    @patch('subprocess.run')
    def test_trigger_build_success(self, mock_run):
        """Test successful build trigger."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        try:
            trigger_build("test-namespace", "test-pod")
        except SystemExit:
            self.fail("trigger_build should not exit on success")
        
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("kubectl exec", args)
        self.assertIn("BUILD_READY", args)


class TestKubernetesMocking(unittest.TestCase):
    """Test cases for Kubernetes API interactions using mocks."""
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.config.load_kube_config')
    def test_successful_build_flow(self, mock_load_config, mock_core_api, mock_exists,
                                   mock_subprocess):
        """Test successful build flow with mocked Kubernetes APIs."""
        
        # Setup mocks
        mock_exists.return_value = True  # Dockerfile exists
        
        # Mock subprocess calls for kubectl operations
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # Mock Kubernetes API responses
        mock_v1 = MagicMock()
        mock_core_api.return_value = mock_v1
        
        # Mock successful namespace creation
        mock_v1.create_namespace.return_value = None
        
        # Mock successful secret creation
        mock_v1.create_namespaced_secret.return_value = None
        
        # Mock no existing pod (404 error)
        mock_v1.read_namespaced_pod.side_effect = [
            ApiException(status=404),  # First call - no existing pod
            # Then successful pod status calls
            MagicMock(status=MagicMock(phase="Running")),  # Pod ready
            MagicMock(status=MagicMock(phase="Succeeded"))  # Pod completed
        ]
        
        # Mock successful pod creation
        mock_v1.create_namespaced_pod.return_value = None
        
        # Mock load_pod_yaml_template function directly on the module
        with patch.object(docker_build_cli, 'load_pod_yaml_template', return_value="apiVersion: v1\nkind: Pod"):
            # Test the build function
            try:
                build_and_push("testuser/testapp:latest", "testuser", "testtoken")
            except SystemExit as e:
                if e.code != 0:
                    self.fail(f"Build failed with exit code {e.code}")
            
            # Verify API calls were made
            mock_load_config.assert_called_once()
            mock_v1.create_namespace.assert_called_once()
            mock_v1.create_namespaced_secret.assert_called_once()
            mock_v1.create_namespaced_pod.assert_called_once()
            
            # Verify kubectl commands were called
            subprocess_calls = mock_subprocess.call_args_list
            self.assertGreaterEqual(len(subprocess_calls), 2)  # At least cp and exec calls
    
    @patch('os.path.exists')
    def test_missing_dockerfile(self, mock_exists):
        """Test behavior when Dockerfile is missing."""
        
        # Mock missing Dockerfile
        mock_exists.return_value = False
        
        # Test should exit with error
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken")
        
        # Should exit with code 1
        self.assertEqual(context.exception.code, 1)
    
    @patch('os.path.exists')
    @patch('kubernetes.config.load_kube_config')
    def test_kubernetes_config_failure(self, mock_load_config, mock_exists):
        """Test behavior when Kubernetes config loading fails."""
        
        mock_exists.return_value = True  # Dockerfile exists
        
        # Mock config loading failure
        mock_load_config.side_effect = Exception("Config not found")
        
        # Test should exit with error
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", "testtoken")
        
        self.assertEqual(context.exception.code, 1)
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('kubernetes.client.CoreV1Api')
    @patch('kubernetes.config.load_kube_config')
    def test_build_failure(self, mock_load_config, mock_core_api, mock_exists,
                          mock_subprocess):
        """Test behavior when build pod fails."""
        
        # Setup basic mocks
        mock_exists.return_value = True
        
        # Mock successful kubectl commands
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        mock_v1 = MagicMock()
        mock_core_api.return_value = mock_v1
        
        # Mock successful setup
        mock_v1.create_namespace.return_value = None
        mock_v1.create_namespaced_secret.return_value = None
        mock_v1.create_namespaced_pod.return_value = None
        
        # Mock pod status progression: no existing pod → running → failed
        mock_v1.read_namespaced_pod.side_effect = [
            ApiException(status=404),  # No existing pod
            MagicMock(status=MagicMock(phase="Running")),  # Pod ready
            MagicMock(status=MagicMock(phase="Failed"))    # Pod failed
        ]
        
        # Mock pod logs for failed build
        mock_v1.read_namespaced_pod_log.return_value = "Build failed: some error"
        
        # Mock load_pod_yaml_template function
        with patch.object(docker_build_cli, 'load_pod_yaml_template', return_value="apiVersion: v1\nkind: Pod"):
            # Test should exit with error
            with self.assertRaises(SystemExit) as context:
                build_and_push("testuser/testapp:latest", "testuser", "testtoken")
            
            self.assertEqual(context.exception.code, 1)
            
            # Verify cleanup was called
            mock_v1.delete_namespaced_secret.assert_called()


class TestCredentialValidation(unittest.TestCase):
    """Test cases for credential validation."""
    
    @patch('os.path.exists')
    def test_missing_username(self, mock_exists):
        """Test behavior when DockerHub username is missing."""
        mock_exists.return_value = True  # Dockerfile exists
        
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", None, "testtoken")
        
        self.assertEqual(context.exception.code, 1)
    
    @patch('os.path.exists') 
    def test_missing_token(self, mock_exists):
        """Test behavior when DockerHub token is missing."""
        mock_exists.return_value = True  # Dockerfile exists
        
        with self.assertRaises(SystemExit) as context:
            build_and_push("testuser/testapp:latest", "testuser", None)
        
        self.assertEqual(context.exception.code, 1)


class TestPodDeletionWaiting(unittest.TestCase):
    """Test cases for pod deletion waiting logic."""
    
    @patch('time.sleep')  # Speed up test by mocking sleep
    def test_wait_for_pod_deletion_success(self, mock_sleep):
        """Test successful pod deletion waiting."""
        mock_v1 = MagicMock()
        
        # First call: pod exists, second call: pod not found (404)
        mock_v1.read_namespaced_pod.side_effect = [
            MagicMock(),  # Pod exists
            ApiException(status=404)  # Pod not found (deleted)
        ]
        
        result = wait_for_pod_deletion(mock_v1, "test-namespace", "test-pod", timeout=5)
        
        self.assertTrue(result)
        mock_v1.read_namespaced_pod.assert_called()
    
    @patch('time.sleep')  # Speed up test
    def test_wait_for_pod_deletion_timeout(self, mock_sleep):
        """Test pod deletion timeout."""
        mock_v1 = MagicMock()
        
        # Pod always exists (never gets deleted)
        mock_v1.read_namespaced_pod.return_value = MagicMock()
        
        result = wait_for_pod_deletion(mock_v1, "test-namespace", "test-pod", timeout=1)
        
        self.assertFalse(result)


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)