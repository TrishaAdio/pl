"""
utils/emoji_entities.py — Build Telegram MessageEntityCustomEmoji objects
for use in Telethon messages.
"""

from typing import List, Tuple
from telethon.tl.types import MessageEntityCustomEmoji
from config import config


def build_custom_emoji_entities(text: str) -> Tuple[str, List[MessageEntityCustomEmoji]]:
    """
    Scan `text` for known emoji characters and produce
    MessageEntityCustomEmoji entries so Telegram renders
    the premium animated custom emoji.

    Returns:
        (text, [MessageEntityCustomEmoji, ...])
    """
    entities: List[MessageEntityCustomEmoji] = []
    text_bytes = text.encode("utf-16-le")

    # We need UTF-16 offsets for Telegram entities
    # Walk through the string character by character
    offset_utf16 = 0
    i = 0
    chars = list(text)

    while i < len(chars):
        ch = chars[i]
        # Check two-char combos (e.g. ☑️ = ☑ + variation selector)
        two_char = text[i : i + 2] if i + 1 < len(chars) else ""

        matched_emoji = None
        matched_len_chars = 0

        if two_char in config.EMOJI_IDS:
            matched_emoji = two_char
            matched_len_chars = 2
        elif ch in config.EMOJI_IDS:
            matched_emoji = ch
            matched_len_chars = 1

        if matched_emoji is not None:
            doc_id = config.EMOJI_IDS[matched_emoji]
            # Length in UTF-16 code units
            utf16_len = len(matched_emoji.encode("utf-16-le")) // 2
            entities.append(
                MessageEntityCustomEmoji(
                    offset=offset_utf16,
                    length=utf16_len,
                    document_id=doc_id,
                )
            )
            # Advance
            for j in range(matched_len_chars):
                c = chars[i + j]
                offset_utf16 += len(c.encode("utf-16-le")) // 2
            i += matched_len_chars
        else:
            offset_utf16 += len(ch.encode("utf-16-le")) // 2
            i += 1

    return text, entities


def discovery_header() -> Tuple[str, List[MessageEntityCustomEmoji]]:
    """Return the '✔️🔎💙👌🌸 New Discovery' text + entities."""
    text = "✔️🔎💙👌🌸 New Discovery"
    return build_custom_emoji_entities(text)


def broken_header() -> Tuple[str, List[MessageEntityCustomEmoji]]:
    """Return the '💔 Oh Sad...' text + entities."""
    text = "💔 Oh Sad..."
    return build_custom_emoji_entities(text)
