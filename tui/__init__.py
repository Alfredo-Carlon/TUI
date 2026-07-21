"""A small, dependency-free text-user-interface toolkit built on curses.

Public API::

    from tui import Window, TextView, ScrollView, SelectView, InputView, SeparatorView
    from tui import Key, KBInter, WindowCreator

Views are laid out in a :class:`Window` using a lower-left coordinate origin;
keystrokes are decoded by :class:`KBInter` into :class:`Key` values.
"""

from .keys import Key, KBInter, to_key
from .formatting import parse_format
from .views import View, TextView, SeparatorView, ScrollView, SelectView, InputView
from .window import Window
from .creator import WindowCreator

__all__ = [
    "Key", "KBInter", "to_key", "parse_format",
    "View", "TextView", "SeparatorView", "ScrollView", "SelectView", "InputView",
    "Window", "WindowCreator",
]
