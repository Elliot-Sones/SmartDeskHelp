"""
Test Configuration - Shared fixtures for indexing tests.

Uses pytest fixtures to create isolated test environments.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from indexing.config import IndexerConfig, set_config


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp(prefix="indexer_test_")
    # Resolve to handle macOS /var -> /private/var symlink
    resolved = Path(tmp).resolve()
    yield resolved
    shutil.rmtree(str(resolved), ignore_errors=True)


@pytest.fixture
def test_config(temp_dir: Path) -> IndexerConfig:
    """Create an isolated test configuration."""
    config = IndexerConfig(
        roots=[temp_dir],
        index_path=temp_dir / "test.index",
        db_path=temp_dir / "test.db",
        scanner_concurrency=5,
        hasher_concurrency=3,
        embedder_batch_size=4,
        db_batch_size=10,
    )
    set_config(config)
    return config


@pytest.fixture
def sample_files(temp_dir: Path) -> dict[str, Path]:
    """Create sample files for testing."""
    files = {}
    
    # Text file
    txt = temp_dir / "sample.txt"
    txt.write_text("This is a sample text file.\nIt has multiple lines.\nFor testing purposes.")
    files["txt"] = txt
    
    # Markdown file
    md = temp_dir / "readme.md"
    md.write_text("# Test Readme\n\nThis is a markdown file for testing.\n\n## Section 1\n\nSome content here.")
    files["md"] = md
    
    # Python file
    py = temp_dir / "script.py"
    py.write_text('"""A sample Python script."""\n\ndef hello():\n    print("Hello, world!")\n\nif __name__ == "__main__":\n    hello()')
    files["py"] = py
    
    # Nested file
    nested_dir = temp_dir / "subdir" / "nested"
    nested_dir.mkdir(parents=True)
    nested = nested_dir / "deep.txt"
    nested.write_text("A deeply nested file.")
    files["nested"] = nested
    
    # Hidden file (should be skipped)
    hidden = temp_dir / ".hidden"
    hidden.write_text("This should be skipped.")
    files["hidden"] = hidden
    
    # Node modules dir (should be skipped)
    node_modules = temp_dir / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.json").write_text('{"name": "test"}')
    files["node_modules"] = node_modules / "package.json"
    
    return files


@pytest.fixture
def icloud_placeholder(temp_dir: Path) -> Path:
    """Create an iCloud placeholder file."""
    # iCloud placeholders are named like: .filename.ext.icloud
    placeholder = temp_dir / ".document.pdf.icloud"
    placeholder.write_bytes(b"placeholder")  # Binary content
    return placeholder


@pytest.fixture
def duplicate_files(temp_dir: Path) -> tuple[Path, Path]:
    """Create two files with identical content."""
    content = "This content is duplicated in two files.\n"
    
    file1 = temp_dir / "original.txt"
    file1.write_text(content)
    
    file2 = temp_dir / "copy.txt"
    file2.write_text(content)
    
    return file1, file2
