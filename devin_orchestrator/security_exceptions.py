"""Security-related exceptions shared across devin-orchestrator modules."""


class SecurityError(Exception):
    """Base exception for security-related errors"""

    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal is detected"""

    pass


class InvalidInputError(SecurityError):
    """Raised when input validation fails"""

    pass


class PermissionError(SecurityError):
    """Raised when file permission checks fail"""

    pass
