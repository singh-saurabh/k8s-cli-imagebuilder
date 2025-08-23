# Contributing to Docker Build CLI

Thank you for your interest in contributing to the Docker Build CLI tool! This document provides guidelines for contributing to the project.

## Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/your-username/k8s-cli-imagebuilder.git
   cd k8s-cli-imagebuilder
   ```

2. **Create Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-mock flake8
   ```

## Code Standards

- **Python Version**: Python 3.7+
- **Code Style**: Follow flake8 standards
- **Line Length**: Maximum 127 characters
- **Testing**: All new features must include tests

## Testing

Run the comprehensive test suite before submitting:

```bash
# Run all tests
python run_tests.py

# Run specific test categories
python -m pytest test/test_docker_build_cli.py -v
python -m pytest test/test_security.py -v

# Check code style
flake8 docker-build-cli.py --max-line-length=127 --max-complexity=15
```

## Submitting Changes

1. **Create a Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write clean, well-documented code
   - Add tests for new functionality
   - Update README if needed

3. **Test Your Changes**
   ```bash
   python run_tests.py
   flake8 docker-build-cli.py --max-line-length=127
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a pull request on GitHub.

## Areas for Contribution

- **Security Enhancements**: Additional validation and security checks
- **Platform Support**: Windows compatibility improvements
- **Error Handling**: Better error messages and recovery
- **Performance**: Optimization for large build contexts
- **Documentation**: Examples, tutorials, and guides
- **Testing**: Additional test cases and edge case coverage

## Security

- Never commit secrets or credentials
- Follow secure coding practices
- Report security vulnerabilities privately via GitHub Security Advisories

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Be respectful and constructive in discussions

Thank you for contributing!