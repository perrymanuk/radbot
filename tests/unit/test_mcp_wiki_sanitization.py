"""Path-traversal and sanitization tests for mcp_server wiki tools."""

from __future__ import annotations

import os
import tempfile

import pytest

from radbot.mcp_server.tools import wiki


@pytest.fixture
def wiki_root(monkeypatch):
    """Create a temp wiki root + symlinked 'outside' dir for traversal tests."""
    with (
        tempfile.TemporaryDirectory() as root,
        tempfile.TemporaryDirectory() as outside,
    ):
        # Populate root
        os.makedirs(os.path.join(root, "wiki", "concepts"), exist_ok=True)
        with open(os.path.join(root, "wiki", "concepts", "thing.md"), "w") as f:
            f.write("# thing\n\nHello.\n")

        # Create a symlink inside root pointing outside
        os.symlink(outside, os.path.join(root, "symlink-out"))

        # Create a file outside root
        with open(os.path.join(outside, "secret.md"), "w") as f:
            f.write("TOP SECRET")

        monkeypatch.setenv("RADBOT_WIKI_PATH", root)
        yield root


class TestResolveUnderRoot:
    def test_resolves_relative_path_inside_root(self, wiki_root):
        abs_path, err = wiki._resolve_under_root("wiki/concepts/thing.md")
        assert err == ""
        assert abs_path is not None
        assert abs_path.startswith(wiki_root)

    def test_rejects_absolute_path(self, wiki_root):
        abs_path, err = wiki._resolve_under_root("/etc/passwd")
        assert abs_path is None
        assert "Absolute paths not allowed" in err

    def test_rejects_parent_traversal(self, wiki_root):
        abs_path, err = wiki._resolve_under_root("../../../../etc/passwd")
        assert abs_path is None
        assert "escapes wiki root" in err

    def test_rejects_symlink_leading_outside(self, wiki_root):
        # `symlink-out/secret.md` resolves via the symlink to `outside/secret.md`
        abs_path, err = wiki._resolve_under_root("symlink-out/secret.md")
        assert abs_path is None
        assert "escapes wiki root" in err

    def test_returns_error_when_root_unconfigured(self, monkeypatch):
        monkeypatch.setenv("RADBOT_WIKI_PATH", "/nonexistent-path-xyz")
        abs_path, err = wiki._resolve_under_root("foo.md")
        assert abs_path is None
        assert "Wiki not configured" in err


class TestWikiRead:
    def test_reads_file(self, wiki_root):
        result = wiki._do_read("wiki/concepts/thing.md")
        assert "Hello." in result.text

    def test_error_on_traversal(self, wiki_root):
        result = wiki._do_read("../../../etc/passwd")
        assert "**Error:**" in result.text

    def test_error_on_missing(self, wiki_root):
        result = wiki._do_read("wiki/does-not-exist.md")
        assert "**Error:**" in result.text


class TestWikiWrite:
    def test_writes_and_creates_dirs(self, wiki_root):
        result = wiki._do_write("wiki/new/nested/file.md", "fresh content\n")
        assert "Wrote" in result.text
        full = os.path.join(wiki_root, "wiki/new/nested/file.md")
        assert os.path.isfile(full)
        with open(full) as f:
            assert f.read() == "fresh content\n"

    def test_rejects_write_outside_root_via_traversal(self, wiki_root):
        result = wiki._do_write("../../../tmp/hijack.md", "nope")
        assert "**Error:**" in result.text

    def test_rejects_write_through_symlink(self, wiki_root):
        result = wiki._do_write("symlink-out/injected.md", "nope")
        assert "**Error:**" in result.text
