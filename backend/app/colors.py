"""Deterministic member colors (FR-10): >=8 accessible colors, chosen from a
stable hash of the member id so a returning member keeps their color."""

from __future__ import annotations

import hashlib

# 8-color WCAG-conscious palette (hex values chosen for contrast on light and
# dark canvases).
PALETTE = [
    "#B3005E",  # magenta
    "#1F6FEB",  # blue
    "#1A7F37",  # green
    "#BF8700",  # amber (dark enough for text on white)
    "#8250DF",  # purple
    "#CF222E",  # red
    "#0969DA",  # azure
    "#116466",  # teal
]


def color_for(member_id: str) -> str:
    digest = hashlib.sha256(member_id.encode()).digest()
    return PALETTE[digest[0] % len(PALETTE)]
