"""Guardrailed web_fetch FunctionTool for scout."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx
from google.adk.tools import FunctionTool

from radbot.tools.shared.sanitize import sanitize_external_content

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 256 * 1024
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_REDIRECTS = 3

# Hostname substrings that should never be fetched.
_DEFAULT_BLOCKLIST: Tuple[str, ...] = (
    "pastebin.com",
    "pastebin.pl",
    "paste.ee",
    "hastebin.com",
    "requestbin.com",
    "requestbin.net",
    "webhook.site",
    "ngrok.io",
    "ngrok.app",
    "ngrok-free.app",
    "beeceptor.com",
    "smee.io",
    "localtunnel.me",
    "serveo.net",
)

_USER_AGENT = "radbot-scout/1.0 (+https://github.com/perrymanuk/radbot)"

# Strip <script>/<style> blocks, then HTML tags, then collapse whitespace.
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NEWLINE_COLLAPSE_RE = re.compile(r"\n{3,}")


def _load_config() -> Dict[str, Any]:
    """Pull web_research config overrides from the DB-merged integration section.

    Falls back to defaults on any error — the tool is still usable without config.
    """
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("web_research", {})
        return cfg or {}
    except Exception as e:  # config subsystem is optional at import-time
        logger.debug("web_research config unavailable, using defaults: %s", e)
        return {}


def _extra_blocklist() -> Tuple[str, ...]:
    cfg = _load_config()
    extra = cfg.get("blocklist") or []
    return tuple(s.lower().strip() for s in extra if isinstance(s, str))


def _allowlist() -> Tuple[str, ...]:
    cfg = _load_config()
    allow = cfg.get("allowlist") or []
    return tuple(s.lower().strip() for s in allow if isinstance(s, str))


def _max_bytes() -> int:
    return int(_load_config().get("max_bytes", _DEFAULT_MAX_BYTES))


def _timeout_seconds() -> float:
    return float(_load_config().get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))


def _hostname(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    return (parsed.hostname or "").lower() or None


def _is_private_ip(host: str) -> bool:
    """True if ``host`` resolves to any loopback / private / link-local address.

    Resolves every A/AAAA record and rejects if *any* is private — prevents
    DNS rebinding-style partial allows. Unresolvable hosts return True (blocked)
    to fail closed rather than fetch into nothing.
    """
    try:
        # If host is already a literal IP, short-circuit
        try:
            addr = ipaddress.ip_address(host)
            return (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
                or addr.is_unspecified
            )
        except ValueError:
            pass

        infos = socket.getaddrinfo(host, None)
        for family, _type, _proto, _canon, sockaddr in infos:
            ip_str = sockaddr[0]
            # IPv6 addresses may include %scope; trim it
            if "%" in ip_str:
                ip_str = ip_str.split("%", 1)[0]
            addr = ipaddress.ip_address(ip_str)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
                or addr.is_unspecified
            ):
                return True
        return False
    except socket.gaierror:
        return True  # fail closed on unresolvable


def _blocked(host: str) -> Optional[str]:
    """Return a reason string if ``host`` is blocked, else None."""
    if not host:
        return "missing hostname"
    lowered = host.lower()

    # Explicit local/private names
    if lowered in {"localhost"} or lowered.endswith(".local") or lowered.endswith(
        ".internal"
    ):
        return f"private/local hostname: {host}"

    blocklist = _DEFAULT_BLOCKLIST + _extra_blocklist()
    for pattern in blocklist:
        if pattern and (lowered == pattern or lowered.endswith("." + pattern)):
            return f"domain on blocklist: {pattern}"

    allow = _allowlist()
    if allow:
        hit = any(lowered == a or lowered.endswith("." + a) for a in allow)
        if not hit:
            return f"domain not on allowlist: {host}"

    if _is_private_ip(host):
        return f"resolves to private/reserved address: {host}"

    return None


def _validate_url(url: str) -> Tuple[bool, Optional[str]]:
    if not isinstance(url, str) or not url:
        return False, "URL required"
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"malformed URL: {e}"
    if parsed.scheme not in {"http", "https"}:
        return False, f"scheme not allowed: {parsed.scheme or '<empty>'}"
    host = (parsed.hostname or "").lower()
    reason = _blocked(host)
    if reason:
        return False, reason
    return True, None


def _html_to_text(html: str) -> str:
    stripped = _SCRIPT_STYLE_RE.sub("", html)
    stripped = _TAG_RE.sub("", stripped)
    # Unescape the most common entities without pulling a dep
    stripped = (
        stripped.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    stripped = _WS_RE.sub(" ", stripped)
    stripped = _NEWLINE_COLLAPSE_RE.sub("\n\n", stripped)
    return stripped.strip()


async def web_fetch(url: str) -> Dict[str, Any]:
    """Fetch a URL and return its text content, with strict guardrails.

    Defense layers: scheme + host validation, private-IP block, domain
    blocklist, 256KB cap, 10s timeout, redirect re-validation, Unicode
    sanitization on the returned body.

    Args:
        url: Absolute http(s) URL to fetch.

    Returns:
        ``{"status": "success", "url": <final>, "content_type": ..., "content": ...}``
        on success; ``{"status": "error", "message": ...}`` on any failure.
        Content is already sanitized; HTML is stripped to plain text.
    """
    ok, reason = _validate_url(url)
    if not ok:
        logger.warning("web_fetch rejected %s: %s", url, reason)
        return {"status": "error", "message": f"refused: {reason}"}

    max_bytes = _max_bytes()
    timeout = _timeout_seconds()

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,text/plain,application/json,*/*;q=0.5"},
        ) as client:
            current_url = url
            for hop in range(_DEFAULT_MAX_REDIRECTS + 1):
                resp = await client.get(current_url)
                if resp.is_redirect:
                    next_url = resp.headers.get("location", "")
                    if not next_url:
                        return {"status": "error", "message": "redirect with no Location"}
                    # Resolve relative redirects against the current URL
                    next_url = str(httpx.URL(current_url).join(next_url))
                    ok, reason = _validate_url(next_url)
                    if not ok:
                        logger.warning(
                            "web_fetch rejected redirect %s → %s: %s",
                            current_url,
                            next_url,
                            reason,
                        )
                        return {
                            "status": "error",
                            "message": f"refused redirect: {reason}",
                        }
                    if hop >= _DEFAULT_MAX_REDIRECTS:
                        return {
                            "status": "error",
                            "message": f"too many redirects (>{_DEFAULT_MAX_REDIRECTS})",
                        }
                    current_url = next_url
                    continue
                break
            else:  # pragma: no cover — for-loop else never hit due to explicit break
                return {"status": "error", "message": "redirect loop"}

            if resp.status_code >= 400:
                return {
                    "status": "error",
                    "message": f"HTTP {resp.status_code} from {current_url}",
                }

            # Enforce size cap by reading capped bytes
            body = resp.content
            if len(body) > max_bytes:
                body = body[:max_bytes]
                truncated = True
            else:
                truncated = False

            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            try:
                text = body.decode(resp.encoding or "utf-8", errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")

            if "html" in content_type:
                text = _html_to_text(text)

            safe = sanitize_external_content(text, source="web_fetch", strictness="strict")

            logger.info(
                "web_fetch ok url=%s final=%s bytes=%d truncated=%s ctype=%s",
                url,
                current_url,
                len(body),
                truncated,
                content_type,
            )

            result: Dict[str, Any] = {
                "status": "success",
                "url": current_url,
                "content_type": content_type or "unknown",
                "content": safe,
            }
            if truncated:
                result["truncated"] = True
                result["truncated_at_bytes"] = max_bytes
            return result

    except httpx.TimeoutException:
        logger.warning("web_fetch timeout url=%s timeout=%s", url, timeout)
        return {"status": "error", "message": f"timeout after {timeout}s"}
    except httpx.HTTPError as e:
        logger.warning("web_fetch http error url=%s err=%s", url, e)
        return {"status": "error", "message": f"http error: {e}"}
    except Exception as e:  # surface unexpected failures to scout, not the model
        logger.exception("web_fetch unexpected failure url=%s", url)
        return {"status": "error", "message": f"fetch failed: {e}"}


web_fetch_tool = FunctionTool(web_fetch)

WEB_RESEARCH_TOOLS = [web_fetch_tool]
