"""
Error Handling - Centralized error policies and custom exceptions.

This module defines how different error types should be handled throughout
the indexing pipeline, ensuring graceful degradation and proper logging.
"""

import logging
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class ErrorAction(Enum):
    """What to do when an error occurs."""
    SKIP = auto()           # Skip this item, continue processing
    RETRY = auto()          # Retry the operation (with backoff)
    ABORT = auto()          # Stop the entire pipeline
    MARK_PLACEHOLDER = auto()  # Index as placeholder (for cloud files)


@dataclass
class ErrorPolicy:
    """Policy for handling a specific error type."""
    action: ErrorAction
    log_level: int
    max_retries: int = 0
    message_template: str = "{file}: {error}"


# Error type to policy mapping
ERROR_POLICIES: dict[type, ErrorPolicy] = {
    PermissionError: ErrorPolicy(
        action=ErrorAction.SKIP,
        log_level=logging.WARNING,
        message_template="Permission denied: {file}"
    ),
    FileNotFoundError: ErrorPolicy(
        action=ErrorAction.SKIP,
        log_level=logging.DEBUG,
        message_template="File not found (possibly deleted): {file}"
    ),
    UnicodeDecodeError: ErrorPolicy(
        action=ErrorAction.SKIP,
        log_level=logging.DEBUG,
        message_template="Cannot decode file (binary?): {file}"
    ),
    IsADirectoryError: ErrorPolicy(
        action=ErrorAction.SKIP,
        log_level=logging.DEBUG,
        message_template="Expected file, got directory: {file}"
    ),
    OSError: ErrorPolicy(
        action=ErrorAction.SKIP,
        log_level=logging.WARNING,
        message_template="OS error reading file: {file} - {error}"
    ),
}


class IndexingError(Exception):
    """Base exception for indexing errors."""
    pass


class ICloudPlaceholderError(IndexingError):
    """File is an iCloud placeholder (not downloaded)."""
    def __init__(self, path: Path, real_name: str):
        self.path = path
        self.real_name = real_name
        super().__init__(f"iCloud placeholder: {real_name}")


class EmbeddingError(IndexingError):
    """Error during embedding generation."""
    pass


class DatabaseError(IndexingError):
    """Error during database operations."""
    pass


def handle_error(
    error: Exception,
    file_path: Optional[Path] = None,
    context: str = ""
) -> ErrorAction:
    """
    Handle an error according to the defined policies.
    
    Args:
        error: The exception that occurred
        file_path: Path to the file being processed (if applicable)
        context: Additional context for logging
    
    Returns:
        The action to take (SKIP, RETRY, etc.)
    """
    # Look up policy for this error type (or its base classes)
    policy = None
    for error_type, p in ERROR_POLICIES.items():
        if isinstance(error, error_type):
            policy = p
            break
    
    # Default policy for unknown errors
    if policy is None:
        policy = ErrorPolicy(
            action=ErrorAction.SKIP,
            log_level=logging.ERROR,
            message_template="Unexpected error: {file} - {error}"
        )
    
    # Format and log the message
    file_str = str(file_path) if file_path else "<unknown>"
    message = policy.message_template.format(file=file_str, error=str(error))
    if context:
        message = f"[{context}] {message}"
    
    logger.log(policy.log_level, message)
    
    return policy.action


@dataclass
class ProcessingResult:
    """Result of processing a single item."""
    success: bool
    path: Optional[Path] = None
    error: Optional[Exception] = None
    action_taken: Optional[ErrorAction] = None
    
    @classmethod
    def ok(cls, path: Path) -> "ProcessingResult":
        return cls(success=True, path=path)
    
    @classmethod
    def failed(cls, path: Path, error: Exception, action: ErrorAction) -> "ProcessingResult":
        return cls(success=False, path=path, error=error, action_taken=action)
