#!/usr/bin/env python3
import os
import sys
import click
import yaml
import time
from dotenv import load_dotenv
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Load environment variables from .env file
load_dotenv()

@click.command()
@click.option('--image-name', required=True, help='Docker image name (e.g., username/repo:tag)')
@click.option('--dockerhub-username', default=lambda: os.getenv('DOCKERHUB_USERNAME'), help='DockerHub username (or set DOCKERHUB_USERNAME env var)')
@click.option('--dockerhub-token', default=lambda: os.getenv('DOCKERHUB_TOKEN'), help='DockerHub access token (or set DOCKERHUB_TOKEN env var)')
@click.option('--context-path', default='.', help='Build context path (default: current directory)')
def build_and_push(image_name, dockerhub_username, dockerhub_token, context_path):
    """Build Docker image using BuildKit in Kubernetes and push to DockerHub."""
    
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
        
        secret = client.V1Secret(
            metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
            type="kubernetes.io/dockerconfigjson",
            data={
                ".dockerconfigjson": str.encode(yaml.dump(dockerconfig)).decode('utf-8').encode('base64').decode('utf-8').replace('\n', '')
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
        for root, dirs, filenames in os.walk(context_path):
            for filename in filenames:
                if filename.startswith('.'):
                    continue
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, context_path)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        files[rel_path] = f.read()
                except UnicodeDecodeError:
                    # Skip binary files
                    continue
        
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
                                    privileged=True
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
    
    # Monitor job status
    click.echo("🔄 Monitoring build progress...")
    
    timeout = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            job_status = batch_v1.read_namespaced_job_status(job_name, namespace)
            
            if job_status.status.succeeded:
                click.echo(f"✅ Build completed successfully! Image {image_name} pushed to DockerHub")
                break
            elif job_status.status.failed:
                click.echo("❌ Build failed!")
                # Get pod logs for debugging
                pods = v1.list_namespaced_pod(namespace, label_selector=f"job-name={job_name}")
                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    try:
                        logs = v1.read_namespaced_pod_log(pod_name, namespace)
                        click.echo("Build logs:")
                        click.echo(logs)
                    except Exception as e:
                        click.echo(f"Failed to get logs: {e}")
                sys.exit(1)
            else:
                click.echo("⏳ Build in progress...")
                time.sleep(10)
                
        except Exception as e:
            click.echo(f"❌ Error monitoring job: {e}")
            sys.exit(1)
    
    if time.time() - start_time >= timeout:
        click.echo("❌ Build timed out!")
        sys.exit(1)

if __name__ == '__main__':
    build_and_push()