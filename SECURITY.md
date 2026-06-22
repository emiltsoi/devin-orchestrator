# Security Best Practices

This document outlines security best practices and security improvements implemented in devin-orchestrator.

## Overview

devin-orchestrator has been hardened with several security improvements to protect against common vulnerabilities including:

- Path traversal attacks
- Command injection
- Insecure file handling
- Hardcoded secrets and paths
- Insufficient input validation

## Security Improvements

### 1. Secrets Management

**Problem:** Hardcoded paths and credentials in source code.

**Solution:** 
- Removed hardcoded paths from `devin_simple.py` and other files
- Configuration loaded from `config.yaml` and environment variables
- Added `get_secret_from_env()` utility for secure secret retrieval

**Usage:**
```python
from security_utils import get_secret_from_env

# Load secrets from environment
api_key = get_secret_from_env("API_KEY")
devin_cli_path = get_secret_from_env("DEVIN_CLI_PATH", default="devin.exe")
```

**Environment Variables:**
- `DEVIN_ORCHESTRATOR_ROOT`: Global root directory
- `DEVIN_ORCHESTRATOR_SKILLS_DIR`: Skills directory path
- `DEVIN_ORCHESTRATOR_WORKFLOWS_DIR`: Workflows directory path
- `DEVIN_ORCHESTRATOR_WORKFLOW_ENGINE_DIR`: Workflow engine directory path
- `DEVIN_CLI_PATH`: Path to devin CLI executable
- `DEVIN_DEFAULT_MODEL`: Default model to use
- `DEVIN_DEFAULT_PERMISSION_MODE`: Default permission mode
- `DEVIN_SESSION_WORK_DIR`: Session work directory

### 2. Input Sanitization

**Problem:** User input not validated before use.

**Solution:**
- Added comprehensive input validation functions in `security_utils.py`
- Implemented sanitization for filenames, strings, session IDs, skill names, and workspace paths
- Validation applied in `dispatch_skill.py` and `orchestration_engine.py`

**Usage:**
```python
from security_utils import (
    sanitize_filename,
    sanitize_string,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
    InvalidInputError
)

# Validate session ID
session_id = validate_session_id("SESSION-001")

# Validate skill name
skill_name = validate_skill_name("brainstorming")

# Validate workspace path
workspace = validate_workspace_path("/path/to/workspace")

# Sanitize filename
safe_filename = sanitize_filename(user_input, max_length=255)

# Sanitize string
safe_string = sanitize_string(user_input, max_length=10000)
```

**Validation Rules:**
- **Session IDs:** Alphanumeric characters, hyphens, and underscores only (max 100 chars)
- **Skill Names:** Alphanumeric characters and hyphens only (max 100 chars)
- **Filenames:** No path separators, no parent directory references, no control characters
- **Strings:** No null bytes, configurable length limits, optional character whitelist

### 3. File Permission Checks

**Problem:** No verification of file/directory permissions before operations.

**Solution:**
- Added `check_file_permissions()` and `check_directory_permissions()` functions
- Permission checks integrated into `session_init()` in `deterministic_tools.py`
- Verifies read, write, and execute permissions before operations

**Usage:**
```python
from security_utils import check_file_permissions, check_directory_permissions

# Check file permissions
if check_file_permissions(file_path, required_read=True, required_write=True):
    # Safe to perform operations
    pass

# Check directory permissions
if check_directory_permissions(dir_path, required_write=True, required_execute=True):
    # Safe to create files/directories
    pass
```

**Permission Checks:**
- Verifies owner read permission (`S_IRUSR`)
- Verifies owner write permission (`S_IWUSR`)
- Verifies owner execute permission (`S_IXUSR`)
- Returns `False` if file/directory doesn't exist
- Gracefully handles permission check errors

### 4. Path Traversal Protection

**Problem:** No protection against path traversal attacks (e.g., `../../../etc/passwd`).

**Solution:**
- Added `validate_path_safe()` function to prevent path traversal
- Resolves paths to absolute form and validates they stay within allowed directories
- Integrated into `orchestration_engine.py` for manifest path validation

**Usage:**
```python
from security_utils import validate_path_safe, PathTraversalError

base_dir = Path("/safe/base/directory")
user_path = Path("../../../etc/passwd")

try:
    safe_path = validate_path_safe(base_dir, user_path)
except PathTraversalError as e:
    print(f"Path traversal detected: {e}")
```

**Protection Mechanisms:**
- Resolves all symbolic links and relative path components
- Validates that resolved path is within base directory
- Optional control over whether absolute paths are allowed
- Raises `PathTraversalError` if validation fails

### 5. Security Utilities Module

New `security_utils.py` module provides:

- **Path Validation:** `validate_path_safe()`, `validate_workspace_path()`
- **Input Sanitization:** `sanitize_filename()`, `sanitize_string()`
- **Permission Checks:** `check_file_permissions()`, `check_directory_permissions()`
- **Specific Validators:** `validate_session_id()`, `validate_skill_name()`
- **Secret Management:** `get_secret_from_env()`
- **Data Redaction:** `redact_sensitive_data()`

**Security Exceptions:**
- `SecurityError`: Base exception for security-related errors
- `PathTraversalError`: Raised when path traversal is detected
- `InvalidInputError`: Raised when input validation fails
- `PermissionError`: Raised when file permission checks fail

## Security Best Practices

### For Developers

1. **Always validate user input**
   ```python
   # Good
   session_id = validate_session_id(user_input)
   
   # Bad
   session_id = user_input
   ```

2. **Never hardcode paths or secrets**
   ```python
   # Good
   from config_loader import ConfigLoader
   config = ConfigLoader.load()
   path = config.devin_cli_path
   
   # Bad
   path = r"C:\Users\username\AppData\Local\devin\cli\bin\devin.exe"
   ```

3. **Use path validation for file operations**
   ```python
   # Good
   safe_path = validate_path_safe(base_dir, user_path)
   
   # Bad
   safe_path = base_dir / user_path
   ```

4. **Check permissions before file operations**
   ```python
   # Good
   if check_directory_permissions(dir_path, required_write=True):
       dir_path.mkdir()
   
   # Bad
   dir_path.mkdir()
   ```

5. **Sanitize filenames from user input**
   ```python
   # Good
   safe_filename = sanitize_filename(user_filename)
   
   # Bad
   safe_filename = user_filename
   ```

### For Operators

1. **Use environment variables for sensitive configuration**
   ```bash
   export DEVIN_CLI_PATH="/path/to/devin.exe"
   export DEVIN_ORCHESTRATOR_ROOT="/secure/path"
   ```

2. **Set appropriate file permissions**
   ```bash
   # Restrict config file to owner only
   chmod 600 ~/.devin-orchestrator/config.yaml
   
   # Ensure directories are not world-writable
   chmod 755 ~/.devin-orchestrator/
   ```

3. **Run with minimal required permissions**
   - Avoid running as root/administrator when possible
   - Use principle of least privilege for service accounts

4. **Keep dependencies updated**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

5. **Review and audit configuration files**
   - Ensure no sensitive data in config files
   - Use environment variables for secrets
   - Regularly rotate credentials

### For Security Audits

1. **Check for hardcoded paths**
   ```bash
   grep -r "C:\\Users" --include="*.py"
   grep -r "~/" --include="*.py"
   ```

2. **Verify input validation**
   - All user inputs should be validated
   - File paths should be validated against base directories
   - Filenames should be sanitized

3. **Review subprocess calls**
   - Ensure no command injection vulnerabilities
   - Use parameterized commands instead of string concatenation
   - Validate all arguments passed to subprocess

4. **Check file permissions**
   - Sensitive files should have restricted permissions
   - Directories should not be world-writable
   - Temporary files should be cleaned up

5. **Audit logging**
   - Security-relevant events should be logged
   - Logs should not contain sensitive data
   - Log files should have appropriate permissions

## Security Testing

### Test Path Traversal Protection
```python
from security_utils import validate_path_safe, PathTraversalError
from pathlib import Path

base = Path("/safe/dir")
malicious = Path("../../../etc/passwd")

try:
    validate_path_safe(base, malicious)
    print("FAIL: Path traversal not detected")
except PathTraversalError:
    print("PASS: Path traversal detected")
```

### Test Input Validation
```python
from security_utils import validate_session_id, InvalidInputError

# Test valid input
try:
    validate_session_id("SESSION-001")
    print("PASS: Valid session ID accepted")
except InvalidInputError:
    print("FAIL: Valid session ID rejected")

# Test invalid input
try:
    validate_session_id("../../../etc/passwd")
    print("FAIL: Invalid session ID accepted")
except InvalidInputError:
    print("PASS: Invalid session ID rejected")
```

### Test Permission Checks
```python
from security_utils import check_file_permissions
from pathlib import Path

# Test permission check
if check_file_permissions(Path("/etc/passwd"), required_read=True):
    print("PASS: Permission check working")
else:
    print("INFO: Permission check returned False (expected on some systems)")
```

## Incident Response

If a security issue is discovered:

1. **Immediately** assess the scope and impact
2. **Contain** the issue by disabling affected systems if necessary
3. **Document** the issue with timestamps and affected components
4. **Remediate** by applying patches or configuration changes
5. **Verify** the fix through testing
6. **Review** logs for indicators of compromise
7. **Report** through appropriate channels (security team, maintainers)

## Security Contact

For security-related questions or to report vulnerabilities:
- Review the project's security policy
- Contact the maintainers through official channels
- Do not open public issues for security vulnerabilities

## References

- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)