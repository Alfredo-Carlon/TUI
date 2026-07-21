"""Keyboard decoding: the :class:`Key` value object and the :class:`KBInter`
decoder.

``KBInter`` turns raw curses key codes into normalized :class:`Key` objects,
correctly handling *modified* keystrokes -- ``Ctrl+<letter>`` and
``Alt+<key>`` -- which is the part most naive TUIs get wrong.

Design decisions (documented inline because there is no test suite):

* Terminals cannot distinguish some control bytes from named keys: ``Tab`` and
  ``Ctrl+I`` are both byte 9; ``Enter`` and ``Ctrl+M`` are both byte 13.  We
  resolve those bytes to the *named* key (``TAB`` / ``ENTER`` / ``BACKSPACE``)
  since that is what applications almost always mean.
* ``Ctrl+<letter>`` is case-insensitive -- the terminal sends the same byte for
  ``Ctrl+a`` and ``Ctrl+A`` -- so the letter is lower-cased.
* Plain printable characters keep their case (``w`` != ``W``): for printables
  Shift is meaningful and already reflected in the byte.
* ``Alt+X`` arrives as ``ESC`` followed by ``X``.  We read the ``ESC`` then peek
  (non-blocking) for a following key: if one is there it becomes ``Alt+...``,
  otherwise it is a bare ``ESC``.
"""

import curses
import dataclasses

# --- canonical special-key names ---------------------------------------------
UP = "UP"
DOWN = "DOWN"
LEFT = "LEFT"
RIGHT = "RIGHT"
ENTER = "ENTER"
BACKSPACE = "BACKSPACE"
DELETE = "DELETE"
INSERT = "INSERT"
TAB = "TAB"
HOME = "HOME"
END = "END"
PAGEUP = "PAGEUP"
PAGEDOWN = "PAGEDOWN"
ESC = "ESC"
RESIZE = "RESIZE"
SPACE = " "  # canonical name for the space key is the literal space character


@dataclasses.dataclass(frozen=True)
class Key:
    """An immutable, hashable keystroke.

    ``name`` is either a single character (``'a'``, ``' '``) or one of the
    canonical special names above.  ``ctrl`` / ``alt`` flag modifiers.  Being
    frozen and hashable, a ``Key`` works directly as a dict key and compares
    equal to any other ``Key`` with the same fields.
    """

    name: str
    ctrl: bool = False
    alt: bool = False

    def __str__(self):
        prefix = ("Ctrl+" if self.ctrl else "") + ("Alt+" if self.alt else "")
        shown = "SPACE" if self.name == " " else self.name
        return prefix + shown

    @classmethod
    def parse(cls, spec):
        """Parse a spec string like ``"Ctrl+s"``, ``"Alt+b"``, ``"UP"``,
        ``"w"`` or ``"Ctrl+Alt+x"`` into a :class:`Key`."""
        if isinstance(spec, cls):
            return spec
        raw = spec.strip()
        if raw == "":
            raise ValueError("empty key spec")
        if raw == "+":
            return cls("+")

        tokens = raw.split("+")
        key_tok = tokens[-1]
        mod_toks = tokens[:-1]
        if key_tok == "":  # e.g. "Ctrl++" -> the '+' key with Ctrl
            key_tok = "+"
            mod_toks = tokens[:-2]

        ctrl = alt = False
        for m in mod_toks:
            ml = m.strip().lower()
            if ml in ("ctrl", "control"):
                ctrl = True
            elif ml in ("alt", "meta", "option"):
                alt = True
            elif ml == "":
                continue
            else:
                raise ValueError("unknown modifier %r in %r" % (m, spec))

        low = key_tok.lower()
        if low in _SPECIAL_ALIASES:
            name = _SPECIAL_ALIASES[low]
        elif len(key_tok) == 1:
            # Ctrl folds case; plain printables keep it.
            name = key_tok.lower() if ctrl else key_tok
        else:
            name = key_tok.upper()
        return cls(name, ctrl=ctrl, alt=alt)


def to_key(spec):
    """Coerce ``None`` / str / :class:`Key` into a :class:`Key` or ``None``."""
    if spec is None:
        return None
    if isinstance(spec, Key):
        return spec
    return Key.parse(spec)


# --- spec aliases -------------------------------------------------------------
_SPECIAL_ALIASES = {
    "up": UP, "down": DOWN, "left": LEFT, "right": RIGHT,
    "enter": ENTER, "return": ENTER, "ret": ENTER, "cr": ENTER,
    "esc": ESC, "escape": ESC,
    "backspace": BACKSPACE, "bksp": BACKSPACE, "bs": BACKSPACE,
    "delete": DELETE, "del": DELETE,
    "insert": INSERT, "ins": INSERT,
    "tab": TAB,
    "space": SPACE, "spc": SPACE, "spacebar": SPACE,
    "home": HOME, "end": END,
    "pageup": PAGEUP, "pgup": PAGEUP, "pgdn": PAGEDOWN,
    "pagedown": PAGEDOWN, "pgdown": PAGEDOWN,
}
for _n in range(1, 25):  # F1..F24
    _SPECIAL_ALIASES["f%d" % _n] = "F%d" % _n


# --- curses code -> canonical name (special keys) -----------------------------
_SPECIAL_CODES = {
    curses.KEY_UP: UP,
    curses.KEY_DOWN: DOWN,
    curses.KEY_LEFT: LEFT,
    curses.KEY_RIGHT: RIGHT,
    curses.KEY_HOME: HOME,
    curses.KEY_END: END,
    curses.KEY_NPAGE: PAGEDOWN,
    curses.KEY_PPAGE: PAGEUP,
    curses.KEY_DC: DELETE,
    curses.KEY_IC: INSERT,
    curses.KEY_RESIZE: RESIZE,
}


# CSI ("ESC [") and SS3 ("ESC O") escape sequences -> canonical names, used as
# a fallback when curses hands us the raw sequence instead of a KEY_* code.
_CSI_SEQUENCES = {
    "[A": UP, "OA": UP,
    "[B": DOWN, "OB": DOWN,
    "[C": RIGHT, "OC": RIGHT,
    "[D": LEFT, "OD": LEFT,
    "[H": HOME, "OH": HOME,
    "[F": END, "OF": END,
    "[1~": HOME, "[2~": INSERT, "[3~": DELETE, "[4~": END,
    "[5~": PAGEUP, "[6~": PAGEDOWN, "[7~": HOME, "[8~": END,
}


class KBInter:
    """Reads and normalizes keystrokes from a curses window."""

    def read(self, stdscr):
        """Block for one keystroke and return a :class:`Key` (or ``None`` for an
        undecodable code)."""
        ch = stdscr.get_wch()
        return self._decode(stdscr, ch)

    def _decode(self, stdscr, ch):
        if ch is None:
            return None
        if isinstance(ch, str):
            code = ord(ch)
            char = ch
        else:
            code = ch
            char = None

        # ESC alone, the lead byte of a CSI/SS3 escape sequence, or the lead
        # byte of an Alt+<key> combination.
        if code == 27:
            stdscr.nodelay(True)
            try:
                nxt = stdscr.get_wch()
            except curses.error:
                nxt = None
            if nxt is None:
                stdscr.nodelay(False)
                return Key(ESC)
            # Fallback CSI/SS3 decoding.  Normally curses assembles arrow/nav
            # keys into KEY_* codes itself; this path catches the cases it does
            # not (e.g. a terminal or multiplexer sending CSI while curses is in
            # application-keypad mode).
            if isinstance(nxt, str) and nxt in ("[", "O"):
                seq = nxt
                try:
                    while True:
                        try:
                            c = stdscr.get_wch()
                        except curses.error:
                            c = None
                        if c is None or isinstance(c, int):
                            break
                        seq += c
                        if c.isalpha() or c == "~":
                            break
                finally:
                    stdscr.nodelay(False)
                mapped = _CSI_SEQUENCES.get(seq)
                return Key(mapped) if mapped is not None else Key(ESC)
            stdscr.nodelay(False)
            base = self._decode(stdscr, nxt)
            if base is None or base.name == ESC:
                return Key(ESC)
            return Key(base.name, ctrl=base.ctrl, alt=True)

        # Bytes that ambiguously mean a named key -- resolve to the name.
        if code in (8, 127) or code == curses.KEY_BACKSPACE:
            return Key(BACKSPACE)
        if code == 9:
            return Key(TAB)
        if code in (10, 13) or code == curses.KEY_ENTER:
            return Key(ENTER)

        named = _SPECIAL_CODES.get(code)
        if named is not None:
            return Key(named)

        if curses.KEY_F0 < code <= curses.KEY_F0 + 63:
            return Key("F%d" % (code - curses.KEY_F0))

        # Control codes 1..26 -> Ctrl+<letter>  (Ctrl+A == 1).
        if 1 <= code <= 26:
            return Key(chr(code + 96), ctrl=True)
        if code == 0:
            return Key(" ", ctrl=True)  # Ctrl+Space / Ctrl+@

        if char is not None:
            return Key(char)
        if 32 <= code < 127:
            return Key(chr(code))
        return None
