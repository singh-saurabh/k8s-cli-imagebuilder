#!/usr/bin/env python3
import os
import sys
import argparse
import yaml
import json
import time
import base64
import subprocess
import tempfile
import shutil
from pathlib import Path
from dotenv import load_dotenv
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import pathspec

# Load environment variables from .env file
load_dotenv()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Build Docker images using BuildKit in a Kubernetes/Minikube cluster and push them to DockerHub.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --image-name myuser/myapp:latest --dockerhub-username myuser --dockerhub-token mytoken
  %(prog)s --image-name myuser/myapp:latest  # Uses env vars DOCKERHUB_USERNAME and DOCKERHUB_TOKEN
        """)

    # Required argument
    parser.add_argument(
        '--image-name',
        required=True,
        help='Docker image name with tag (e.g., username/repo:tag)')

    # Optional arguments with environment variable fallback
    parser.add_argument(
        '--dockerhub-username',
        default=os.getenv('DOCKERHUB_USERNAME'),
        help='DockerHub username (or set DOCKERHUB_USERNAME env var)')

    parser.add_argument(
        '--dockerhub-token',
        default=os.getenv('DOCKERHUB_TOKEN'),
        help='DockerHub access token (or set DOCKERHUB_TOKEN env var)')

    # Parse arguments
    args = parser.parse_args()

    # Validate required credentials
    if not args.dockerhub_username:
        print(
            "❌ DockerHub username required. Use --dockerhub-username or set DOCKERHUB_USERNAME env var",
            file=sys.stderr)
        sys.exit(1)

    if not args.dockerhub_token:
        print(
            "❌ DockerHub token required. Use --dockerhub-token or set DOCKERHUB_TOKEN env var",
            file=sys.stderr)
        sys.exit(1)

    # Call the main build function (to be implemented)
    build_and_push(
        args.image_name,
        args.dockerhub_username,
        args.dockerhub_token)


def validate_dockerfile():
    """Check if Dockerfile exists in current directory."""
    dockerfile_path = os.path.join(".", "Dockerfile")
    if not os.path.exists(dockerfile_path):
        print("❌ No Dockerfile found in current directory")
        sys.exit(1)
    print("✅ Found Dockerfile in current directory")


def load_dockerignore():
    """Load .dockerignore patterns using pathspec."""
    dockerignore_path = Path(".dockerignore")

    if not dockerignore_path.exists():
        print("ℹ️  No .dockerignore found, copying all files")
        return None

    try:
        lines = dockerignore_path.read_text().splitlines()
        spec = pathspec.PathSpec.from_lines('gitwildmatch', lines)
        print(f"✅ Loaded .dockerignore with {len(lines)} patterns")
        return spec
    except Exception as e:
        print(f"⚠️  Failed to parse .dockerignore: {e}")
        print("ℹ️  Copying all files")
        return None


def should_ignore_path(spec, file_path):
    """Check if a file path should be ignored based on .dockerignore."""
    if spec is None:
        return False

    # Convert to relative path and normalize
    rel_path = Path(file_path).relative_to(Path.cwd())
    return spec.match_file(str(rel_path))


def create_filtered_build_context(spec):
    """Create a temporary directory with filtered files based on .dockerignore."""
    temp_dir = tempfile.mkdtemp(prefix='docker-build-context-')
    print(f"📁 Creating filtered build context in {temp_dir}")

    copied_files = 0
    ignored_files = 0

    try:
        # Walk through all files in current directory
        for root, dirs, files in os.walk('.'):
            # Convert root to relative path
            root_path = Path(root).relative_to('.')

            # Check if directory should be ignored
            if root != '.' and should_ignore_path(spec, root):
                ignored_files += len(files)
                dirs.clear()  # Don't recurse into ignored directories
                continue

            # Create corresponding directory in temp location
            dest_root = Path(temp_dir) / root_path
            dest_root.mkdir(parents=True, exist_ok=True)

            # Copy files that aren't ignored
            for file in files:
                src_file = Path(root) / file

                if should_ignore_path(spec, src_file):
                    ignored_files += 1
                    continue

                dest_file = dest_root / file
                try:
                    shutil.copy2(src_file, dest_file)
                    copied_files += 1
                except Exception as e:
                    print(f"⚠️  Failed to copy {src_file}: {e}")

        print(f"✅ Copied {copied_files} files, ignored {ignored_files} files")
        return temp_dir

    except Exception as e:
        print(f"❌ Failed to create filtered build context: {e}")
        # Clean up on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)


def load_kubernetes_config():
    """Load Kubernetes configuration."""
    try:
        config.load_kube_config()
        print("✅ Kubernetes config loaded")
        return client.CoreV1Api()
    except Exception as e:
        print(f"❌ Failed to load Kubernetes config: {e}")
        sys.exit(1)


def create_namespace(v1, namespace):
    """Create namespace if it doesn't exist."""
    try:
        v1.create_namespace(
            client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace)))
        print(f"✅ Created namespace {namespace}")
    except ApiException as e:
        if e.status == 409:  # Already exists
            print(f"✅ Using existing namespace {namespace}")
        else:
            print(f"❌ Failed to create namespace: {e}")
            sys.exit(1)


def create_dockerhub_secret(v1, namespace, secret_name, username, token):
    """Create DockerHub secret for authentication."""
    try:
        dockerconfig = {
            "auths": {
                "https://index.docker.io/v1/": {
                    "username": username,
                    "password": token
                }
            }
        }

        dockerconfig_json = json.dumps(dockerconfig)
        dockerconfig_b64 = base64.b64encode(
            dockerconfig_json.encode('utf-8')).decode('utf-8')

        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=secret_name,
                namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            data={
                ".dockerconfigjson": dockerconfig_b64})

        # Delete existing secret if it exists
        try:
            v1.delete_namespaced_secret(secret_name, namespace)
        except ApiException:
            pass

        v1.create_namespaced_secret(namespace, secret)
        print("✅ Created DockerHub secret")
    except Exception as e:
        print(f"❌ Failed to create secret: {e}")
        sys.exit(1)


def run_kubectl_command(command):
    """Run a kubectl command and return the result."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ kubectl command failed: {command}")
        print(f"❌ Error: {e.stderr.strip()}")
        sys.exit(1)


def wait_for_pod_ready(v1, namespace, pod_name, timeout=120):
    """Wait for pod to be in Running state."""
    print("🔄 Waiting for pod to be ready...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)
            if pod.status.phase == "Running":
                print("✅ Pod is ready")
                return True
            elif pod.status.phase == "Failed":
                print("❌ Pod failed to start")
                return False
            else:
                print(f"🔄 Pod status: {pod.status.phase}")
                time.sleep(2)
        except Exception as e:
            print(f"❌ Error checking pod status: {e}")
            time.sleep(2)

    print("❌ Timeout waiting for pod to be ready")
    return False


def upload_build_context(namespace, pod_name):
    """Upload build context using kubectl cp with .dockerignore filtering."""
    print("📁 Uploading build context...")

    # Load .dockerignore patterns
    dockerignore_spec = load_dockerignore()

    # Determine source directory
    if dockerignore_spec is None:
        # No .dockerignore, use current directory
        source_dir = "."
        temp_dir = None
    else:
        # Create filtered build context
        temp_dir = create_filtered_build_context(dockerignore_spec)
        source_dir = temp_dir

    # Copy source directory to pod
    kubectl_cp_cmd = f"kubectl cp {source_dir} -n {namespace} {pod_name}:/build-context"
    print(f"🔄 Running: {kubectl_cp_cmd}")

    try:
        result = subprocess.run(
            kubectl_cp_cmd,
            shell=True,
            capture_output=True,
            text=True)

        # Clean up temporary directory
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if result.returncode != 0:
            print(f"❌ Failed to upload build context: {result.stderr}")
            sys.exit(1)
        print("✅ Build context uploaded successfully")
    except Exception as e:
        # Clean up temporary directory on error
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"❌ Error uploading build context: {e}")
        sys.exit(1)


def trigger_build(namespace, pod_name):
    """Create BUILD_READY file to trigger the build process."""
    print("🚀 Triggering build process...")

    # Create a trigger file to signal build can start
    trigger_cmd = f"kubectl exec -n {namespace} {pod_name} -- touch /build-context/BUILD_READY"

    try:
        result = subprocess.run(
            trigger_cmd,
            shell=True,
            capture_output=True,
            text=True)
        if result.returncode != 0:
            print(f"❌ Failed to trigger build: {result.stderr}")
            sys.exit(1)
        print("✅ Build triggered successfully")
    except Exception as e:
        print(f"❌ Error triggering build: {e}")
        sys.exit(1)


def load_pod_yaml_template():
    """Load BuildKit pod YAML template from file."""
    try:
        # Get script directory to find YAML file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        yaml_path = os.path.join(script_dir, "buildkit-pod.yaml")

        with open(yaml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("❌ buildkit-pod.yaml template file not found")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to load YAML template: {e}")
        sys.exit(1)


def wait_for_pod_deletion(v1, namespace, pod_name, timeout=60):
    """Wait for pod to be completely deleted."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            v1.read_namespaced_pod(pod_name, namespace)
            # Pod still exists, keep waiting
            time.sleep(1)
        except ApiException as e:
            if e.status == 404:
                # Pod not found, deletion complete
                return True
            # Other error, keep waiting
            time.sleep(1)
        except Exception:
            # Other error, keep waiting
            time.sleep(1)

    return False


def create_buildkit_pod(v1, namespace, pod_name, image_name, secret_name):
    """Create BuildKit pod from YAML template."""
    try:
        # Delete existing pod if it exists and wait for deletion
        try:
            v1.read_namespaced_pod(pod_name, namespace)
            print(f"🗑️  Deleting existing pod: {pod_name}")
            v1.delete_namespaced_pod(pod_name, namespace)
            if not wait_for_pod_deletion(v1, namespace, pod_name):
                print("❌ Timeout waiting for pod deletion")
                sys.exit(1)
            print("✅ Pod deletion completed")
        except ApiException as e:
            if e.status != 404:
                # Pod doesn't exist, that's fine
                pass

        # Load and format the YAML template
        pod_yaml_template = load_pod_yaml_template()
        pod_yaml = pod_yaml_template.format(
            pod_name=pod_name,
            namespace=namespace,
            image_name=image_name,
            secret_name=secret_name
        )

        # Parse YAML and create pod
        pod_spec = yaml.safe_load(pod_yaml)
        v1.create_namespaced_pod(namespace, pod_spec)
        print(f"✅ Created BuildKit pod: {pod_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to create pod: {e}")
        sys.exit(1)


def monitor_pod(v1, namespace, pod_name, secret_name):
    """Monitor pod status and show logs."""
    print("🔄 Monitoring build progress...")

    timeout = 600  # 10 minutes
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            pod = v1.read_namespaced_pod(pod_name, namespace)

            if pod.status.phase == "Succeeded":
                print("✅ Build completed successfully!")
                cleanup_secret(v1, namespace, secret_name)
                break
            elif pod.status.phase == "Failed":
                print("❌ Build failed!")
                # Show pod logs
                try:
                    logs = v1.read_namespaced_pod_log(pod_name, namespace)
                    print("Build logs:")
                    print(logs)
                except Exception as e:
                    print(f"Failed to get logs: {e}")
                cleanup_secret(v1, namespace, secret_name)
                sys.exit(1)
            else:
                # Show running logs
                try:
                    logs = v1.read_namespaced_pod_log(pod_name, namespace)
                    if logs:
                        lines = logs.strip().split('\n')
                        for line in lines[-5:]:  # Show last 5 lines
                            if line.strip():
                                print(f"🔄 {line}")
                except Exception:
                    pass  # Pod might not be ready yet

                time.sleep(5)

        except Exception as e:
            print(f"❌ Error monitoring pod: {e}")
            cleanup_secret(v1, namespace, secret_name)
            sys.exit(1)

    if time.time() - start_time >= timeout:
        print("❌ Build timed out!")
        cleanup_secret(v1, namespace, secret_name)
        sys.exit(1)


def cleanup_secret(v1, namespace, secret_name):
    """Clean up DockerHub secret."""
    try:
        v1.delete_namespaced_secret(secret_name, namespace)
        print("🗑️  Cleaned up DockerHub secret")
    except ApiException:
        pass


def build_and_push(image_name, dockerhub_username, dockerhub_token):
    """Build Docker image using BuildKit in Kubernetes and push to DockerHub."""
    validate_dockerfile()

    # Load Kubernetes config
    v1 = load_kubernetes_config()

    # Setup resources
    namespace = "docker-builds"
    secret_name = "dockerhub-secret"
    pod_name = f"build-{image_name.replace('/', '-').replace(':', '-').lower()}"

    # Create Kubernetes resources
    create_namespace(v1, namespace)
    create_dockerhub_secret(
        v1,
        namespace,
        secret_name,
        dockerhub_username,
        dockerhub_token)
    create_buildkit_pod(v1, namespace, pod_name, image_name, secret_name)

    # Wait for pod to be ready
    if not wait_for_pod_ready(v1, namespace, pod_name):
        cleanup_secret(v1, namespace, secret_name)
        sys.exit(1)

    # Upload build context
    upload_build_context(namespace, pod_name)

    # Trigger the build
    trigger_build(namespace, pod_name)

    # Monitor the build
    monitor_pod(v1, namespace, pod_name, secret_name)


if __name__ == '__main__':
    main()
