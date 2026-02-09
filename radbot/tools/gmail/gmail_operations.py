"""Low-level Gmail API operations."""

import base64
import logging
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Type alias
GmailService = Any


def _decode_body(payload: Dict[str, Any]) -> str:
    """Decode the message body from a Gmail message payload.

    Handles both simple messages and multipart MIME structures.
    Prefers plain text; falls back to stripping HTML tags.

    Args:
        payload: The message payload dict from the Gmail API.

    Returns:
        Decoded body text.
    """
    # Try to find plain text part first, then HTML
    plain_text = ""
    html_text = ""

    def _extract_parts(part: Dict[str, Any]):
        nonlocal plain_text, html_text
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data and not plain_text:
            try:
                plain_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            except Exception:
                pass
        elif mime_type == "text/html" and body_data and not html_text:
            try:
                html_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            except Exception:
                pass

        # Recurse into sub-parts
        for sub_part in part.get("parts", []):
            _extract_parts(sub_part)

    _extract_parts(payload)

    if plain_text:
        return plain_text

    if html_text:
        # Simple HTML tag stripping (no extra dependencies)
        import re
        text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        return text.strip()

    return ""


def _parse_message(raw_message: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a raw Gmail API message into a structured dict.

    Args:
        raw_message: The full message resource from Gmail API.

    Returns:
        Dict with id, threadId, snippet, subject, from, to, date, body, attachments.
    """
    payload = raw_message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    # Extract attachment metadata
    attachments = []
    def _find_attachments(part: Dict[str, Any]):
        filename = part.get("filename", "")
        if filename:
            attachments.append({
                "filename": filename,
                "mimeType": part.get("mimeType", ""),
                "size": part.get("body", {}).get("size", 0),
            })
        for sub_part in part.get("parts", []):
            _find_attachments(sub_part)

    _find_attachments(payload)

    body = _decode_body(payload)

    from radbot.tools.shared.sanitize import sanitize_dict
    return sanitize_dict({
        "id": raw_message.get("id", ""),
        "threadId": raw_message.get("threadId", ""),
        "snippet": raw_message.get("snippet", ""),
        "subject": headers.get("subject", "(no subject)"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "body": body,
        "attachments": attachments,
        "labelIds": raw_message.get("labelIds", []),
    }, source="gmail", keys=["snippet", "subject", "from", "to", "body"])


def list_messages(
    service: GmailService,
    max_results: int = 10,
    label_ids: Optional[List[str]] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List messages from Gmail.

    Args:
        service: Authenticated Gmail API service object.
        max_results: Maximum number of messages to return.
        label_ids: Label IDs to filter by (default: ["INBOX"]).
        query: Gmail search query string.

    Returns:
        List of message stubs with id, threadId, and snippet.
    """
    if label_ids is None:
        label_ids = ["INBOX"]

    try:
        params: Dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
        }
        if label_ids:
            params["labelIds"] = label_ids
        if query:
            params["q"] = query

        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])

        if not messages:
            return []

        # Fetch snippet for each message via metadata format
        enriched = []
        for msg_stub in messages:
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=msg_stub["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                ).execute()
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                from radbot.tools.shared.sanitize import sanitize_dict
                enriched.append(sanitize_dict({
                    "id": msg.get("id", ""),
                    "threadId": msg.get("threadId", ""),
                    "snippet": msg.get("snippet", ""),
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from", ""),
                    "date": headers.get("date", ""),
                }, source="gmail", keys=["snippet", "subject", "from"]))
            except HttpError as e:
                logger.warning(f"Failed to fetch metadata for message {msg_stub['id']}: {e}")
                enriched.append({
                    "id": msg_stub.get("id", ""),
                    "threadId": msg_stub.get("threadId", ""),
                    "snippet": "",
                    "subject": "(error fetching)",
                    "from": "",
                    "date": "",
                })

        return enriched

    except HttpError as e:
        logger.error(f"Error listing Gmail messages: {e}")
        return []


def get_message(
    service: GmailService,
    message_id: str,
    msg_format: str = "full",
) -> Optional[Dict[str, Any]]:
    """Get a full Gmail message by ID.

    Args:
        service: Authenticated Gmail API service object.
        message_id: The message ID.
        msg_format: The format to retrieve ("full", "metadata", "raw", "minimal").

    Returns:
        Parsed message dict or None on error.
    """
    try:
        raw = service.users().messages().get(
            userId="me",
            id=message_id,
            format=msg_format,
        ).execute()
        return _parse_message(raw)
    except HttpError as e:
        logger.error(f"Error getting Gmail message {message_id}: {e}")
        return None


def search_messages(
    service: GmailService,
    query: str,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Search Gmail messages using Gmail query syntax.

    Args:
        service: Authenticated Gmail API service object.
        query: Gmail search query (supports Gmail search operators).
        max_results: Maximum number of results.

    Returns:
        List of message stubs with id, threadId, snippet, subject, from, date.
    """
    return list_messages(service, max_results=max_results, label_ids=None, query=query)
