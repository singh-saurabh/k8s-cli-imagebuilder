#!/usr/bin/env python3
import os
import sys
import click
import yaml
import json
import time
import re
import base64
from dotenv import load_dotenv
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Load environment variables from .env file
load_dotenv()

def validate_image_name(image_name):
    """Validate Docker image name format."""
    if not image_name or not isinstance(image_name, str):
        raise ValueError("Image name must be a non-empty string")
    
    # Check length limit
    if len(image_name) > 255:
        raise ValueError(f"Image name too long (max 255 chars): {len(image_name)}")
    
    # Check for dangerous characters and patterns
    dangerous_chars = [';', '&', '|', '`', '$', '\n', '\r', '\t', '\x00', ' ', '@']
    for char in dangerous_chars:
        if char in image_name:
            raise ValueError(f"Invalid character in image name: {char!r}")
    
    # Check for path traversal
    if '..' in image_name or image_name.startswith('/') or '\\' in image_name:
        raise ValueError(f"Invalid Docker image name format: {image_name}")
    
    # Check for invalid patterns
    if image_name.startswith('-') or image_name.endswith('-'):
        raise ValueError(f"Invalid Docker image name format: {image_name}")
    
    # Split image name and tag to validate separately
    if ':' in image_name:
        image_part, tag_part = image_name.rsplit(':', 1)
    else:
        image_part, tag_part = image_name, None
    
    # Check for uppercase in image part (Docker image names should be lowercase)
    if image_part != image_part.lower():
        raise ValueError(f"Docker image names must be lowercase: {image_name}")
    
    # Docker image name pattern: [registry[:port]/]namespace/repository[:tag]
    # Image part must be lowercase, tag can have uppercase
    image_pattern = r'^([a-z0-9][a-z0-9._-]*(?:\.[a-z0-9][a-z0-9._-]*)*(?::[0-9]+)?/)?[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$'
    if not re.match(image_pattern, image_part):
        raise ValueError(f"Invalid Docker image name format: {image_name}")
    
    # Validate tag if present
    if tag_part:
        tag_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$'
        if not re.match(tag_pattern, tag_part):
            raise ValueError(f"Invalid Docker tag format: {tag_part}")

def build_and_push(image_name, dockerhub_username, dockerhub_token, context_path):
    """Build Docker image using BuildKit in Kubernetes and push to DockerHub."""
    
    # Validate image name format
    try:
        validate_image_name(image_name)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    
    # Validate required credentials
    if not dockerhub_username:
        click.echo("❌ DockerHub username required. Use --dockerhub-username or set DOCKERHUB_USERNAME env var")
        sys.exit(1)
    
    if not dockerhub_token:
        click.echo("❌ DockerHub token required. Use --dockerhub-token or set DOCKERHUB_TOKEN env var")
        sys.exit(1)
    
    # Check if Dockerfile exists
    dockerfile_path = os.path.join(context_path, 'Dockerfile')
    if not os.path.exists(dockerfile_path):
        click.echo(f"❌ No Dockerfile found in {context_path}")
        sys.exit(1)
    
    click.echo(f"✅ Found Dockerfile in {context_path}")
    
    # Load kubernetes config
    try:
        config.load_kube_config()
        click.echo("✅ Kubernetes config loaded")
    except Exception as e:
        click.echo(f"❌ Failed to load kubernetes config: {e}")
        sys.exit(1)
    
    # Create kubernetes clients
    v1 = client.CoreV1Api()
    batch_v1 = client.BatchV1Api()
    
    # Create namespace if it doesn't exist
    namespace = "docker-builds"
    try:
        v1.create_namespace(client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace)))
        click.echo(f"✅ Created namespace {namespace}")
    except ApiException as e:
        if e.status == 409:  # Already exists
            click.echo(f"✅ Using existing namespace {namespace}")
        else:
            click.echo(f"❌ Failed to create namespace: {e}")
            sys.exit(1)
    
    # Create DockerHub secret
    secret_name = "dockerhub-secret"
    try:
        dockerconfig = {
            "auths": {
                "https://index.docker.io/v1/": {
                    "username": dockerhub_username,
                    "password": dockerhub_token
                }
            }
        }
        
        # Properly encode credentials as base64
        dockerconfig_json = json.dumps(dockerconfig)
        dockerconfig_b64 = base64.b64encode(dockerconfig_json.encode('utf-8')).decode('utf-8')
        
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            data={
                ".dockerconfigjson": dockerconfig_b64
            }
        )
        
        try:
            v1.delete_namespaced_secret(secret_name, namespace)
        except ApiException:
            pass  # Secret doesn't exist, that's fine
            
        v1.create_namespaced_secret(namespace, secret)
        click.echo(f"✅ Created DockerHub secret")
    except Exception as e:
        click.echo(f"❌ Failed to create secret: {e}")
        sys.exit(1)
    
    # Create ConfigMap with build context
    configmap_name = "build-context"
    try:
        # Read all files in context path
        files = {}
        skipped_files = []
        max_file_size = 1024 * 1024  # 1MB limit for individual files
        
        for root, dirs, filenames in os.walk(context_path):
            # Skip hidden directories and common build/cache directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
            
            for filename in filenames:
                if filename.startswith('.') or filename.endswith(('.pyc', '.pyo')):
                    continue
                    
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, context_path)
                
                # Check file size
                if os.path.getsize(file_path) > max_file_size:
                    skipped_files.append(f"{rel_path} (too large: {os.path.getsize(file_path)} bytes)")
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        files[rel_path] = f.read()
                except UnicodeDecodeError:
                    # Handle binary files by base64 encoding them
                    try:
                        with open(file_path, 'rb') as f:
                            binary_content = f.read()
                            files[f"{rel_path}.b64"] = base64.b64encode(binary_content).decode('utf-8')
                    except Exception as e:
                        skipped_files.append(f"{rel_path} (read error: {str(e)})")
                except Exception as e:
                    skipped_files.append(f"{rel_path} (error: {str(e)})")
        
        if skipped_files:
            click.echo(f"⚠️  Skipped {len(skipped_files)} files: {', '.join(skipped_files[:5])}{'...' if len(skipped_files) > 5 else ''}")
        
        configmap = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=configmap_name, namespace=namespace),
            data=files
        )
        
        try:
            v1.delete_namespaced_config_map(configmap_name, namespace)
        except ApiException:
            pass  # ConfigMap doesn't exist, that's fine
            
        v1.create_namespaced_config_map(namespace, configmap)
        click.echo(f"✅ Created build context ConfigMap")
    except Exception as e:
        click.echo(f"❌ Failed to create ConfigMap: {e}")
        sys.exit(1)
    
    # Create BuildKit build job
    job_name = f"build-{image_name.replace('/', '-').replace(':', '-').lower()}"
    try:
        job = client.V1Job(
            metadata=client.V1ObjectMeta(name=job_name, namespace=namespace),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="buildkit",
                                image="moby/buildkit:latest",
                                command=["/usr/bin/buildctl-daemonless.sh"],
                                args=[
                                    "build",
                                    "--frontend=dockerfile.v0",
                                    "--local", "context=/workspace",
                                    "--local", "dockerfile=/workspace",
                                    f"--output", f"type=image,name={image_name},push=true"
                                ],
                                env=[
                                    client.V1EnvVar(
                                        name="BUILDKITD_FLAGS",
                                        value="--oci-worker-no-process-sandbox"
                                    )
                                ],
                                security_context=client.V1SecurityContext(
                                    run_as_non_root=True,
                                    run_as_user=1000,
                                    capabilities=client.V1Capabilities(
                                        add=["SETUID", "SETGID"]
                                    )
                                ),
                                resources=client.V1ResourceRequirements(
                                    requests={"memory": "512Mi", "cpu": "500m"},
                                    limits={"memory": "2Gi", "cpu": "2"}
                                ),
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="build-context",
                                        mount_path="/workspace"
                                    ),
                                    client.V1VolumeMount(
                                        name="docker-config",
                                        mount_path="/root/.docker"
                                    )
                                ]
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="build-context",
                                config_map=client.V1ConfigMapVolumeSource(
                                    name=configmap_name
                                )
                            ),
                            client.V1Volume(
                                name="docker-config",
                                secret=client.V1SecretVolumeSource(
                                    secret_name=secret_name,
                                    items=[
                                        client.V1KeyToPath(
                                            key=".dockerconfigjson",
                                            path="config.json"
                                        )
                                    ]
                                )
                            )
                        ],
                        restart_policy="Never"
                    )
                ),
                backoff_limit=0
            )
        )
        
        try:
            batch_v1.delete_namespaced_job(job_name, namespace)
            time.sleep(2)  # Wait for deletion
        except ApiException:
            pass  # Job doesn't exist, that's fine
        
        batch_v1.create_namespaced_job(namespace, job)
        click.echo(f"✅ Created BuildKit build job: {job_name}")
    except Exception as e:
        click.echo(f"❌ Failed to create job: {e}")
        sys.exit(1)
    
    # Clean up function for resources
    def cleanup_resources():
        """Clean up secrets and other sensitive resources."""
        try:
            v1.delete_namespaced_secret(secret_name, namespace)
            click.echo("🗑️  Cleaned up DockerHub secret")
        except ApiException:
            pass  # Secret already deleted or doesn't exist
    
    # Monitor job status
    click.echo("🔄 Monitoring build progress...")
    
    timeout = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            job_status = batch_v1.read_namespaced_job_status(job_name, namespace)
            
            if job_status.status.succeeded:
                click.echo(f"✅ Build completed successfully! Image {image_name} pushed to DockerHub")
                cleanup_resources()
                break
            elif job_status.status.failed:
                click.echo("❌ Build failed!")
                # Get pod logs for debugging
                pods = v1.list_namespaced_pod(namespace, label_selector=f"job-name={job_name}")
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    try:
                        logs = v1.read_namespaced_pod_log(pod_name, namespace)
                        # Sanitize logs to remove potential sensitive information
                        sanitized_logs = logs.replace(dockerhub_token, "***TOKEN***") if dockerhub_token in logs else logs
                        click.echo("Build logs:")
                        click.echo(sanitized_logs)
                    except Exception as e:
                        click.echo(f"Failed to get logs: {e}")
                cleanup_resources()
                sys.exit(1)
            else:
                click.echo("⏳ Build in progress...")
                time.sleep(10)
                
        except Exception as e:
            click.echo(f"❌ Error monitoring job: {e}")
            cleanup_resources()
            sys.exit(1)
    
    if time.time() - start_time >= timeout:
        click.echo("❌ Build timed out!")
        cleanup_resources()
        sys.exit(1)

@click.command()
@click.option('--image-name', required=True, help='Docker image name (e.g., username/repo:tag)')
@click.option('--dockerhub-username', default=lambda: os.getenv('DOCKERHUB_USERNAME'), help='DockerHub username (or set DOCKERHUB_USERNAME env var)')
@click.option('--dockerhub-token', default=lambda: os.getenv('DOCKERHUB_TOKEN'), help='DockerHub access token (or set DOCKERHUB_TOKEN env var)')
@click.option('--context-path', default='.', help='Build context path (default: current directory)')
def main(image_name, dockerhub_username, dockerhub_token, context_path):
    """Main CLI entry point."""
    build_and_push(image_name, dockerhub_username, dockerhub_token, context_path)

if __name__ == '__main__':
    main()