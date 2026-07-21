"""The abstract :class:`View` base class.

A View owns a rectangular region and a backing curses window.  It exposes:

* two constructors -- an explicit ``__init__`` and a ``from_dict`` classmethod
  whose keys are short and self-explanatory (mirroring the layout-spec vocab);
* data mutation -- ``set_content`` / ``replace`` / ``clear`` (SelectView uses
  ``set_items``);
* the drawing helper ``_addstr`` which handles the lower-left -> curses flip,
  width clipping, and the notorious "writing the bottom-right cell raises even
  on success" curses quirk.
"""

import abc

import curses

from ..geometry import view_top_row, local_to_curses, clamp


class View(abc.ABC):
    def __init__(self, name, origin, width, height):
        self.name = name
        self.origin = (int(origin[0]), int(origin[1]))  # (ox, oy) lower-left
        self.width = int(width)
        self.height = int(height)
        self.win = None            # backing curses window (set by attach)
        self._eff_w = self.width   # effective (clamped) window size
        self._eff_h = self.height

    # --- geometry ------------------------------------------------------------
    @property
    def ox(self):
        return self.origin[0]

    @property
    def oy(self):
        return self.origin[1]

    def attach(self, win_width, win_height):
        """(Re)create the backing curses window for the current terminal size.

        Sizes and positions are clamped so a view that momentarily doesn't fit
        (e.g. mid-resize) degrades instead of raising ``curses.error``.
        """
        h = max(1, min(self.height, win_height))
        w = max(1, min(self.width, win_width))
        top = clamp(view_top_row(win_height, self.oy, self.height),
                    0, max(0, win_height - h))
        left = clamp(self.ox, 0, max(0, win_width - w))
        self._eff_h, self._eff_w = h, w
        self.win = curses.newwin(h, w, top, left)
        self.win.keypad(True)

    # --- drawing helpers -----------------------------------------------------
    def _erase(self):
        if self.win is not None:
            self.win.erase()

    def _addstr(self, lx, ly, text, attr=0):
        """Draw ``text`` at view-local ``(lx, ly)`` (``ly`` from the bottom).

        Clips to the view width, drops rows outside the view, and swallows the
        harmless error curses raises when the write reaches the very last cell.
        """
        if self.win is None or not text:
            return
        if ly < 0 or ly >= self._eff_h:
            return
        row, col = local_to_curses(self.height, lx, ly)
        if row < 0 or row >= self._eff_h:
            return
        if col < 0:
            text = text[-col:]
            col = 0
        avail = self._eff_w - col
        if avail <= 0:
            return
        text = text[:avail]
        try:
            self.win.addstr(row, col, text, attr)
        except curses.error:
            # addstr to the bottom-right cell writes the glyph then fails to
            # advance the cursor -> the glyph is present; ignore the error.
            pass

    def noutrefresh(self):
        if self.win is not None:
            self.win.noutrefresh()

    # --- modal support (overridden by InputView) -----------------------------
    @property
    def active(self):
        return False

    def place_cursor(self):
        """Position the hardware cursor; meaningful only for active modal views."""
        return None

    # --- abstract API --------------------------------------------------------
    @abc.abstractmethod
    def draw(self):
        """Render the view's content into ``self.win``."""

    @abc.abstractmethod
    def handle_key(self, key):
        """Handle a :class:`~tui.keys.Key`; return ``True`` if consumed."""

    @classmethod
    def from_dict(cls, d):  # pragma: no cover - overridden by every subclass
        raise NotImplementedError
