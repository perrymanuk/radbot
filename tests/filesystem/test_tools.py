"""
Tests for the filesystem tools module.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from radbot.filesystem.security import set_allowed_directories
from radbot.filesystem.tools import (
    copy,
    delete,
    edit_file,
    get_info,
    list_directory,
    read_file,
    search,
    write_file,
)


class FilesystemToolsTest(unittest.TestCase):
    """Test the filesystem tools module."""

    def setUp(self):
        """Set up the test environment with temporary directories."""
        # Create temporary test directories
        self.temp_dir = tempfile.mkdtemp(prefix="fs_tools_test_")

        # Create test directories
        self.test_dir = os.path.join(self.temp_dir, "test_dir")
        self.subdir = os.path.join(self.test_dir, "subdir")
        os.makedirs(self.test_dir)
        os.makedirs(self.subdir)

        # Create test files
        self.test_file1 = os.path.join(self.test_dir, "test1.txt")
        self.test_file2 = os.path.join(self.test_dir, "test2.txt")
        self.subdir_file = os.path.join(self.subdir, "subfile.txt")

        with open(self.test_file1, "w") as f:
            f.write("Test file 1 content")

        with open(self.test_file2, "w") as f:
            f.write("Test file 2 content")

        with open(self.subdir_file, "w") as f:
            f.write("Subdir file content")

        # Configure allowed directories
        set_allowed_directories([self.temp_dir])

    def tearDown(self):
        """Clean up the test environment."""
        # Remove the temporary directories
        shutil.rmtree(self.temp_dir)

        # Reset allowed directories
        set_allowed_directories([])

    def test_read_file(self):
        """Test reading a file."""
        # Read test file
        content = read_file(self.test_file1)
        self.assertEqual(content, "Test file 1 content")

        # Test reading non-existent file
        with self.assertRaises(FileNotFoundError):
            read_file(os.path.join(self.test_dir, "nonexistent.txt"))

        # Test reading a directory
        with self.assertRaises(ValueError):
            read_file(self.test_dir)

    def test_write_file(self):
        """Test writing a file."""
        # Write new file
        new_file = os.path.join(self.test_dir, "new.txt")
        result = write_file(new_file, "New file content")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["size"], len("New file content"))

        # Verify file was written
        with open(new_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "New file content")

        # Test overwriting existing file without overwrite flag
        with self.assertRaises(FileExistsError):
            write_file(self.test_file1, "New content")

        # Test overwriting with overwrite flag
        result = write_file(self.test_file1, "Overwritten content", overwrite=True)
        self.assertEqual(result["status"], "success")

        # Verify file was overwritten
        with open(self.test_file1, "r") as f:
            content = f.read()
        self.assertEqual(content, "Overwritten content")

        # Test writing to a new subdirectory
        new_subdir_file = os.path.join(self.test_dir, "newdir", "newfile.txt")
        result = write_file(new_subdir_file, "New subdir file content")

        self.assertEqual(result["status"], "success")

        # Verify directory and file were created
        self.assertTrue(os.path.exists(os.path.dirname(new_subdir_file)))
        self.assertTrue(os.path.exists(new_subdir_file))

    def test_edit_file(self):
        """Test editing a file."""
        # Create test file with multiline content
        multiline_file = os.path.join(self.test_dir, "multiline.txt")
        with open(multiline_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\n")

        # Test simple edit
        edits = [{"oldText": "Line 2", "newText": "Modified Line 2"}]
        diff = edit_file(multiline_file, edits)

        # Verify diff is not empty
        self.assertTrue(len(diff) > 0)

        # Verify file was modified
        with open(multiline_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Line 1\nModified Line 2\nLine 3\nLine 4\n")

        # Test multiple edits
        edits = [
            {"oldText": "Line 1", "newText": "Modified Line 1"},
            {"oldText": "Line 3", "newText": "Modified Line 3"},
        ]
        diff = edit_file(multiline_file, edits)

        # Verify diff is not empty
        self.assertTrue(len(diff) > 0)

        # Verify file was modified
        with open(multiline_file, "r") as f:
            content = f.read()
        self.assertEqual(
            content, "Modified Line 1\nModified Line 2\nModified Line 3\nLine 4\n"
        )

        # Test editing non-existent file
        with self.assertRaises(FileNotFoundError):
            edit_file(os.path.join(self.test_dir, "nonexistent.txt"), edits)

        # Test editing a directory
        with self.assertRaises(ValueError):
            edit_file(self.test_dir, edits)

        # Test dry run
        edits = [{"oldText": "Line 4", "newText": "Modified Line 4"}]
        diff = edit_file(multiline_file, edits, dry_run=True)

        # Verify diff is not empty
        self.assertTrue(len(diff) > 0)

        # Verify file was not modified
        with open(multiline_file, "r") as f:
            content = f.read()
        self.assertEqual(
            content, "Modified Line 1\nModified Line 2\nModified Line 3\nLine 4\n"
        )

        # Test edit with text not found
        edits = [{"oldText": "Non-existent text", "newText": "New text"}]
        with self.assertRaises(ValueError):
            edit_file(multiline_file, edits)

    def test_copy(self):
        """Test copying a file or directory."""
        # Test copying a file
        dest_file = os.path.join(self.test_dir, "copy_of_test1.txt")
        result = copy(self.test_file1, dest_file)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], "file")

        # Verify file was copied
        self.assertTrue(os.path.exists(dest_file))
        with open(dest_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Test file 1 content")

        # Test copying to existing destination
        with self.assertRaises(FileExistsError):
            copy(self.test_file1, dest_file)

        # Test copying a directory
        dest_dir = os.path.join(self.test_dir, "copy_of_subdir")
        result = copy(self.subdir, dest_dir)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], "directory")

        # Verify directory was copied
        self.assertTrue(os.path.exists(dest_dir))
        self.assertTrue(os.path.exists(os.path.join(dest_dir, "subfile.txt")))

        # Test copying non-existent file
        with self.assertRaises(FileNotFoundError):
            copy(os.path.join(self.test_dir, "nonexistent.txt"), dest_file)

    def test_delete(self):
        """Test deleting a file or directory."""
        # Test deleting a file
        result = delete(self.test_file1)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], "file")

        # Verify file was deleted
        self.assertFalse(os.path.exists(self.test_file1))

        # Test deleting a directory
        result = delete(self.subdir)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], "directory")

        # Verify directory was deleted
        self.assertFalse(os.path.exists(self.subdir))

        # Test deleting non-existent file
        with self.assertRaises(FileNotFoundError):
            delete(os.path.join(self.test_dir, "nonexistent.txt"))

    def test_list_directory(self):
        """Test listing directory contents."""
        # Test listing directory
        contents = list_directory(self.test_dir)

        # Should have 3 items: test1.txt, test2.txt, subdir
        self.assertEqual(len(contents), 3)

        # Verify all items are present
        names = [item["name"] for item in contents]
        self.assertIn("test1.txt", names)
        self.assertIn("test2.txt", names)
        self.assertIn("subdir", names)

        # Verify types are correct
        for item in contents:
            if item["name"] == "subdir":
                self.assertEqual(item["type"], "[DIR]")
            else:
                self.assertEqual(item["type"], "[FILE]")

        # Test listing non-existent directory
        with self.assertRaises(FileNotFoundError):
            list_directory(os.path.join(self.test_dir, "nonexistent"))

        # Test listing a file
        with self.assertRaises(ValueError):
            list_directory(self.test_file1)

    def test_get_info(self):
        """Test getting file or directory information."""
        # Test getting file info
        info = get_info(self.test_file1)

        self.assertEqual(info["name"], "test1.txt")
        self.assertEqual(info["type"], "file")
        self.assertEqual(info["size"], len("Test file 1 content"))

        # Test getting directory info
        info = get_info(self.test_dir)

        self.assertEqual(info["name"], "test_dir")
        self.assertEqual(info["type"], "directory")

        # Test getting info for non-existent file
        with self.assertRaises(FileNotFoundError):
            get_info(os.path.join(self.test_dir, "nonexistent.txt"))

    def test_search(self):
        """Test searching for files or directories."""
        # Create additional test files
        os.makedirs(os.path.join(self.test_dir, "searchdir"))
        with open(os.path.join(self.test_dir, "searchdir", "found1.txt"), "w") as f:
            f.write("Found 1")
        with open(os.path.join(self.test_dir, "searchdir", "found2.txt"), "w") as f:
            f.write("Found 2")
        with open(os.path.join(self.test_dir, "searchdir", "notfound.log"), "w") as f:
            f.write("Not found")

        # Test searching for *.txt files
        results = search(self.test_dir, "*.txt")

        # Should find test1.txt, test2.txt, subdir/subfile.txt, searchdir/found1.txt, searchdir/found2.txt
        self.assertEqual(len(results), 5)

        # Verify all items are found
        names = [os.path.basename(item["path"]) for item in results]
        self.assertIn("test1.txt", names)
        self.assertIn("test2.txt", names)
        self.assertIn("subfile.txt", names)
        self.assertIn("found1.txt", names)
        self.assertIn("found2.txt", names)

        # Test with exclude pattern
        results = search(self.test_dir, "*.txt", exclude_patterns=["found*"])

        # Should find test1.txt, test2.txt, subdir/subfile.txt
        self.assertEqual(len(results), 3)

        # Verify excluded items are not found
        names = [os.path.basename(item["path"]) for item in results]
        self.assertIn("test1.txt", names)
        self.assertIn("test2.txt", names)
        self.assertIn("subfile.txt", names)
        self.assertNotIn("found1.txt", names)
        self.assertNotIn("found2.txt", names)

        # Test searching non-existent directory
        with self.assertRaises(FileNotFoundError):
            search(os.path.join(self.test_dir, "nonexistent"), "*.txt")

        # Test searching a file
        with self.assertRaises(ValueError):
            search(self.test_file1, "*.txt")


if __name__ == "__main__":
    unittest.main()
