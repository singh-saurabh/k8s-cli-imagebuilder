# Docker Build CLI

[![Test Suite](https://github.com/singh-saurabh/k8s-cli-imagebuilder/actions/workflows/test.yml/badge.svg)](https://github.com/singh-saurabh/k8s-cli-imagebuilder/actions/workflows/test.yml)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Code Style](https://img.shields.io/badge/code%20style-flake8-blue.svg)](https://flake8.pycqa.org/)

A command-line tool that builds Docker images using BuildKit in a Kubernetes/Minikube cluster and pushes them to DockerHub.

## Features

- 🐳 Checks for Dockerfile presence in project root
- ⚙️ Submits build jobs to Kubernetes cluster using BuildKit
- 🚀 Automatically pushes built multiplatform images (linux/amd64, linux/arm64) to DockerHub
- 📊 Real-time build monitoring with progress updates
- 📁 Handles build context via kubectl cp (supports large files, no size limits)
- 🗑️ Automatic cleanup of sensitive resources after completion

## Prerequisites

- Python 3.7+
- Kubernetes cluster (Minikube recommended for local development)
- `kubectl` configured with cluster access
- DockerHub account with access token

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd cli-tool
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create environment file (optional):
```bash
cp .env.example .env
# Edit .env with your DockerHub credentials
```

5. Make the script globally accessible (optional):
```bash
# Make script executable
chmod +x docker-build-cli.py

# Add to your PATH (choose your shell)
echo 'export PATH="$PATH:'$(pwd)'"' >> ~/.bashrc   # For bash
echo 'export PATH="$PATH:'$(pwd)'"' >> ~/.zshrc    # For zsh

# Reload your shell configuration
source ~/.bashrc  # or source ~/.zshrc
```

## Usage

### From Installation Directory

```bash
python docker-build-cli.py --image-name username/myapp:latest --dockerhub-username myuser --dockerhub-token mytoken
```

### From Any Directory (if added to PATH)

Navigate to any project directory and run:
```bash
cd /path/to/my/project
docker-build-cli.py --image-name username/myapp:latest --dockerhub-username myuser --dockerhub-token mytoken
```

### Using Environment Variables

Set credentials once:
```bash
export DOCKERHUB_USERNAME=myuser
export DOCKERHUB_TOKEN=mytoken
```

Then run from any project directory:
```bash
cd /my/react/project
docker-build-cli.py --image-name myuser/react-app:latest

cd /my/python/project  
docker-build-cli.py --image-name myuser/python-app:v1.0
```

### Options

- `--image-name` (required): Docker image name with tag (e.g., `username/repo:tag`)
- `--dockerhub-username`: DockerHub username (or set `DOCKERHUB_USERNAME` env var)
- `--dockerhub-token`: DockerHub access token (or set `DOCKERHUB_TOKEN` env var)

## How It Works

1. **Validation**: Checks for Dockerfile in the current directory
2. **Kubernetes Setup**: Creates namespace and required secrets for DockerHub authentication
3. **Pod Creation**: Creates a BuildKit pod with emptyDir volume for build context
4. **Pod Management**: Automatically deletes and waits for cleanup of existing pods with the same name
5. **Build Context Upload**: Uses `kubectl cp` to upload entire project directory (supports large files, binaries, node_modules, etc.)
6. **Build Trigger**: Creates BUILD_READY signal file to start the build process
7. **Multiplatform Build**: BuildKit builds for both linux/amd64 and linux/arm64 architectures
8. **Push**: Automatically pushes successful multiplatform builds to DockerHub
9. **Monitoring**: Tracks build progress with real-time logs
10. **Cleanup**: Automatically removes sensitive DockerHub secrets after completion

## Workflow Example

```bash
# Go to your project directory
cd /Users/myuser/projects/my-web-app

# Ensure Dockerfile exists
ls Dockerfile

# Run the build tool
docker-build-cli.py --image-name myuser/webapp:v1.0

# The tool will:
# ✅ Found Dockerfile in current directory
# ✅ Kubernetes config loaded  
# ✅ Using existing namespace docker-builds
# ✅ Created DockerHub secret
# 🗑️  Deleting existing pod: build-myuser-webapp-v1-0
# ✅ Pod deletion completed
# ✅ Created BuildKit pod: build-myuser-webapp-v1-0
# 🔄 Waiting for pod to be ready...
# ✅ Pod is ready
# 📁 Uploading build context...
# ✅ Build context uploaded successfully
# 🚀 Triggering build process...
# ✅ Build triggered successfully
# 🔄 Monitoring build progress...
# ✅ Build completed successfully! Image myuser/webapp:v1.0 pushed to DockerHub
# 🗑️  Cleaned up DockerHub secret
```


## Troubleshooting

### Common Issues

1. **Kubernetes Config Not Found**
   ```
   ❌ Failed to load kubernetes config
   ```
   - Ensure `kubectl` is configured and can access your cluster
   - Run `kubectl cluster-info` to verify connection

2. **Dockerfile Not Found**
   ```
   ❌ No Dockerfile found in current directory
   ```
   - Ensure you're in the project root directory with a Dockerfile

3. **Pod Deletion Timeout**
   ```
   ❌ Timeout waiting for pod deletion
   ```
   - Previous build pod may be stuck in terminating state
   - Manually delete with: `kubectl delete pod -n docker-builds <pod-name> --force --grace-period=0`

4. **kubectl cp Failed**
   ```
   ❌ Failed to upload build context
   ```
   - Ensure `kubectl` has access to your cluster
   - Check if pod is running: `kubectl get pods -n docker-builds`
   - Verify kubectl version compatibility

5. **Build Context Too Large**
   - The tool handles large files automatically
   - For extremely large projects (>1GB), consider adding files to `.gitignore` to exclude from build context

6. **Permission Denied**
   - Ensure your Kubernetes user has permissions to create namespaces, pods, secrets
   - Required RBAC permissions: pods, secrets, namespaces (create, read, update, delete)

### Getting Build Logs

If a build fails, the tool automatically displays the pod logs to help with debugging.

## Development

### Project Structure

```
cli-tool/
├── docker-build-cli.py    # Main CLI application
├── buildkit-pod.yaml     # Kubernetes pod template for BuildKit
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── run_tests.py          # Test runner script
├── test/                 # Test directory
│   ├── __init__.py
│   ├── test_docker_build_cli.py  # Main functionality tests
│   └── test_security.py         # Security validation tests
└── README.md            # This file
```

### Dependencies

- `argparse`: Command-line interface (built-in)
- `kubernetes`: Kubernetes Python client
- `pyyaml`: YAML processing
- `python-dotenv`: Environment variable loading
- `pytest`: Testing framework
- `pytest-mock`: Mock testing support

### Key Features

- **Multiplatform Builds**: Automatically builds for both linux/amd64 and linux/arm64 architectures
- **kubectl cp Integration**: Handles large files, binaries, and complex project structures without size limits
- **Pod Management**: Intelligent pod lifecycle management with proper deletion and cleanup
- **Real-time Monitoring**: Live build progress tracking with detailed logs
- **Secure Credential Handling**: Automatic cleanup of DockerHub secrets after build completion

### Testing

Run the comprehensive test suite:

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
python run_tests.py

# Run specific test categories
python -m pytest test/test_docker_build_cli.py::TestImageNameValidation -v
python -m pytest test/test_security.py::TestSecurityValidation -v
```

Test coverage includes:
- Image name validation and security checks
- Kubernetes API interaction mocking
- Command injection prevention
- Path traversal attack prevention
- Credential validation and security

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Add your license information here]

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review Kubernetes cluster logs
3. Ensure all prerequisites are met
4. Open an issue in this repository
