"""Utility functions for Weixin iLink Adapter."""

import base64
import re
import secrets
from typing import Any


def random_wechat_uin() -> str:
    """X-WECHAT-UIN: random uint32 as decimal string, base64-encoded."""
    u32 = int.from_bytes(secrets.token_bytes(4), "big") & 0xFFFFFFFF
    return base64.b64encode(str(u32).encode()).decode("ascii")


def ensure_trailing_slash(url: str) -> str:
    """Ensure URL ends with a trailing slash."""
    return url if url.endswith("/") else f"{url}/"


def markdown_to_plain_text(text: str) -> str:
    """Strip markdown for Weixin plain-text delivery."""
    if not text:
        return ""
    result = text
    result = re.sub(r"```[^\n]*\n?([\s\S]*?)```", lambda m: m.group(1).strip(), result)
    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)
    result = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", result)
    result = re.sub(r"^\|[\s:|-]+\|$", "", result, flags=re.MULTILINE)
    result = re.sub(
        r"^\|(.+)\|$",
        lambda m: "  ".join(c.strip() for c in m.group(1).split("|")),
        result,
        flags=re.MULTILINE,
    )
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"__(.+?)__", r"\1", result)
    result = re.sub(r"`([^`]+)`", r"\1", result)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    return result.strip()


def is_media_item(item: dict[str, Any]) -> bool:
    """Check if message item is a media type."""
    from weixin_adapter import constants
    t = item.get("type")
    return t in (
        constants.MESSAGE_ITEM_IMAGE,
        constants.MESSAGE_ITEM_VIDEO,
        constants.MESSAGE_ITEM_FILE,
        constants.MESSAGE_ITEM_VOICE,
    )


def body_from_item_list(item_list: list[dict[str, Any]] | None) -> str:
    """Extract text body from item_list."""
    from weixin_adapter import constants

    if not item_list:
        return ""
    for item in item_list:
        if item.get("type") == constants.MESSAGE_ITEM_TEXT:
            ti = item.get("text_item") or {}
            tx = ti.get("text")
            if tx is None:
                continue
            text = str(tx)
            ref = item.get("ref_msg")
            if not ref:
                return text
            rmi = (ref.get("message_item") or {}) if isinstance(ref, dict) else {}
            if rmi and is_media_item(rmi):
                return text
            parts: list[str] = []
            if isinstance(ref, dict) and ref.get("title"):
                parts.append(str(ref["title"]))
            if rmi:
                rb = body_from_item_list([rmi])
                if rb:
                    parts.append(rb)
            if not parts:
                return text
            return f'[引用: {" | ".join(parts)}]\n{text}'
        if item.get("type") == constants.MESSAGE_ITEM_VOICE:
            vi = item.get("voice_item") or {}
            if vi.get("text"):
                return str(vi["text"])
    return ""
