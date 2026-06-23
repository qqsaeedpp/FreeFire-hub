"""Premium-emoji entity helpers: UTF-16 offsets, persistence, card composition."""
from aiogram.types import MessageEntity

from app.utils.entities import (
    EntityCard,
    dump_entities,
    entities_for_storage,
    has_custom_emoji,
    load_entities,
    normalize_with_entities,
    utf16_len,
)


def _emoji(cid: str, offset: int = 0, length: int = 2) -> MessageEntity:
    return MessageEntity(
        type="custom_emoji", offset=offset, length=length, custom_emoji_id=cid
    )


def _emoji_at(text: str, offset: int) -> str:
    """Decode the 2 UTF-16 units at ``offset`` back to a character."""
    u = text.encode("utf-16-le")
    return u[offset * 2 : (offset + 2) * 2].decode("utf-16-le")


def test_utf16_len_counts_surrogate_pairs():
    assert utf16_len("A") == 1
    assert utf16_len("🦊") == 2  # one char, two UTF-16 code units
    assert utf16_len("🦊A") == 3


def test_dump_load_roundtrip_preserves_custom_emoji_id():
    raw = dump_entities([_emoji("5123"), MessageEntity(type="bold", offset=3, length=4)])
    back = load_entities(raw)
    assert back[0].type == "custom_emoji" and back[0].custom_emoji_id == "5123"
    assert back[1].type == "bold" and back[1].offset == 3


def test_load_entities_tolerates_empty_and_garbage():
    assert load_entities(None) is None
    assert load_entities("") is None
    assert load_entities("not json") is None
    assert load_entities("[]") is None


def test_storage_gate_keeps_only_premium():
    assert has_custom_emoji([_emoji("9")]) is True
    assert has_custom_emoji([MessageEntity(type="bold", offset=0, length=1)]) is False
    # bold/url-only → not persisted; a custom_emoji present → persisted.
    assert entities_for_storage([MessageEntity(type="url", offset=0, length=4)]) is None
    assert entities_for_storage([_emoji("9")]) == [_emoji("9")]


def test_normalize_lstrip_shifts_offsets():
    text, ents = normalize_with_entities("  🦊x", [_emoji("9", offset=2)])
    assert text == "🦊x"
    assert ents[0].offset == 0 and ents[0].length == 2


def test_normalize_truncation_drops_split_custom_emoji():
    # 'abc🦊' capped to 3 chars → 'abc'; the trailing premium emoji is dropped whole.
    text, ents = normalize_with_entities("abc🦊", [_emoji("9", offset=3)], max_len=3)
    assert text == "abc"
    assert ents is None


def test_entitycard_shifts_embedded_offsets_to_utf16_position():
    card = (
        EntityCard()
        .bold("سرتیتر")
        .text("\nنام: ")
        .text("🦊نام", [_emoji("777")])
    )
    text, ents = card.build()
    bold, emoji = ents[0], ents[1]
    assert bold.type == "bold" and bold.offset == 0 and bold.length == utf16_len("سرتیتر")
    expected = utf16_len("سرتیتر" + "\nنام: ")
    assert emoji.type == "custom_emoji" and emoji.custom_emoji_id == "777"
    assert emoji.offset == expected
    assert _emoji_at(text, emoji.offset) == "🦊"


def test_entitycard_empty_returns_no_entities():
    text, ents = EntityCard().text("plain").build()
    assert text == "plain" and ents is None
