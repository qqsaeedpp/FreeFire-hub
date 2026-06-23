"""Premium (custom) emoji support for account text — capture, persist, re-render.

A Telegram *premium* emoji travels with a message as a ``custom_emoji``
**entity**: the text itself holds an ordinary fallback emoji while a parallel
:class:`~aiogram.types.MessageEntity` carries the ``custom_emoji_id``. To re-send
the very same premium emoji later we must persist those entities and replay them
with ``parse_mode=None`` — entities and HTML are mutually exclusive in the Bot
API (see :mod:`app.services.text_service`, which does the same for managed texts).

This module is the single home for that round-trip:

* :func:`dump_entities` / :func:`load_entities` — (de)serialise entities to the
  JSON stored on an account (``title_entities_json`` / ``description_entities_json``).
* :func:`normalize_with_entities` — apply the same ``strip``/truncate the form
  always did, but shift/clip the entity offsets so they stay aligned.
* :class:`EntityCard` — compose a card (bold headers + dynamic fields) into one
  ``(text, entities)`` pair with correct **UTF-16** offsets. Telegram measures
  entity offsets in UTF-16 code units, so a 4-byte emoji counts as 2 — naive
  ``len()`` math would corrupt every offset after the first emoji.

Only listings that actually carry a premium emoji store/replay entities; every
other listing renders through the exact HTML path it always did.
"""
from __future__ import annotations

import json

from aiogram.types import MessageEntity


def utf16_len(text: str) -> int:
    """Length of ``text`` in UTF-16 code units — Telegram's entity offset unit."""
    return len(text.encode("utf-16-le")) // 2


def has_custom_emoji(entities: list[MessageEntity] | None) -> bool:
    """Whether ``entities`` contains at least one premium (custom) emoji."""
    return bool(entities) and any(e.type == "custom_emoji" for e in entities)


def entities_for_storage(
    entities: list[MessageEntity] | None,
) -> list[MessageEntity] | None:
    """Keep entities only when a premium emoji is present, else ``None``.

    Telegram auto-detects URLs/mentions/emails as entities even with no
    formatting; persisting those for an ordinary listing would needlessly switch
    it onto the entity send-path. Storing entities *only* when a ``custom_emoji``
    is present keeps every non-premium listing byte-identical to before.
    """
    return list(entities) if has_custom_emoji(entities) else None


def dump_entities(entities: list[MessageEntity] | None) -> str | None:
    """Serialise entities to a JSON string (``None`` when empty)."""
    if not entities:
        return None
    return json.dumps(
        [e.model_dump(mode="json", exclude_none=True) for e in entities]
    )


def load_entities(raw: str | None) -> list[MessageEntity] | None:
    """Rebuild entities from stored JSON (``None`` when empty or malformed)."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not data:
        return None
    return [MessageEntity.model_validate(d) for d in data]


def entity_kwargs(entities: list[MessageEntity] | None) -> dict:
    """Extra kwargs for ``send_message``/``edit_text``/``answer``.

    With entities → replay them and disable HTML (mutually exclusive); without →
    an empty dict, so the bot's default HTML parse mode applies as before.
    """
    return {"entities": entities, "parse_mode": None} if entities else {}


def caption_entity_kwargs(entities: list[MessageEntity] | None) -> dict:
    """Like :func:`entity_kwargs` but for a photo ``caption``."""
    return {"caption_entities": entities, "parse_mode": None} if entities else {}


def _clip_entities(entities: list[MessageEntity], limit: int) -> list[MessageEntity]:
    """Drop/clip entities so none extends past ``limit`` UTF-16 units.

    A ``custom_emoji`` whose span would be cut is dropped wholesale (a partial
    custom-emoji length is rejected by Telegram); other entities are shortened.
    """
    out: list[MessageEntity] = []
    for e in entities:
        if e.offset >= limit:
            continue
        end = min(e.offset + e.length, limit)
        length = end - e.offset
        if length <= 0:
            continue
        if length != e.length:
            if e.type == "custom_emoji":
                continue
            e = e.model_copy(update={"length": length})
        out.append(e)
    return out


def normalize_with_entities(
    text: str | None,
    entities: list[MessageEntity] | None,
    *,
    max_len: int | None = None,
) -> tuple[str, list[MessageEntity] | None]:
    """Reproduce the form's ``text.strip()[:max_len]`` while keeping entities aligned.

    Leading whitespace shifts every offset left (entities starting inside the
    stripped run are clipped/dropped); trailing whitespace and the length cap clip
    entities that fall off the end. Returns the cleaned text and the surviving
    entities (``None`` when none remain).
    """
    text = text or ""
    ents = list(entities or [])

    # Left strip — shift offsets by the UTF-16 width of the removed prefix.
    lstripped = text.lstrip()
    shift = utf16_len(text) - utf16_len(lstripped)
    text = lstripped
    if shift:
        shifted: list[MessageEntity] = []
        for e in ents:
            new_off = e.offset - shift
            if new_off >= 0:
                shifted.append(e.model_copy(update={"offset": new_off}))
                continue
            new_len = e.length + new_off  # part of the entity was stripped
            if new_len > 0 and e.type != "custom_emoji":
                shifted.append(e.model_copy(update={"offset": 0, "length": new_len}))
        ents = shifted

    # Right strip, then optional length cap (Python chars, mirroring the old code).
    text = text.rstrip()
    if max_len is not None and len(text) > max_len:
        text = text[:max_len]

    ents = _clip_entities(ents, utf16_len(text))
    return text, (ents or None)


class EntityCard:
    """Accumulate plain text + entities with correct UTF-16 offsets.

    Headers are added as ``bold`` entities so the card looks identical to the old
    HTML ``<b>…</b>`` version, and each dynamic field is added together with its
    stored entities shifted to its absolute position. :meth:`build` returns
    ``(text, entities)`` ready to send with ``parse_mode=None``.
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._entities: list[MessageEntity] = []
        self._offset = 0

    def text(
        self, value: str, entities: list[MessageEntity] | None = None
    ) -> "EntityCard":
        """Append plain text, optionally carrying its own (relative) entities."""
        if not value:
            return self
        for e in entities or []:
            self._entities.append(
                e.model_copy(update={"offset": e.offset + self._offset})
            )
        self._parts.append(value)
        self._offset += utf16_len(value)
        return self

    def bold(self, value: str) -> "EntityCard":
        """Append text wrapped in a ``bold`` entity (a card header)."""
        if not value:
            return self
        self._entities.append(
            MessageEntity(type="bold", offset=self._offset, length=utf16_len(value))
        )
        self._parts.append(value)
        self._offset += utf16_len(value)
        return self

    def build(self) -> tuple[str, list[MessageEntity] | None]:
        return "".join(self._parts), (self._entities or None)
