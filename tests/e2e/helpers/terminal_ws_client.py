"""Binary WebSocket client for terminal PTY e2e tests.

Speaks the terminal binary protocol:
  0x01 = data (terminal I/O)
  0x02 = resize (uint16BE cols + uint16BE rows)
  0x03 = closed (int32BE exit code)
"""

import asyncio
import logging
import re
import struct
from typing import Optional

import websockets

logger = logging.getLogger(__name__)

# Binary protocol constants (must match radbot/web/api/terminal.py)
_MSG_DATA = 0x01
_MSG_RESIZE = 0x02
_MSG_CLOSED = 0x03

# Regex to strip ANSI escape sequences from PTY output
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"  # CSI sequences (colors, cursor, etc.)
    r"|\x1b\][^\x07]*\x07"  # OSC sequences
    r"|\x1b[()][012AB]"  # Character set selection
    r"|\x1b\[[\?0-9;]*[hlm]"  # Mode set/reset
    r"|\x1b[=>]"  # Keypad mode
    r"|\x1b\[\d*[ABCDJK]"  # Cursor movement / erase
    r"|\r"  # Carriage returns
)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from terminal output."""
    return _ANSI_RE.sub("", text)


class TerminalWSClient:
    """Binary WebSocket client for terminal PTY sessions."""

    def __init__(self, ws):
        self._ws = ws
        self._output_buffer = bytearray()
        self._closed = False
        self._exit_code: Optional[int] = None

    @classmethod
    async def connect(
        cls,
        base_url: str,
        terminal_id: str,
        timeout: float = 10.0,
        cols: int = 120,
        rows: int = 30,
    ) -> "TerminalWSClient":
        """Connect to ``/ws/terminal/{terminal_id}`` and send initial size."""
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws/terminal/{terminal_id}"

        ws = await asyncio.wait_for(
            websockets.connect(ws_url),
            timeout=timeout,
        )
        client = cls(ws)

        # Send initial terminal size
        await client.send_resize(cols, rows)

        return client

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def exit_code(self) -> Optional[int]:
        return self._exit_code

    def _process_frame(self, data: bytes) -> Optional[str]:
        """Process a single binary frame. Returns decoded text for DATA frames."""
        if not data:
            return None

        msg_type = data[0]
        payload = data[1:]

        if msg_type == _MSG_DATA:
            self._output_buffer.extend(payload)
            return payload.decode("utf-8", errors="replace")

        elif msg_type == _MSG_CLOSED:
            self._closed = True
            if len(payload) >= 4:
                self._exit_code = struct.unpack(">i", payload[:4])[0]
            else:
                self._exit_code = -1
            return None

        return None

    async def recv_output(self, timeout: float = 30.0) -> str:
        """Receive PTY output frames until timeout or close.

        Returns all accumulated output as decoded text.
        Stops early if a MSG_CLOSED frame is received.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        collected = []

        while not self._closed:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=min(remaining, 2.0))
                text = self._process_frame(raw)
                if text:
                    collected.append(text)
            except asyncio.TimeoutError:
                # No more data within the short poll window — if we have data, return it
                if collected:
                    break
            except websockets.exceptions.ConnectionClosed:
                self._closed = True
                break

        return "".join(collected)

    async def recv_until_text(self, pattern: str, timeout: float = 30.0) -> str:
        """Read PTY output until ANSI-stripped output contains *pattern*.

        Returns the full accumulated stripped output.
        Raises TimeoutError if the pattern isn't found within *timeout*.
        """
        deadline = asyncio.get_event_loop().time() + timeout

        while not self._closed:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Pattern {pattern!r} not found within {timeout}s. "
                    f"Output so far: {self.get_output()[:500]}"
                )
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
                self._process_frame(raw)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Pattern {pattern!r} not found within {timeout}s. "
                    f"Output so far: {self.get_output()[:500]}"
                )
            except websockets.exceptions.ConnectionClosed:
                self._closed = True
                break

            stripped = self.get_output()
            if pattern in stripped:
                return stripped

        raise TimeoutError(
            f"Connection closed before pattern {pattern!r} found. "
            f"Output: {self.get_output()[:500]}"
        )

    async def send_input(self, text: str) -> None:
        """Send keystrokes to the PTY (MSG_DATA prefix + UTF-8 bytes)."""
        payload = bytes([_MSG_DATA]) + text.encode("utf-8")
        await self._ws.send(payload)

    async def send_resize(self, cols: int, rows: int) -> None:
        """Send a resize message (MSG_RESIZE + uint16BE cols + uint16BE rows)."""
        payload = bytes([_MSG_RESIZE]) + struct.pack(">HH", cols, rows)
        await self._ws.send(payload)

    def get_output(self) -> str:
        """Return all accumulated output with ANSI sequences stripped."""
        raw = self._output_buffer.decode("utf-8", errors="replace")
        return _strip_ansi(raw)

    def get_raw_output(self) -> str:
        """Return all accumulated output without ANSI stripping."""
        return self._output_buffer.decode("utf-8", errors="replace")

    async def wait_for_close(self, timeout: float = 10.0) -> bool:
        """Wait for a MSG_CLOSED frame. Returns True if received."""
        deadline = asyncio.get_event_loop().time() + timeout

        while not self._closed:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return False
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
                self._process_frame(raw)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                return self._closed

        return True

    async def close(self) -> None:
        """Close the WebSocket connection."""
        try:
            await self._ws.close()
        except Exception:
            pass
