"""TextView -- a static rectangular region that displays formatted text,
trimmed to fit."""

from .base import View
from ..formatting import parse_format


class TextView(View):
    def __init__(self, name, origin, width, height, content="", format="", fmt=""):
        super().__init__(name, origin, width, height)
        self._fmt_spec = format or fmt
        self.set_content(content)

    # --- data mutation -------------------------------------------------------
    def set_content(self, content):
        self.content = "" if content is None else str(content)
        self._lines = self.content.split("\n")

    replace = set_content

    def clear(self):
        self.set_content("")

    def set_format(self, spec):
        self._fmt_spec = spec

    # --- rendering -----------------------------------------------------------
    def draw(self):
        self._erase()
        attr = parse_format(self._fmt_spec)
        # First logical line at the top; keep only what fits, clip each line.
        for i, line in enumerate(self._lines[:self.height]):
            ly = self.height - 1 - i          # top row first
            self._addstr(0, ly, line[:self.width], attr)

    def handle_key(self, key):
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
        )
