"""Tests for the shell command execution tool."""

import unittest
from unittest.mock import MagicMock, patch

from radbot.tools.shell.shell_command import ALLOWED_COMMANDS, execute_shell_command
from radbot.tools.shell.shell_tool import get_shell_tool, handle_shell_function_call


class TestShellCommand(unittest.TestCase):
    """Test cases for the shell command execution feature."""

    @patch("radbot.tools.shell.shell_command.subprocess.run")
    def test_execute_allowed_command_strict_mode(self, mock_run):
        """Test execution of an allowed command in strict mode."""
        # Setup
        mock_result = MagicMock()
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Use a command that's in the ALLOWED_COMMANDS set
        allowed_cmd = next(iter(ALLOWED_COMMANDS))

        # Execute
        result = execute_shell_command(
            command=allowed_cmd, arguments=["-l"], timeout=30, strict_mode=True
        )

        # Assert
        self.assertEqual(result["stdout"], "test output")
        self.assertEqual(result["stderr"], "")
        self.assertEqual(result["return_code"], 0)
        self.assertIsNone(result["error"])

        # Verify subprocess was called correctly
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], [allowed_cmd, "-l"])
        self.assertTrue(kwargs["shell"] is False)
        self.assertTrue(kwargs["capture_output"] is True)
        self.assertTrue(kwargs["text"] is True)
        self.assertEqual(kwargs["timeout"], 30)

    @patch("radbot.tools.shell.shell_command.subprocess.run")
    def test_disallowed_command_strict_mode(self, mock_run):
        """Test rejection of a disallowed command in strict mode."""
        # Setup a command that's definitely not in the allow-list
        disallowed_cmd = "rm"
        if disallowed_cmd in ALLOWED_COMMANDS:
            disallowed_cmd = "definitely_not_allowed_command"

        # Execute
        result = execute_shell_command(
            command=disallowed_cmd, arguments=["-rf", "/"], strict_mode=True
        )

        # Assert
        self.assertEqual(result["stdout"], "")
        self.assertIn("not allowed", result["stderr"])
        self.assertEqual(result["return_code"], -1)
        self.assertIsNotNone(result["error"])

        # Verify subprocess was NOT called
        mock_run.assert_not_called()

    @patch("radbot.tools.shell.shell_command.subprocess.run")
    def test_disallowed_command_allow_all_mode(self, mock_run):
        """Test execution of a disallowed command in allow all mode."""
        # Setup
        mock_result = MagicMock()
        mock_result.stdout = "non-allowed command output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Use a command definitely not in the allow-list
        disallowed_cmd = "rm"
        if disallowed_cmd in ALLOWED_COMMANDS:
            disallowed_cmd = "definitely_not_allowed_command"

        # Execute with strict_mode=False
        result = execute_shell_command(
            command=disallowed_cmd, arguments=["-rf", "/tmp/test"], strict_mode=False
        )

        # Assert command was executed despite not being in the allow-list
        self.assertEqual(result["stdout"], "non-allowed command output")
        self.assertEqual(result["stderr"], "")
        self.assertEqual(result["return_code"], 0)
        self.assertIsNone(result["error"])

        # Verify subprocess was called
        mock_run.assert_called_once()

    def test_unsafe_arguments_rejected(self):
        """Test that unsafe arguments are rejected."""
        # Test with a semicolon (command injection attempt)
        result = execute_shell_command(
            command="echo", arguments=["hello; rm -rf /"], strict_mode=True
        )

        self.assertEqual(result["return_code"], -1)
        self.assertIn("unsafe", result["stderr"])

        # Test with high-risk shell metacharacters
        for dangerous_char in ["|", "&", "$", "`"]:
            result = execute_shell_command(
                command="echo",
                arguments=[f"test{dangerous_char}injection"],
                strict_mode=True,
            )

            self.assertEqual(result["return_code"], -1)
            self.assertIn("unsafe", result["stderr"])

    def test_get_shell_tool(self):
        """Test the tool registration function."""
        # Test in strict mode
        strict_tool = get_shell_tool(strict_mode=True)
        self.assertIsNotNone(strict_tool)
        # FunctionTool wraps a function with __name__ and __doc__
        self.assertEqual(strict_tool.func.__name__, "execute_shell_command")
        self.assertIn("allow-listed", strict_tool.func.__doc__)

        # Test in allow all mode
        allow_all_tool = get_shell_tool(strict_mode=False)
        self.assertIsNotNone(allow_all_tool)
        self.assertIn("WARNING", allow_all_tool.func.__doc__)
        self.assertIn("SECURITY RISK", allow_all_tool.func.__doc__)

    @patch("radbot.tools.shell.shell_tool.execute_shell_command")
    async def test_handle_shell_function_call(self, mock_execute):
        """Test the function call handler."""
        # Setup
        mock_execute.return_value = {
            "stdout": "handled output",
            "stderr": "",
            "return_code": 0,
            "error": None,
        }

        # Test with valid arguments
        result = await handle_shell_function_call(
            function_name="execute_shell_command",
            arguments={"command": "echo", "arguments": ["hello"], "timeout": 30},
            strict_mode=True,
        )

        self.assertEqual(result["stdout"], "handled output")
        mock_execute.assert_called_once_with(
            command="echo", arguments=["hello"], timeout=30, strict_mode=True
        )


if __name__ == "__main__":
    unittest.main()
