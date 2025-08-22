# Docker Build CLI

A command-line tool that builds Docker images using BuildKit in a Kubernetes/Minikube cluster and pushes them to DockerHub.

## Features

- 🐳 Checks for Dockerfile presence in project root
- ⚙️ Submits build jobs to Kubernetes cluster using BuildKit
- 🚀 Automatically pushes built images to DockerHub
- 📊 Real-time build monitoring with progress updates
- 🔄 Handles build context via Kubernetes ConfigMaps

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
- `--context-path`: Build context path (default: current directory)

## How It Works

1. **Validation**: Checks for Dockerfile in the current directory (or specified context path)
2. **Security Check**: Validates image name format and prevents injection attacks
3. **Kubernetes Setup**: Creates namespace and required secrets/configmaps
4. **Build Context**: Uploads project files to Kubernetes ConfigMap
5. **Build Job**: Creates a Kubernetes Job using `moby/buildkit:latest`
6. **Monitoring**: Tracks build progress and displays logs on failure
7. **Push**: BuildKit automatically pushes successful builds to DockerHub
8. **Cleanup**: Automatically removes secrets and resources after completion

## Workflow Example

```bash
# Go to your project directory
cd /Users/myuser/projects/my-web-app

# Ensure Dockerfile exists
ls Dockerfile

# Run the build tool
docker-build-cli.py --image-name myuser/webapp:v1.0

# The tool will:
# ✅ Found Dockerfile in .
# ✅ Kubernetes config loaded  
# ✅ Created namespace docker-builds
# ✅ Created DockerHub secret
# ✅ Created build context ConfigMap
# ✅ Created BuildKit build job
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
   ❌ No Dockerfile found in .
   ```
   - Ensure you're in the project root directory
   - Use `--context-path` to specify a different directory

3. **Build Timeout**
   ```
   ❌ Build timed out!
   ```
   - Large projects may exceed the 10-minute timeout
   - Check cluster resources and build complexity

4. **Permission Denied**
   - Ensure your Kubernetes user has permissions to create namespaces, jobs, secrets, and configmaps

### Getting Build Logs

If a build fails, the tool automatically displays the pod logs to help with debugging.

## Development

### Project Structure

```
cli-tool/
├── docker-build-cli.py    # Main CLI application
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

- `click`: Command-line interface framework
- `kubernetes`: Kubernetes Python client
- `pyyaml`: YAML processing
- `python-dotenv`: Environment variable loading
- `pytest`: Testing framework
- `pytest-mock`: Mock testing support

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
