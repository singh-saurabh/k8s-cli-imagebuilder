#!/usr/bin/env python3
"""
Test runner script for Docker Build CLI tests.
Runs both unittest and pytest test suites.
"""

import sys
import subprocess
import os

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=False)
        print(f"✅ {description} passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False

def main():
    """Run all tests."""
    print("Docker Build CLI Test Suite")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not os.path.exists('docker-build-cli.py'):
        print("❌ Error: docker-build-cli.py not found. Run this script from the project root.")
        sys.exit(1)
    
    # Install test dependencies
    print("Installing test dependencies...")
    install_result = run_command(
        "pip install pytest pytest-mock", 
        "dependency installation"
    )
    
    if not install_result:
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    test_results = []
    
    # Run unittest suite
    test_results.append(run_command(
        "python -m unittest test.test_docker_build_cli -v",
        "Unit Tests"
    ))
    
    # Run security tests
    test_results.append(run_command(
        "python -m unittest test.test_security -v",
        "Security Tests"
    ))
    
    # Run pytest for additional test discovery
    test_results.append(run_command(
        "python -m pytest test/ -v",
        "Pytest Suite"
    ))
    
    # Run specific test categories
    test_results.append(run_command(
        "python -m pytest test/test_docker_build_cli.py::TestDockerfileValidation -v",
        "Dockerfile Validation Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_docker_build_cli.py::TestYAMLTemplateLoading -v", 
        "YAML Template Loading Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_docker_build_cli.py::TestKubectlOperations -v",
        "kubectl Operations Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_docker_build_cli.py::TestKubernetesMocking -v",
        "Kubernetes Mock Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_docker_build_cli.py::TestPodDeletionWaiting -v",
        "Pod Deletion Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_security.py::TestSecurityValidation -v",
        "Security Validation Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_security.py::TestCredentialSecurity -v",
        "Credential Security Tests"
    ))
    
    # Run dockerignore tests
    test_results.append(run_command(
        "python -m unittest test.test_dockerignore -v",
        "Dockerignore Unit Tests"
    ))
    
    test_results.append(run_command(
        "python -m pytest test/test_dockerignore.py::TestDockerignoreFunctionality -v",
        "Dockerignore Functionality Tests"
    ))
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(test_results)
    total = len(test_results)
    
    if passed == total:
        print(f"✅ All {total} test suites passed!")
        sys.exit(0)
    else:
        print(f"❌ {total - passed} of {total} test suites failed")
        sys.exit(1)

if __name__ == '__main__':
    main()