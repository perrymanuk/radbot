"""
Unit tests for Claude Code + GitHub integration tools.

Tests use mocked subprocess/httpx to avoid needing actual services.
"""

import asyncio
import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ────────────────────────────────────────────────────────────
# GitHub App Client tests
# ────────────────────────────────────────────────────────────


class TestGitHubAppClient:
    """Tests for GitHubAppClient."""

    @patch("radbot.tools.github.github_app_client._get_config")
    def test_get_github_client_unconfigured(self, mock_config):
        """Returns None when not configured."""
        mock_config.return_value = {
            "app_id": None,
            "installation_id": None,
            "private_key": None,
            "enabled": True,
        }
        from radbot.tools.github.github_app_client import (
            get_github_client,
            reset_github_client,
        )

        reset_github_client()
        client = get_github_client()
        assert client is None

    @patch("radbot.tools.github.github_app_client._get_config")
    def test_get_github_client_disabled(self, mock_config):
        """Returns None when disabled."""
        mock_config.return_value = {
            "app_id": "123",
            "installation_id": "456",
            "private_key": "key",
            "enabled": False,
        }
        from radbot.tools.github.github_app_client import (
            get_github_client,
            reset_github_client,
        )

        reset_github_client()
        client = get_github_client()
        assert client is None

    def test_generate_jwt(self):
        """JWT generation produces a valid token."""
        # Use a real RSA key for testing
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        from radbot.tools.github.github_app_client import GitHubAppClient

        client = GitHubAppClient("12345", "67890", pem)
        token = client._generate_jwt()

        import jwt as pyjwt

        # Decode without verification to check structure
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        assert decoded["iss"] == "12345"
        assert "exp" in decoded
        assert "iat" in decoded

    @patch("radbot.tools.github.github_app_client.httpx.get")
    def test_get_status_success(self, mock_get):
        """get_status returns app info on success."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"name": "test-app", "id": 12345}
        mock_get.return_value = mock_resp

        from radbot.tools.github.github_app_client import GitHubAppClient

        client = GitHubAppClient("12345", "67890", pem)
        status = client.get_status()
        assert status["status"] == "ok"
        assert status["app_name"] == "test-app"

    @patch("radbot.tools.github.github_app_client.subprocess.run")
    @patch("radbot.tools.github.github_app_client.httpx.post")
    def test_clone_repo_new(self, mock_post, mock_run):
        """clone_repo clones a new repo."""
        import tempfile

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        # Mock token fetch
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"token": "ghs_fake_token"}
        mock_post.return_value = mock_resp

        # Mock git clone
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from radbot.tools.github.github_app_client import GitHubAppClient

        client = GitHubAppClient("12345", "67890", pem)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = client.clone_repo("owner", "repo", tmpdir)
            assert result["status"] == "success"
            assert result["action"] == "clone"
            assert "local_path" in result


# ────────────────────────────────────────────────────────────
# Claude Code Client tests
# ────────────────────────────────────────────────────────────


class TestClaudeCodeClient:
    """Tests for ClaudeCodeClient."""

    def test_get_claude_code_status_no_cli(self):
        """Returns error when claude CLI not found."""
        with patch(
            "radbot.tools.claude_code.claude_code_client.shutil.which",
            return_value=None,
        ):
            from radbot.tools.claude_code.claude_code_client import (
                get_claude_code_status,
            )

            status = get_claude_code_status()
            assert status["status"] == "error"
            assert status["cli_available"] is False

    def test_get_claude_code_status_no_token(self):
        """Returns error when CLI exists but no token."""
        with (
            patch(
                "radbot.tools.claude_code.claude_code_client.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "radbot.tools.claude_code.claude_code_client._get_oauth_token",
                return_value=None,
            ),
        ):
            from radbot.tools.claude_code.claude_code_client import (
                get_claude_code_status,
            )

            status = get_claude_code_status()
            assert status["status"] == "error"
            assert status["cli_available"] is True
            assert status["token_configured"] is False

    def test_get_claude_code_status_ok(self):
        """Returns ok when CLI and token are available."""
        with (
            patch(
                "radbot.tools.claude_code.claude_code_client.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "radbot.tools.claude_code.claude_code_client._get_oauth_token",
                return_value="test-token",
            ),
        ):
            from radbot.tools.claude_code.claude_code_client import (
                get_claude_code_status,
            )

            status = get_claude_code_status()
            assert status["status"] == "ok"
            assert status["cli_available"] is True
            assert status["token_configured"] is True

    @pytest.mark.asyncio
    async def test_run_plan_cli_not_found(self):
        """run_plan returns error when CLI not on PATH."""
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient(oauth_token="test-token")

        with patch(
            "radbot.tools.claude_code.claude_code_client.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("claude not found"),
        ):
            result = await client.run_plan("/tmp", "test prompt")
            assert result["status"] == "error"
            assert "not found" in result["stderr"]

    @pytest.mark.asyncio
    async def test_run_plan_success(self):
        """run_plan parses stream-json output correctly."""
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient(oauth_token="test-token")

        # Simulate stream-json output
        stream_lines = [
            json.dumps(
                {
                    "type": "assistant",
                    "session_id": "sess-123",
                    "content": [{"type": "text", "text": "Here is the plan..."}],
                }
            )
            + "\n",
            json.dumps(
                {
                    "type": "result",
                    "session_id": "sess-123",
                    "result": "Plan complete.",
                }
            )
            + "\n",
        ]

        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[line.encode() for line in stream_lines] + [b""]
        )
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 0

        with patch(
            "radbot.tools.claude_code.claude_code_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await client.run_plan("/tmp", "Create a plan")
            assert result["status"] == "success"
            assert result["session_id"] == "sess-123"
            assert "plan" in result["output"].lower() or len(result["output"]) > 0

    @pytest.mark.asyncio
    async def test_run_execute_uses_skip_permissions(self):
        """run_execute includes --dangerously-skip-permissions in command."""
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient(oauth_token="test-token")

        captured_cmd = []

        async def mock_create_subprocess(*args, **kwargs):
            captured_cmd.extend(args)
            mock_proc = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(return_value=b"")
            mock_proc.stderr.read = AsyncMock(return_value=b"")
            mock_proc.wait = AsyncMock()
            mock_proc.returncode = 0
            return mock_proc

        with patch(
            "radbot.tools.claude_code.claude_code_client.asyncio.create_subprocess_exec",
            side_effect=mock_create_subprocess,
        ):
            await client.run_execute("/tmp", "Execute plan")
            assert "--dangerously-skip-permissions" in captured_cmd


# ────────────────────────────────────────────────────────────
# Tool wrapper tests
# ────────────────────────────────────────────────────────────


class TestClaudeCodeTools:
    """Tests for the FunctionTool wrappers."""

    @patch("radbot.tools.github.github_app_client.get_github_client")
    def test_clone_repository_no_client(self, mock_get_client):
        """clone_repository returns error when GitHub App not configured."""
        mock_get_client.return_value = None

        from radbot.tools.claude_code.claude_code_tools import clone_repository

        result = clone_repository("owner", "repo")
        assert result["status"] == "error"
        assert "not configured" in result["message"].lower()

    @patch("radbot.tools.github.github_app_client.get_github_client")
    def test_clone_repository_success(self, mock_get_client):
        """clone_repository returns success with work_folder."""
        mock_client = MagicMock()
        mock_client.clone_repo.return_value = {
            "status": "success",
            "local_path": "/app/workspaces/owner/repo",
            "action": "clone",
        }
        mock_get_client.return_value = mock_client

        from radbot.tools.claude_code.claude_code_tools import clone_repository

        with patch("radbot.tools.claude_code.db.create_workspace"):
            result = clone_repository("owner", "repo")
            assert result["status"] == "success"
            assert result["work_folder"] == "/app/workspaces/owner/repo"

    def test_list_workspaces_returns_dict(self):
        """list_workspaces returns proper format."""
        with patch(
            "radbot.tools.claude_code.db.list_active_workspaces",
            return_value=[
                {
                    "owner": "owner",
                    "repo": "repo",
                    "branch": "main",
                    "local_path": "/app/workspaces/owner/repo",
                    "last_session_id": "sess-123",
                    "last_used_at": "2026-02-23T12:00:00",
                }
            ],
        ):
            from radbot.tools.claude_code.claude_code_tools import list_workspaces

            result = list_workspaces()
            assert result["status"] == "success"
            assert result["count"] == 1
            assert result["workspaces"][0]["owner"] == "owner"

    @patch("radbot.tools.github.github_app_client.get_github_client")
    def test_commit_and_push_no_client(self, mock_get_client):
        """commit_and_push returns error when GitHub App not configured."""
        mock_get_client.return_value = None

        from radbot.tools.claude_code.claude_code_tools import commit_and_push

        result = commit_and_push("/tmp/repo", "test commit")
        assert result["status"] == "error"

    def test_claude_code_tools_list(self):
        """CLAUDE_CODE_TOOLS contains expected number of tools."""
        from radbot.tools.claude_code.claude_code_tools import CLAUDE_CODE_TOOLS

        assert len(CLAUDE_CODE_TOOLS) == 6
        names = [
            getattr(t, "name", "") or getattr(t, "__name__", "")
            for t in CLAUDE_CODE_TOOLS
        ]
        assert "clone_repository" in names
        assert "claude_code_plan" in names
        assert "claude_code_continue" in names
        assert "claude_code_execute" in names
        assert "commit_and_push" in names
        assert "list_workspaces" in names


# ────────────────────────────────────────────────────────────
# DB schema tests
# ────────────────────────────────────────────────────────────


class TestCoderDB:
    """Tests for coder_workspaces DB operations (mock DB)."""

    @patch("radbot.tools.shared.db_schema.get_db_connection")
    @patch("radbot.tools.shared.db_schema.get_db_cursor")
    def test_init_coder_schema(self, mock_cursor, mock_conn):
        """init_coder_schema calls init_table_schema without error."""
        # Mock the connection and cursor context managers
        mock_cursor_obj = MagicMock()
        mock_cursor_obj.fetchone.return_value = (True,)  # table already exists
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = MagicMock(return_value=mock_conn_ctx)
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value.__enter__ = MagicMock(
            return_value=mock_cursor_obj
        )
        mock_conn_ctx.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_ctx

        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor_obj)
        mock_cursor_ctx.__exit__ = MagicMock(return_value=False)
        mock_cursor.return_value = mock_cursor_ctx

        from radbot.tools.claude_code.db import init_coder_schema

        # Should not raise
        init_coder_schema()
