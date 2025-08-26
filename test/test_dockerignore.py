#!/usr/bin/env python3
import unittest
import unittest.mock as mock
import pytest
import os
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add the parent directory to sys.path to import the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions from the main module
import importlib.util
main_module_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker-build-cli.py")
spec = importlib.util.spec_from_file_location("docker_build_cli", main_module_path)
docker_build_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_build_cli)

# Import dockerignore functions
load_dockerignore = docker_build_cli.load_dockerignore
should_ignore_path = docker_build_cli.should_ignore_path
create_filtered_build_context = docker_build_cli.create_filtered_build_context
upload_build_context = docker_build_cli.upload_build_context


class TestDockerignoreFunctionality(unittest.TestCase):
    """Test cases for .dockerignore file functionality."""
    
    @patch('pathlib.Path.exists')
    def test_load_dockerignore_missing_file(self, mock_exists):
        """Test loading when .dockerignore file doesn't exist."""
        mock_exists.return_value = False
        
        result = load_dockerignore()
        
        self.assertIsNone(result)
    
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.exists')
    def test_load_dockerignore_success(self, mock_exists, mock_read_text):
        """Test successful .dockerignore loading."""
        mock_exists.return_value = True
        mock_read_text.return_value = "node_modules/\n*.log\n# Comment line"
        
        result = load_dockerignore()
        
        self.assertIsNotNone(result)
        mock_read_text.assert_called_once()
    
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.exists')
    def test_load_dockerignore_parse_error(self, mock_exists, mock_read_text):
        """Test .dockerignore loading with parse error."""
        mock_exists.return_value = True
        mock_read_text.side_effect = Exception("Read error")
        
        result = load_dockerignore()
        
        self.assertIsNone(result)
    
    def test_should_ignore_path_no_spec(self):
        """Test path checking when no spec is provided."""
        result = should_ignore_path(None, "some/file.txt")
        
        self.assertFalse(result)
    
    @patch('pathlib.Path.cwd')
    def test_should_ignore_path_with_spec(self, mock_cwd):
        """Test path checking with a spec."""
        # Mock current working directory
        mock_cwd.return_value = Path("/test")
        
        # Create a mock pathspec that ignores .log files
        mock_spec = MagicMock()
        mock_spec.match_file.return_value = True
        
        result = should_ignore_path(mock_spec, "/test/app.log")
        
        self.assertTrue(result)
        mock_spec.match_file.assert_called_once()
    
    @patch('shutil.rmtree')
    @patch('shutil.copy2')
    @patch('pathlib.Path.mkdir')
    @patch('os.walk')
    @patch('tempfile.mkdtemp')
    def test_create_filtered_build_context_success(self, mock_mkdtemp, mock_walk, 
                                                   mock_mkdir, mock_copy2, mock_rmtree):
        """Test successful filtered build context creation."""
        # Setup mocks
        mock_mkdtemp.return_value = "/tmp/test-context"
        mock_walk.return_value = [
            (".", [], ["Dockerfile", "app.py", "node_modules"]),
            ("./src", [], ["main.py", "test.log"])
        ]
        
        # Mock spec that ignores .log files
        mock_spec = MagicMock()
        mock_spec.match_file.side_effect = lambda path: path.endswith('.log')
        
        with patch.object(docker_build_cli, 'should_ignore_path', side_effect=lambda spec, path: str(path).endswith('.log')):
            result = create_filtered_build_context(mock_spec)
        
        self.assertEqual(result, "/tmp/test-context")
        mock_copy2.assert_called()  # Should copy some files
    
    @patch('shutil.rmtree')
    @patch('tempfile.mkdtemp')
    @patch('os.walk')
    def test_create_filtered_build_context_error(self, mock_walk, mock_mkdtemp, mock_rmtree):
        """Test filtered build context creation with error."""
        mock_mkdtemp.return_value = "/tmp/test-context"
        mock_walk.side_effect = Exception("OS Error")
        
        with self.assertRaises(SystemExit) as context:
            create_filtered_build_context(None)
        
        self.assertEqual(context.exception.code, 1)
        mock_rmtree.assert_called_with("/tmp/test-context", ignore_errors=True)
    
    @patch('subprocess.run')
    @patch('shutil.rmtree')
    @patch.object(docker_build_cli, 'load_dockerignore')
    def test_upload_build_context_no_dockerignore(self, mock_load_dockerignore, 
                                                  mock_rmtree, mock_subprocess):
        """Test upload build context when no .dockerignore exists."""
        # Mock no .dockerignore
        mock_load_dockerignore.return_value = None
        
        # Mock successful subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        try:
            upload_build_context("test-namespace", "test-pod")
        except SystemExit:
            self.fail("upload_build_context should not exit on success")
        
        # Should use current directory
        args = mock_subprocess.call_args[0][0]
        self.assertIn("kubectl cp .", args)
        mock_rmtree.assert_not_called()  # No temp dir to clean up
    
    @patch('subprocess.run')
    @patch('shutil.rmtree')
    @patch.object(docker_build_cli, 'create_filtered_build_context')
    @patch.object(docker_build_cli, 'load_dockerignore')
    def test_upload_build_context_with_dockerignore(self, mock_load_dockerignore,
                                                    mock_create_filtered, mock_rmtree,
                                                    mock_subprocess):
        """Test upload build context with .dockerignore filtering."""
        # Mock .dockerignore exists
        mock_spec = MagicMock()
        mock_load_dockerignore.return_value = mock_spec
        mock_create_filtered.return_value = "/tmp/filtered-context"
        
        # Mock successful subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        try:
            upload_build_context("test-namespace", "test-pod")
        except SystemExit:
            self.fail("upload_build_context should not exit on success")
        
        # Should use filtered directory
        args = mock_subprocess.call_args[0][0]
        self.assertIn("kubectl cp /tmp/filtered-context", args)
        mock_rmtree.assert_called_with("/tmp/filtered-context", ignore_errors=True)
    
    @patch('subprocess.run')
    @patch('shutil.rmtree')
    @patch.object(docker_build_cli, 'create_filtered_build_context')
    @patch.object(docker_build_cli, 'load_dockerignore')
    def test_upload_build_context_with_dockerignore_failure(self, mock_load_dockerignore,
                                                            mock_create_filtered, mock_rmtree,
                                                            mock_subprocess):
        """Test upload build context failure with cleanup."""
        # Mock .dockerignore exists
        mock_spec = MagicMock()
        mock_load_dockerignore.return_value = mock_spec
        mock_create_filtered.return_value = "/tmp/filtered-context"
        
        # Mock subprocess failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Upload failed"
        mock_subprocess.return_value = mock_result
        
        with self.assertRaises(SystemExit) as context:
            upload_build_context("test-namespace", "test-pod")
        
        self.assertEqual(context.exception.code, 1)
        # Should clean up temp directory on failure
        mock_rmtree.assert_called_with("/tmp/filtered-context", ignore_errors=True)

    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.exists')
    def test_dockerignore_patterns(self, mock_exists, mock_read_text):
        """Test various .dockerignore patterns work correctly."""
        mock_exists.return_value = True
        mock_read_text.return_value = """
# Comments should be ignored
node_modules/
*.log
*.tmp
!important.log
.git/
build/
dist/
        """.strip()
        
        spec = load_dockerignore()
        self.assertIsNotNone(spec)
        
        # Test patterns
        with patch('pathlib.Path.cwd', return_value=Path("/project")):
            # These should be ignored
            self.assertTrue(should_ignore_path(spec, "/project/node_modules/package.json"))
            self.assertTrue(should_ignore_path(spec, "/project/app.log"))
            self.assertTrue(should_ignore_path(spec, "/project/temp.tmp"))
            self.assertTrue(should_ignore_path(spec, "/project/.git/config"))
            self.assertTrue(should_ignore_path(spec, "/project/build/output.js"))
            
            # These should not be ignored
            self.assertFalse(should_ignore_path(spec, "/project/Dockerfile"))
            self.assertFalse(should_ignore_path(spec, "/project/src/main.py"))


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)