"""InputView -- a modal, multi-line text editor.

While *active* it captures every keystroke (the Window routes exclusively to
it).  Enter inserts a newline, Backspace/Delete edit, and the arrow keys plus
Home/End navigate.  A block hardware cursor marks the insertion point.  The
activate/deactivate keystrokes are user-supplied; on deactivation the completion
callback is invoked with the full text.

The callback is expected to return a truthy value on success and a falsy one on
failure.  The submitted text then stays on screen as feedback -- rendered with
``fmt_success`` (bold green) after a success or ``fmt_failure`` (bold red) after
a failure -- until the user next activates the view.  On that re-activation a
prior *success* clears the field for fresh input, while a prior *failure* keeps
the text so it can be corrected and resubmitted.  A view with no callback keeps
its plain formatting and never clears itself.
"""

from .base import View
from ..formatting import parse_format
from ..geometry import clamp
from ..keys import (to_key, ENTER, BACKSPACE, DELETE, LEFT, RIGHT, UP, DOWN,
                    HOME, END, TAB)


class InputView(View):
    def __init__(self, name, origin, width, height, content="",
                 activate=None, deactivate=None, on_submit=None,
                 format="", fmt="", fmt_success="bold green",
                 fmt_failure="bold red", tab_width=4):
        super().__init__(name, origin, width, height)
        self._fmt_spec = format or fmt
        self.fmt_success = fmt_success
        self.fmt_failure = fmt_failure
        self.k_activate = to_key(activate)
        self.k_deactivate = to_key(deactivate)
        self.on_submit = on_submit
        self.tab_width = max(1, int(tab_width))
        self._active = False
        # Result of the last submission: None (none/editing), True (success),
        # or False (failure).  Drives the feedback format and what activation
        # does to the field.
        self._result = None
        self.top = 0        # first visible buffer row
        self.left = 0       # horizontal scroll (columns)
        self.set_content(content)

    @property
    def active(self):
        return self._active

    # --- data mutation -------------------------------------------------------
    def set_content(self, content):
        content = "" if content is None else str(content)
        self.lines = content.split("\n") or [""]
        if not self.lines:
            self.lines = [""]
        self.cy = len(self.lines) - 1
        self.cx = len(self.lines[self.cy])
        self.top = 0
        self.left = 0
        self._result = None

    replace = set_content

    def clear(self):
        self.lines = [""]
        self.cy = self.cx = 0
        self.top = self.left = 0
        self._result = None

    def text(self):
        return "\n".join(self.lines)

    # --- viewport ------------------------------------------------------------
    def _scroll_to_cursor(self):
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + self.height:
            self.top = self.cy - self.height + 1
        self.top = max(0, self.top)
        if self.cx < self.left:
            self.left = self.cx
        elif self.cx >= self.left + self.width:
            self.left = self.cx - self.width + 1
        self.left = max(0, self.left)

    # --- rendering -----------------------------------------------------------
    def draw(self):
        self._erase()
        self._scroll_to_cursor()
        if self._result is True:
            spec = self.fmt_success
        elif self._result is False:
            spec = self.fmt_failure
        else:
            spec = self._fmt_spec
        attr = parse_format(spec)
        visible = self.lines[self.top:self.top + self.height]
        for i, line in enumerate(visible):
            ly = self.height - 1 - i
            seg = line[self.left:self.left + self.width]
            self._addstr(0, ly, seg, attr)

    def place_cursor(self):
        if self.win is None:
            return
        self._scroll_to_cursor()
        # Top visible line maps to curses row 0, so the on-screen row is simply
        # the cursor's distance below the viewport top.
        row = clamp(self.cy - self.top, 0, self._eff_h - 1)
        col = clamp(self.cx - self.left, 0, self._eff_w - 1)
        try:
            self.win.move(row, col)
        except Exception:
            pass

    # --- interaction ---------------------------------------------------------
    def _activate(self):
        # Entering the field consumes the previous result: a success clears the
        # field for fresh input, a failure keeps the text so it can be fixed.
        # Either way editing resumes with the plain format until the next submit.
        if self._result is True:
            self.clear()
        self._result = None
        self._active = True

    def handle_key(self, key):
        if not self._active:
            if self.k_activate is not None and key == self.k_activate:
                self._activate()
                return True
            return False
        # Active: check deactivate first so a shared toggle key closes the view.
        if self.k_deactivate is not None and key == self.k_deactivate:
            self._active = False
            if self.on_submit:
                # Truthy return -> success (bold green, clears on re-entry);
                # falsy -> failure (bold red, text persists on re-entry).
                self._result = bool(self.on_submit(self.text()))
            return True
        self._edit(key)
        return True

    def _insert(self, s):
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx] + s + line[self.cx:]
        self.cx += len(s)

    def _edit(self, key):
        name = key.name
        # Ignore other modified combos while typing (they aren't text input).
        if (key.ctrl or key.alt) and name != " ":
            return

        if name == ENTER:
            rest = self.lines[self.cy][self.cx:]
            self.lines[self.cy] = self.lines[self.cy][:self.cx]
            self.lines.insert(self.cy + 1, rest)
            self.cy += 1
            self.cx = 0
        elif name == BACKSPACE:
            if self.cx > 0:
                line = self.lines[self.cy]
                self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
                self.cx -= 1
            elif self.cy > 0:
                prev = self.lines[self.cy - 1]
                self.cx = len(prev)
                self.lines[self.cy - 1] = prev + self.lines[self.cy]
                del self.lines[self.cy]
                self.cy -= 1
        elif name == DELETE:
            line = self.lines[self.cy]
            if self.cx < len(line):
                self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
            elif self.cy < len(self.lines) - 1:
                self.lines[self.cy] = line + self.lines[self.cy + 1]
                del self.lines[self.cy + 1]
        elif name == LEFT:
            if self.cx > 0:
                self.cx -= 1
            elif self.cy > 0:
                self.cy -= 1
                self.cx = len(self.lines[self.cy])
        elif name == RIGHT:
            if self.cx < len(self.lines[self.cy]):
                self.cx += 1
            elif self.cy < len(self.lines) - 1:
                self.cy += 1
                self.cx = 0
        elif name == UP:
            if self.cy > 0:
                self.cy -= 1
                self.cx = min(self.cx, len(self.lines[self.cy]))
        elif name == DOWN:
            if self.cy < len(self.lines) - 1:
                self.cy += 1
                self.cx = min(self.cx, len(self.lines[self.cy]))
        elif name == HOME:
            self.cx = 0
        elif name == END:
            self.cx = len(self.lines[self.cy])
        elif name == TAB:
            self._insert(" " * self.tab_width)
        elif len(name) == 1 and name >= " ":
            self._insert(name)

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d.get("name", ""),
            origin=d["origin"],
            width=d["width"],
            height=d["height"],
            content=d.get("content", ""),
            activate=d.get("activate"),
            deactivate=d.get("deactivate"),
            on_submit=d.get("callback"),
            format=d.get("format", ""),
            fmt_success=d.get("success-format", "bold green"),
            fmt_failure=d.get("failure-format", "bold red"),
        )
