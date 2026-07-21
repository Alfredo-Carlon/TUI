"""ScrollView -- a text region with keystroke-driven scrolling.

The mode is chosen by *which* scroll keystrokes the user supplies:

* vertical only  -> the text is hard-wrapped to the view width, scrolls by row.
* horizontal only-> no wrap; shows as many rows as fit, scrolls by column.
* both           -> no wrap; scrolls on both axes.
* neither        -> static top-left clip.

The wrapping and windowing are pure functions so they can be verified without
a terminal.

When vertical scrolling is enabled, the rightmost column carries scroll hints:
an ``↑`` on the top line when content is hidden above, and a ``↓`` on the last
line when content is hidden below.
"""

from .base import View
from ..formatting import parse_format
from ..geometry import clamp
from ..keys import to_key

ARROW_UP = "↑"      # UPWARDS ARROW -- "more content above" indicator
ARROW_DOWN = "↓"    # DOWNWARDS ARROW -- "more content below" indicator


def wrap_line(line, width):
    """Hard-wrap one logical line to ``width`` columns.  ``''`` -> ``['']``."""
    if width <= 0 or line == "":
        return [line]
    return [line[i:i + width] for i in range(0, len(line), width)]


def wrap_text(text, width):
    """Hard-wrap multi-line text, preserving blank lines."""
    out = []
    for line in text.split("\n"):
        out.extend(wrap_line(line, width))
    return out


class ScrollView(View):
    def __init__(self, name, origin, width, height, content="", format="", fmt="",
                 scroll_up=None, scroll_down=None, scroll_left=None,
                 scroll_right=None, step=1):
        super().__init__(name, origin, width, height)
        self._fmt_spec = format or fmt
        self.step = max(1, int(step))
        self.k_up = to_key(scroll_up)
        self.k_down = to_key(scroll_down)
        self.k_left = to_key(scroll_left)
        self.k_right = to_key(scroll_right)
        self.offset_x = 0
        self.offset_y = 0
        self.set_content(content)

    # --- modes ---------------------------------------------------------------
    @property
    def vertical(self):
        return self.k_up is not None or self.k_down is not None

    @property
    def horizontal(self):
        return self.k_left is not None or self.k_right is not None

    # --- data mutation -------------------------------------------------------
    def set_content(self, content):
        self.content = "" if content is None else str(content)
        self.offset_x = 0
        self.offset_y = 0

    replace = set_content

    def clear(self):
        self.set_content("")

    # --- layout (pure) -------------------------------------------------------
    def display_lines(self):
        """The list of lines actually laid out, honoring wrap mode."""
        if self.vertical and not self.horizontal:
            return wrap_text(self.content, self.width)
        return self.content.split("\n")

    def _max_offsets(self, lines):
        max_y = max(0, len(lines) - self.height)
        if self.horizontal:
            longest = max((len(l) for l in lines), default=0)
            max_x = max(0, longest - self.width)
        else:
            max_x = 0
        return max_x, max_y

    # --- rendering -----------------------------------------------------------
    def draw(self):
        self._erase()
        attr = parse_format(self._fmt_spec)
        lines = self.display_lines()
        max_x, max_y = self._max_offsets(lines)
        self.offset_y = clamp(self.offset_y, 0, max_y)
        self.offset_x = clamp(self.offset_x, 0, max_x)
        visible = lines[self.offset_y:self.offset_y + self.height]
        for i, line in enumerate(visible):
            ly = self.height - 1 - i
            seg = line[self.offset_x:self.offset_x + self.width]
            self._addstr(0, ly, seg, attr)

        # Overlay scroll indicators on the rightmost column: an up arrow on the
        # top line when there is content above, a down arrow on the last line
        # when there is content below.  Only shown when the matching scroll key
        # is bound (otherwise the user cannot actually scroll that way).  On a
        # single-row view where both apply, the down arrow wins (drawn last).
        rx = self.width - 1
        if self.k_up is not None and self.offset_y > 0:
            self._addstr(rx, self.height - 1, ARROW_UP, attr)
        if self.k_down is not None and self.offset_y < max_y and visible:
            self._addstr(rx, self.height - len(visible), ARROW_DOWN, attr)

    def handle_key(self, key):
        lines = self.display_lines()
        max_x, max_y = self._max_offsets(lines)
        if self.k_up is not None and key == self.k_up:
            self.offset_y = clamp(self.offset_y - self.step, 0, max_y)
            return True
        if self.k_down is not None and key == self.k_down:
            self.offset_y = clamp(self.offset_y + self.step, 0, max_y)
            return True
        if self.k_left is not None and key == self.k_left:
            self.offset_x = clamp(self.offset_x - self.step, 0, max_x)
            return True
        if self.k_right is not None and key == self.k_right:
            self.offset_x = clamp(self.offset_x + self.step, 0, max_x)
            return True
        return False

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d.get("name", ""),
            origin=d["origin"],
            width=d["width"],
            height=d["height"],
            content=d.get("content", ""),
            format=d.get("format", ""),
            scroll_up=d.get("scroll-up"),
            scroll_down=d.get("scroll-down"),
            scroll_left=d.get("scroll-left"),
            scroll_right=d.get("scroll-right"),
            step=int(d.get("step", 1)),
        )
