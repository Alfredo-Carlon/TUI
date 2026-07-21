"""SelectView -- a navigable list/menu with highlight, multi-selection and
per-state formatting.

* One string per row; a moving *cursor* highlights the current row.
* Moving the cursor with the up/down keys fires the ``on_item`` callback with
  the newly highlighted row's string (only when the highlight actually moves).
* A select keystroke toggles the row's membership in the selection set and
  fires the ``on_select`` / ``on_deselect`` callback with the row's string.
* The viewport follows the cursor when the list is taller than the view.
* Navigation is *circular* by default: moving up from the first entry wraps to
  the last and vice versa (pass ``circular=False`` to clamp at the ends).
* Horizontal scrolling is enabled only when left/right keystrokes are supplied.

Entries are either *solid* (the default) or *transparent*.  A solid entry is
always shown on its own row.  A transparent entry is shown only while it is
highlighted; each maximal run of consecutive transparent entries collapses to a
single display row -- blank when none of them is highlighted, otherwise showing
the highlighted one in place.  The cursor still steps through every underlying
entry, so moving within a transparent run keeps the highlight on the same row
(only the text changes), while moving to or from a solid entry moves the
highlight as usual.  Use :meth:`set_transparent` / :meth:`set_solid` to change
an entry's kind by index.
"""

from .base import View
from ..formatting import parse_format
from ..geometry import clamp
from ..keys import to_key


class SelectView(View):
    def __init__(self, name, origin, width, height, items=None,
                 fmt_normal="", fmt_highlight="reverse", fmt_selected="bold",
                 key_up="UP", key_down="DOWN", key_select=None,
                 key_left=None, key_right=None,
                 on_select=None, on_deselect=None, on_item=None, step=1,
                 circular=True):
        super().__init__(name, origin, width, height)
        self.circular = bool(circular)
        self.fmt_normal = fmt_normal
        self.fmt_highlight = fmt_highlight
        self.fmt_selected = fmt_selected
        self.k_up = to_key(key_up)
        self.k_down = to_key(key_down)
        self.k_select = to_key(key_select)
        self.k_left = to_key(key_left)
        self.k_right = to_key(key_right)
        self.on_select = on_select
        self.on_deselect = on_deselect
        self.on_item = on_item
        self.step = max(1, int(step))
        self.cursor = 0
        self.top = 0
        self.h_offset = 0
        self.selected = set()      # indices into self.items
        self.set_items(items or [])

    @property
    def horizontal(self):
        return self.k_left is not None or self.k_right is not None

    # --- data mutation -------------------------------------------------------
    def set_items(self, items):
        self.items = [str(x) for x in items]
        self.cursor = 0
        self.top = 0
        self.h_offset = 0
        self.selected = set()
        self.transparent = set()   # indices shown only while highlighted

    replace = set_items

    def clear(self):
        self.set_items([])

    def set_transparent(self, index):
        """Mark the entry at ``index`` *transparent*: shown only while it is
        highlighted, sharing one row with adjacent transparent entries.
        Out-of-range indices are ignored."""
        if 0 <= index < len(self.items):
            self.transparent.add(index)

    def set_solid(self, index):
        """Mark the entry at ``index`` *solid*: always shown on its own row.
        Out-of-range indices are ignored."""
        if 0 <= index < len(self.items):
            self.transparent.discard(index)

    def selected_items(self):
        return [self.items[i] for i in sorted(self.selected) if 0 <= i < len(self.items)]

    def curnt(self):
        """Return the currently highlighted item's string, or ``None`` when the
        list is empty."""
        if 0 <= self.cursor < len(self.items):
            return self.items[self.cursor]
        return None

    def curnt_idx(self):
        """Return the index of the currently highlighted item's string, or ``None``
        when the list is empty."""
        if 0 <= self.cursor < len(self.items):
            return self.cursor
        return None

    def select(self, index, notify=False):
        """Programmatically highlight the item at ``index`` (0-based).  The
        index is clamped into range and the viewport scrolls to keep it
        visible; an empty list leaves the highlight at 0.  ``on_item`` fires
        only when ``notify`` is true and the highlight actually moves to a
        different row -- matching key-driven movement."""
        previous = self.cursor
        self.cursor = int(index)
        self._clamp_view()
        if notify and self.items and self.cursor != previous and self.on_item:
            self.on_item(self.items[self.cursor])

    # --- display layout ------------------------------------------------------
    def _slots(self):
        """Lay the entries out into one slot per screen row: ``("solid", idx)``
        for an always-shown entry, and ``("gap", start, end)`` for a maximal run
        of transparent entries ``start..end`` that share a single row."""
        slots = []
        i, n = 0, len(self.items)
        while i < n:
            if i in self.transparent:
                j = i
                while j < n and j in self.transparent:
                    j += 1
                slots.append(("gap", i, j - 1))
                i = j
            else:
                slots.append(("solid", i))
                i += 1
        return slots

    def _cursor_slot(self, slots):
        """Index of the slot that currently holds the highlight."""
        for si, slot in enumerate(slots):
            if slot[0] == "solid":
                if slot[1] == self.cursor:
                    return si
            elif slot[1] <= self.cursor <= slot[2]:
                return si
        return 0

    # --- viewport ------------------------------------------------------------
    def _clamp_view(self):
        if not self.items:
            self.cursor = self.top = 0
            return
        self.cursor = clamp(self.cursor, 0, len(self.items) - 1)
        slots = self._slots()
        cur = self._cursor_slot(slots)
        if cur < self.top:
            self.top = cur
        elif cur >= self.top + self.height:
            self.top = cur - self.height + 1
        self.top = clamp(self.top, 0, max(0, len(slots) - self.height))

    # --- rendering -----------------------------------------------------------
    def _row_text(self, item):
        if self.horizontal:
            return item[self.h_offset:self.h_offset + self.width]
        return item[:self.width]

    def draw(self):
        self._erase()
        self._clamp_view()
        normal = parse_format(self.fmt_normal)
        slots = self._slots()
        visible = slots[self.top:self.top + self.height]
        for i, slot in enumerate(visible):
            ly = self.height - 1 - i
            if slot[0] == "solid":
                idx = slot[1]
                if idx == self.cursor:
                    attr = parse_format(self.fmt_highlight)
                elif idx in self.selected:
                    attr = parse_format(self.fmt_selected)
                else:
                    attr = normal
                text = self._row_text(self.items[idx])
            else:  # gap run: show the highlighted transparent entry, else blank
                start, end = slot[1], slot[2]
                if start <= self.cursor <= end:
                    attr = parse_format(self.fmt_highlight)
                    text = self._row_text(self.items[self.cursor])
                else:
                    attr = normal
                    text = ""
            # Pad so the highlight/reverse (or normal background) fills the row.
            self._addstr(0, ly, text.ljust(self.width), attr)

    # --- interaction ---------------------------------------------------------
    def _move(self, delta):
        """Move the cursor by ``delta`` entries and -- if the highlighted entry
        actually changed -- fire ``on_item`` with its string.  When ``circular``
        is set, stepping past either end wraps around; otherwise it clamps, so
        pressing into a boundary fires nothing."""
        n = len(self.items)
        if not n:
            self._clamp_view()
            return
        previous = self.cursor
        if self.circular:
            self.cursor = (self.cursor + delta) % n
        else:
            self.cursor += delta
        self._clamp_view()
        if self.cursor != previous and self.on_item:
            self.on_item(self.items[self.cursor])

    def _toggle(self):
        if not self.items:
            return
        idx = self.cursor
        item = self.items[idx]
        if idx in self.selected:
            # Ignore the action entirely when no deselect handler is bound.
            if not self.on_deselect:
                return
            self.selected.discard(idx)
            self.on_deselect(item)
        else:
            # Ignore the action entirely when no select handler is bound.
            if not self.on_select:
                return
            self.selected.add(idx)
            self.on_select(item)

    def handle_key(self, key):
        if self.k_up is not None and key == self.k_up:
            self._move(-self.step)
            return True
        if self.k_down is not None and key == self.k_down:
            self._move(self.step)
            return True
        if self.k_select is not None and key == self.k_select:
            self._toggle()
            return True
        if self.horizontal:
            longest = max((len(i) for i in self.items), default=0)
            max_x = max(0, longest - self.width)
            if self.k_left is not None and key == self.k_left:
                self.h_offset = clamp(self.h_offset - self.step, 0, max_x)
                return True
            if self.k_right is not None and key == self.k_right:
                self.h_offset = clamp(self.h_offset + self.step, 0, max_x)
                return True
        return False

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d.get("name", ""),
            origin=d["origin"],
            width=d["width"],
            height=d["height"],
            items=d.get("items"),
            fmt_normal=d.get("menu-normal", ""),
            fmt_highlight=d.get("menu-highlighted", "reverse"),
            fmt_selected=d.get("select-font", "bold"),
            key_up=d.get("menu-up", "UP"),
            key_down=d.get("menu-down", "DOWN"),
            key_select=d.get("select-item"),
            key_left=d.get("scroll-left"),
            key_right=d.get("scroll-right"),
            on_select=d.get("select-callback"),
            on_deselect=d.get("deselect-callback"),
            on_item=d.get("on-item-callback"),
            step=int(d.get("step", 1)),
            circular=d.get("circular", True),
        )
