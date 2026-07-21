"""Window -- the container that owns the views and drives the input loop.

Responsibilities:

* hold an ordered list of views plus a :class:`~tui.keys.KBInter`;
* size itself to the terminal and (re)lay out views on start and on resize;
* draw every frame and route keystrokes, honoring a *modal* view (an active
  :class:`~tui.views.input.InputView`) which, once focused, receives every key
  until it deactivates;
* dispatch global key bindings registered with :meth:`bind` / :meth:`unbind`
  (checked before the views, and -- like the quit key -- ignored while a modal
  view is capturing input).

``run()`` uses ``curses.wrapper`` so the terminal is always restored on exit --
even on an exception -- and ``curses.raw()`` so modifier keys (including
Ctrl+C) are delivered to the app as ordinary keystrokes rather than signals.
"""

import curses

from . import formatting
from .keys import KBInter, to_key, RESIZE


class Window:
    def __init__(self, views=None, quit_key="Ctrl+c"):
        self.views = list(views) if views else []
        self.kb = KBInter()
        self.quit_key = to_key(quit_key)
        self.bindings = {}         # Key -> zero-arg callback (global shortcuts)
        self.focus = None          # the modal view currently capturing input
        self.stdscr = None
        self.win_w = 0
        self.win_h = 0
        self._running = False

    # --- composition ---------------------------------------------------------
    def add(self, view):
        self.views.append(view)
        return view

    def get(self, name):
        for v in self.views:
            if v.name == name:
                return v
        return None

    def set_content(self, name, content):
        """Replace the content of the view named ``name``.

        Routes to ``set_items`` for a :class:`~tui.views.select.SelectView`
        (whose data is a list of rows) and to ``set_content`` for every other
        view.  Raises ``KeyError`` if no view has that name."""
        view = self.get(name)
        if view is None:
            raise KeyError("no view named %r" % name)
        if hasattr(view, "set_items"):
            view.set_items(content)
        elif hasattr(view, "set_content"):
            view.set_content(content)
        else:
            raise TypeError("view %r has no settable content" % name)

    # --- key bindings --------------------------------------------------------
    def bind(self, key_spec, callback):
        """Bind a key (``"Ctrl+c"``, ``"Alt+p"``, ``"UP"``, ...) to a zero-arg
        ``callback`` invoked when that key is pressed and no modal view is
        capturing input.  Can be called at runtime; binding an already-bound
        key replaces its callback.  Returns the parsed :class:`~tui.keys.Key`."""
        key = to_key(key_spec)
        if key is None:
            raise ValueError("cannot bind an empty key")
        self.bindings[key] = callback
        return key

    def unbind(self, key_spec):
        """Remove a previously-bound key.  Returns ``True`` if a binding was
        removed, ``False`` if the key was not bound."""
        return self.bindings.pop(to_key(key_spec), None) is not None

    # --- layout --------------------------------------------------------------
    def _layout(self):
        self.win_h, self.win_w = self.stdscr.getmaxyx()
        for v in self.views:
            v.attach(self.win_w, self.win_h)

    def _active_view(self):
        if self.focus is not None and self.focus.active:
            return self.focus
        for v in self.views:
            if v.active:
                return v
        return None

    # --- drawing -------------------------------------------------------------
    def _draw(self):
        self.stdscr.erase()
        self.stdscr.noutrefresh()
        for v in self.views:
            v.draw()
            v.noutrefresh()
        active = self._active_view()
        if active is not None:
            try:
                curses.curs_set(2)          # solid block cursor
            except curses.error:
                pass
            active.place_cursor()
            active.noutrefresh()            # last refresh wins the cursor
        else:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        curses.doupdate()

    # --- routing -------------------------------------------------------------
    def _dispatch(self, key):
        if self.focus is not None:
            self.focus.handle_key(key)
            if not self.focus.active:
                self.focus = None
            return
        for v in self.views:
            if v.handle_key(key):
                if v.active:
                    self.focus = v
                break

    # --- run loop ------------------------------------------------------------
    def run(self):
        curses.wrapper(self._run)

    def _run(self, stdscr):
        self.stdscr = stdscr
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        try:
            curses.start_color()
            curses.use_default_colors()
        except curses.error:
            pass
        formatting.reset_registry()
        stdscr.keypad(True)
        curses.raw()                        # deliver Ctrl+C/Ctrl+Q as keys
        if hasattr(curses, "set_escdelay"):
            curses.set_escdelay(25)         # snappy Alt/Esc disambiguation
        self._layout()

        self._running = True
        while self._running:
            self._draw()
            try:
                key = self.kb.read(stdscr)
            except (curses.error, KeyboardInterrupt):
                continue
            if key is None:
                continue
            if key.name == RESIZE:
                self._layout()
                continue
            # Global quit only when no modal view is capturing input.
            if (self.quit_key is not None and key == self.quit_key
                    and self.focus is None):
                break
            # Global key bindings, likewise suppressed while a modal view has
            # focus (so they don't fire mid-typing).  A match is consumed here
            # and not routed on to the views.
            if self.focus is None and key in self.bindings:
                self.bindings[key]()
                continue
            self._dispatch(key)

    def stop(self):
        self._running = False
