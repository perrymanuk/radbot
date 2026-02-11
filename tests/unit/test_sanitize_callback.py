"""Tests for the before-model sanitize callback."""

from unittest.mock import MagicMock, patch

from radbot.callbacks.sanitize_callback import sanitize_before_model_callback


def _make_part(text=None):
    """Create a mock Part with a .text attribute."""
    part = MagicMock()
    part.text = text
    return part


def _make_content(parts):
    """Create a mock Content with a .parts list."""
    content = MagicMock()
    content.parts = parts
    return content


def _make_request(contents):
    """Create a mock LlmRequest with .contents."""
    req = MagicMock()
    req.contents = contents
    return req


class TestSanitizeCallback:
    """Tests for sanitize_before_model_callback."""

    def test_returns_none(self):
        """Callback should always return None to allow request to proceed."""
        part = _make_part("hello")
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        result = sanitize_before_model_callback(ctx, request)
        assert result is None

    def test_strips_invisible_chars_in_place(self):
        """Invisible chars in part.text should be stripped in-place."""
        part = _make_part("a\u200bb\u200dc")
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert part.text == "abc"

    def test_clean_text_unchanged(self):
        """Clean text should not be modified."""
        part = _make_part("Hello, world!")
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert part.text == "Hello, world!"

    def test_multiple_parts(self):
        """All parts in all contents should be sanitized."""
        p1 = _make_part("a\u200bb")
        p2 = _make_part("c\u200dd")
        c1 = _make_content([p1])
        c2 = _make_content([p2])
        request = _make_request([c1, c2])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert p1.text == "ab"
        assert p2.text == "cd"

    def test_none_text_skipped(self):
        """Parts with None text should be skipped."""
        part = _make_part(None)
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert part.text is None

    def test_empty_text_skipped(self):
        """Parts with empty text should be skipped."""
        part = _make_part("")
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert part.text == ""

    def test_no_contents(self):
        """Request with no contents should not error."""
        request = _make_request(None)
        ctx = MagicMock()

        result = sanitize_before_model_callback(ctx, request)
        assert result is None

    def test_empty_parts(self):
        """Content with no parts should not error."""
        content = _make_content(None)
        request = _make_request([content])
        ctx = MagicMock()

        result = sanitize_before_model_callback(ctx, request)
        assert result is None

    def test_disabled_via_config(self):
        """When callback_enabled is False, text should not be modified."""
        with patch(
            "radbot.callbacks.sanitize_callback._get_sanitize_config"
        ) as mock_cfg:
            mock_cfg.return_value = {
                "enabled": True,
                "callback_enabled": False,
                "strictness": "standard",
                "log_detections": True,
            }
            part = _make_part("a\u200bb")
            content = _make_content([part])
            request = _make_request([content])
            ctx = MagicMock()

            sanitize_before_model_callback(ctx, request)
            assert part.text == "a\u200bb"

    def test_disabled_globally(self):
        """When enabled is False, text should not be modified."""
        with patch(
            "radbot.callbacks.sanitize_callback._get_sanitize_config"
        ) as mock_cfg:
            mock_cfg.return_value = {
                "enabled": False,
                "callback_enabled": True,
                "strictness": "standard",
                "log_detections": True,
            }
            part = _make_part("a\u200bb")
            content = _make_content([part])
            request = _make_request([content])
            ctx = MagicMock()

            sanitize_before_model_callback(ctx, request)
            assert part.text == "a\u200bb"

    def test_tag_char_attack_stripped(self):
        """Tag characters used for invisible smuggling should be stripped."""
        hidden = "".join(chr(0xE0000 + ord(c)) for c in "INJECT")
        part = _make_part("safe" + hidden + "text")
        content = _make_content([part])
        request = _make_request([content])
        ctx = MagicMock()

        sanitize_before_model_callback(ctx, request)
        assert part.text == "safetext"
