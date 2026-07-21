"""Pure coordinate math bridging the user's lower-left origin system and curses.

User coordinate system (per the design):
    (0, 0)   -> lower-left corner of a region
    (W, H)   -> upper-right corner
    x grows rightward, y grows *upward*.

curses coordinate system:
    (0, 0)   -> upper-left corner
    addressed as (row, col); row grows *downward*.

Every function here is pure -- no curses calls -- so the arithmetic can be
reasoned about and checked without a live terminal.  This module is where the
single most bug-prone part of the toolkit (the vertical flip) lives, isolated.
"""


def view_top_row(win_height, oy, height):
    """curses row of a view's top edge.

    A view's origin ``(ox, oy)`` is its lower-left corner in window coords.
    Its top edge sits ``height - 1`` rows above ``oy`` counting from the
    bottom, i.e. at ``y = oy + height - 1``.  Converting that to a distance
    from the top of a ``win_height``-row screen::

        top_row = (win_height - 1) - (oy + height - 1)
                = win_height - oy - height
    """
    return win_height - oy - height


def local_to_curses(height, lx, ly):
    """Map a view-local point ``(lx, ly)`` (``ly`` measured from the bottom)
    to a curses ``(row, col)`` *inside* that view's own window."""
    return (height - 1 - ly, lx)


def fits(win_width, win_height, ox, oy, width, height):
    """True if a view at ``(ox, oy)`` sized ``width x height`` fits fully."""
    if width <= 0 or height <= 0:
        return False
    if ox < 0 or oy < 0:
        return False
    if ox + width > win_width:
        return False
    if oy + height > win_height:
        return False
    return True


def clamp(value, low, high):
    """Clamp ``value`` into ``[low, high]``.  If ``high < low`` returns ``low``
    (used when the scrollable extent is smaller than the viewport)."""
    if high < low:
        return low
    if value < low:
        return low
    if value > high:
        return high
    return value
