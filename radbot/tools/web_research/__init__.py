"""Web research tools for scout (read-only, guardrailed).

Defense-in-depth layers for any web content that reaches scout's context:

1. URL validation — http/https only; block ``file://`` and other schemes.
2. Host validation — block private IPs, loopback, link-local (including AWS
   IMDS at ``169.254.169.254``), and known exfil sinks
   (pastebin, requestbin, webhook.site, ngrok, …).
3. Size + time caps — 256KB response body, 10s timeout, max 3 redirects.
4. Content sanitization — ``sanitize_external_content`` at strictness=strict.
5. Structured audit log per call.

Raw web search (Tavily / Brave) is tracked as PT19. For now scout relies on
the existing ``search_agent`` transfer path for grounded Google Search, and
uses :func:`web_fetch` to pull specific cited URLs.
"""

from radbot.tools.web_research.web_fetch import WEB_RESEARCH_TOOLS, web_fetch_tool

__all__ = ["WEB_RESEARCH_TOOLS", "web_fetch_tool"]
