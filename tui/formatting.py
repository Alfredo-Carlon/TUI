"""Format-string parsing: ``"Red | Bold | on Blue"`` -> a curses attribute int.

The grammar is intentionally forgiving so users can be expressive:

* Tokens are separated by ``|`` and/or whitespace, case-insensitive.
* The first color name found is the foreground; ``on <color>`` (or a second
  bare color) is the background.
* ``bright`` / ``light`` before a color selects its high-intensity variant
  (when the terminal advertises >= 16 colors).
* Any of these attributes may be combined: bold, dim, reverse, standout,
  underline, blink, invisible, italic (italic only if the curses build has it).

Color *pairs* are allocated lazily the first time a ``(fg, bg)`` combination is
needed -- after the Window has called ``start_color()`` / ``use_default_colors()``.
All curses state access is guarded so this module is import- and parse-safe
without a live terminal (colors simply resolve to no-ops when uninitialized).
"""

import curses

_COLORS = {
    "black": curses.COLOR_BLACK,
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "purple": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
    "default": -1,
    "none": -1,
}

_ATTRS = {
    "bold": curses.A_BOLD,
    "dim": curses.A_DIM,
    "reverse": curses.A_REVERSE,
    "standout": curses.A_STANDOUT,
    "underline": curses.A_UNDERLINE,
    "under": curses.A_UNDERLINE,
    "blink": curses.A_BLINK,
    "invisible": curses.A_INVIS,
    "invis": curses.A_INVIS,
    "normal": curses.A_NORMAL,
}
if hasattr(curses, "A_ITALIC"):
    _ATTRS["italic"] = curses.A_ITALIC


class _PairRegistry:
    """Maps ``(fg, bg)`` color combinations to curses color-pair indices,
    allocating lazily and never exceeding the terminal's pair budget."""

    def __init__(self):
        self._pairs = {}
        self._next = 1

    def pair(self, fg, bg):
        if fg == -1 and bg == -1:
            return 0  # default-on-default needs no pair
        key = (fg, bg)
        if key in self._pairs:
            return self._pairs[key]
        idx = self._next
        max_pairs = getattr(curses, "COLOR_PAIRS", 0)
        if max_pairs and idx >= max_pairs:
            return 0  # out of pairs -> fall back to default colors
        try:
            curses.init_pair(idx, fg, bg)
        except (curses.error, ValueError):
            return 0  # curses not initialized (headless) or bad color
        self._pairs[key] = idx
        self._next += 1
        return idx


_registry = _PairRegistry()


def reset_registry():
    """Start a fresh pair registry -- called once when a Window starts, so a
    re-run inside the same process doesn't reuse stale pair indices."""
    global _registry
    _registry = _PairRegistry()


def _color_value(name, bright):
    base = _COLORS.get(name)
    if base is None:
        return None
    if bright and base >= 0 and getattr(curses, "COLORS", 0) >= 16:
        return base + 8
    return base


def parse_format(spec):
    """Turn a format spec string into a combined curses attribute integer.

    Unknown tokens are ignored (leniency over strictness).  An empty/None spec
    yields ``A_NORMAL``.
    """
    if not spec:
        return curses.A_NORMAL

    fg, bg = -1, -1
    fg_set = False
    attr = 0
    expecting_bg = False
    pending_bright = False

    for word in spec.replace("|", " ").split():
        w = word.lower()
        if w == "on":
            expecting_bg = True
            continue
        if w in ("bright", "light"):
            pending_bright = True
            continue
        if w in _ATTRS and not expecting_bg:
            attr |= _ATTRS[w]
            pending_bright = False
            continue
        color = _color_value(w, pending_bright)
        pending_bright = False
        if color is None:
            continue  # ignore unknown token
        if expecting_bg:
            bg = color
            expecting_bg = False
        elif not fg_set:
            fg = color
            fg_set = True
        else:
            bg = color

    pair = _registry.pair(fg, bg)
    if pair:
        attr |= curses.color_pair(pair)
    return attr
