"""SeparatorView -- a thin rule (width 1 x N, or N x height 1, or a filled
block) that tiles a formatted string across its extent."""

from .base import View
from ..formatting import parse_format


class SeparatorView(View):
    def __init__(self, name, origin, width, height, content="-", format="", fmt=""):
        super().__init__(name, origin, width, height)
        self._fmt_spec = format or fmt
        self.set_content(content)

    def set_content(self, content):
        # Empty content would make tiling impossible; fall back to a space.
        self.content = content if content else " "

    replace = set_content

    def clear(self):
        self.set_content(" ")

    def _row_fill(self):
        unit = self.content
        reps = self.width // len(unit) + 1
        return (unit * reps)[:self.width]

    def draw(self):
        self._erase()
        attr = parse_format(self._fmt_spec)
        fill = self._row_fill()
        for ly in range(self.height):
            self._addstr(0, ly, fill, attr)

    def handle_key(self, key):
        return False

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d.get("name", ""),
            origin=d["origin"],
            width=d["width"],
            height=d["height"],
            content=d.get("content", "-"),
            format=d.get("format", ""),
        )
