"""Button color & premium-emoji helpers (Telegram Bot API 9.4+).

Bot API 9.4 (Feb 2026) added two optional fields to BOTH ``InlineKeyboardButton``
and ``KeyboardButton``:

* ``style`` — one of ``"primary"`` (blue), ``"success"`` (green), ``"danger"``
  (red). Omitted ⇒ the client's default button color.
* ``icon_custom_emoji_id`` — a premium (custom) emoji shown before the label.
  Usable only by bots whose owner has Telegram Premium (or that purchased a
  username on Fragment).

The installed aiogram models declare ``model_config = {"extra": "allow"}``, so
these fields can be passed straight through ``builder.button(...)`` and are
serialized to the API even before aiogram adds them natively. ``style_kwargs``
returns only the keys that are actually set, so a neutral button stays neutral.
"""
from __future__ import annotations

from typing import Any

# Telegram style tokens (sent verbatim to the Bot API).
STYLE_PRIMARY = "primary"  # 🔵 blue
STYLE_SUCCESS = "success"  # 🟢 green
STYLE_DANGER = "danger"    # 🔴 red

VALID_STYLES = (STYLE_PRIMARY, STYLE_SUCCESS, STYLE_DANGER)

# Persian labels + colored dot for the admin appearance picker.
STYLE_LABELS: dict[str, str] = {
    STYLE_PRIMARY: "🔵 آبی",
    STYLE_SUCCESS: "🟢 سبز",
    STYLE_DANGER: "🔴 قرمز",
}

STYLE_DOT: dict[str, str] = {
    STYLE_PRIMARY: "🔵",
    STYLE_SUCCESS: "🟢",
    STYLE_DANGER: "🔴",
}


def style_kwargs(
    style: str | None = None, custom_emoji_id: str | None = None
) -> dict[str, Any]:
    """Return the keyboard-button kwargs for color / premium emoji.

    Empty when nothing is set, so callers can splat it unconditionally:
    ``kb.button(text=..., **style_kwargs(style=STYLE_SUCCESS))``.
    """
    extra: dict[str, Any] = {}
    if style in VALID_STYLES:
        extra["style"] = style
    if custom_emoji_id:
        extra["icon_custom_emoji_id"] = custom_emoji_id
    return extra
