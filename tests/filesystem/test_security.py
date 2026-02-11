"""
Tests for the filesystem security module.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from radbot.filesystem.security import (
    create_parent_directory,
    get_allowed_directories,
    set_allowed_directories,
    validate_path,
)


class FilesystemSecurityTest(unittest.TestCase):
    """Test the filesystem security module."""

    def setUp(self):
        """Set up the test environment with temporary directories."""
        # Create temporary test directories
        self.temp_dir = tempfile.mkdtemp(prefix="fs_security_test_")
        self.allowed_dir1 = os.path.join(self.temp_dir, "allowed1")
        self.allowed_dir2 = os.path.join(self.temp_dir, "allowed2")
        self.forbidden_dir = os.path.join(self.temp_dir, "forbidden")

        # Create the directories
        os.makedirs(self.allowed_dir1)
        os.makedirs(self.allowed_dir2)
        os.makedirs(self.forbidden_dir)

        # Configure allowed directories
        set_allowed_directories([self.allowed_dir1, self.allowed_dir2])

    def tearDown(self):
        """Clean up the test environment."""
        # Remove the temporary directories
        shutil.rmtree(self.temp_dir)

        # Reset allowed directories
        set_allowed_directories([])

    def test_get_allowed_directories(self):
        """Test getting allowed directories."""
        allowed_dirs = get_allowed_directories()
        self.assertEqual(len(allowed_dirs), 2)
        self.assertIn(self.allowed_dir1, allowed_dirs)
        self.assertIn(self.allowed_dir2, allowed_dirs)

    def test_validate_path_allowed(self):
        """Test validating allowed paths."""
        # Test paths in allowed directories
        test_path1 = os.path.join(self.allowed_dir1, "test.txt")
        test_path2 = os.path.join(self.allowed_dir2, "test.txt")

        # Validation should succeed
        validated_path1 = validate_path(test_path1)
        validated_path2 = validate_path(test_path2)

        self.assertEqual(
            os.path.normpath(validated_path1), os.path.normpath(test_path1)
        )
        self.assertEqual(
            os.path.normpath(validated_path2), os.path.normpath(test_path2)
        )

    def test_validate_path_forbidden(self):
        """Test validating forbidden paths."""
        # Test path in forbidden directory
        test_path = os.path.join(self.forbidden_dir, "test.txt")

        # Validation should fail
        with self.assertRaises(PermissionError):
            validate_path(test_path)

    def test_validate_path_must_exist(self):
        """Test validating paths with must_exist=True."""
        # Test non-existent path
        test_path = os.path.join(self.allowed_dir1, "nonexistent.txt")

        # Validation should fail with must_exist=True
        with self.assertRaises(FileNotFoundError):
            validate_path(test_path, must_exist=True)

        # Validation should succeed with must_exist=False
        validated_path = validate_path(test_path, must_exist=False)
        self.assertEqual(os.path.normpath(validated_path), os.path.normpath(test_path))

    def test_validate_path_symlink(self):
        """Test validating symlink paths."""
        # Create a file in allowed directory
        allowed_file = os.path.join(self.allowed_dir1, "file.txt")
        with open(allowed_file, "w") as f:
            f.write("test")

        # Create a symlink in forbidden directory pointing to allowed directory
        symlink_path = os.path.join(self.forbidden_dir, "symlink_to_allowed")
        try:
            os.symlink(allowed_file, symlink_path)
        except OSError:
            # Skip on platforms where symlinks are not supported
            self.skipTest("Symlinks not supported")

        # Validation should PASS because realpath resolves to the allowed directory
        validated = validate_path(symlink_path)
        self.assertEqual(validated, os.path.realpath(symlink_path))

        # Create a symlink in allowed directory pointing to forbidden directory
        symlink_path = os.path.join(self.allowed_dir1, "symlink_to_forbidden")
        forbidden_file = os.path.join(self.forbidden_dir, "forbidden.txt")
        with open(forbidden_file, "w") as f:
            f.write("test")

        try:
            os.symlink(forbidden_file, symlink_path)
        except OSError:
            # Skip on platforms where symlinks are not supported
            self.skipTest("Symlinks not supported")

        # Validation should fail because the symlink targets a forbidden directory
        with self.assertRaises(PermissionError):
            validate_path(symlink_path)

    def test_create_parent_directory(self):
        """Test creating parent directory."""
        # Test creating parent directory
        test_path = os.path.join(self.allowed_dir1, "subdir", "test.txt")

        # Parent directory should not exist yet
        self.assertFalse(os.path.exists(os.path.dirname(test_path)))

        # Create parent directory
        create_parent_directory(test_path)

        # Parent directory should exist now
        self.assertTrue(os.path.exists(os.path.dirname(test_path)))

        # Test with forbidden path
        test_path = os.path.join(self.forbidden_dir, "subdir", "test.txt")

        # Creating parent directory should fail
        with self.assertRaises(PermissionError):
            create_parent_directory(test_path)


if __name__ == "__main__":
    unittest.main()
