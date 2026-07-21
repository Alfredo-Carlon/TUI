# =============================================================================
# spec_example.spec
# -----------------------------------------------------------------------------
# A fully-commented reference for the tui layout-spec format consumed by
# tui.WindowCreator.  Generate a Window subclass from a spec like this with:
#
#     from tui import WindowCreator
#     src = WindowCreator(class_name="MyWindow").generate(open("x.spec").read())
#     # or write straight to a file:
#     WindowCreator().write("x.spec", "my_window.py")
#
# This file is itself a valid spec -- feeding it to WindowCreator produces a
# compilable Window with one of every view type.
#
# TWO IMPORTANT PARSER RULES, worth knowing before reading on:
#   1. Comments must be on their OWN line, starting with '#'.  There are NO
#      trailing/inline comments -- everything after the first ':' on a setting
#      line is part of the value.
#   2. The parser scans the whole file for angle-bracket tags, so the view-type
#      tags in these comments are written WITHOUT angle brackets (e.g. "TextView
#      block") on purpose; a real-looking tag pair inside a comment would be
#      parsed as an actual block.  The concrete blocks below show real syntax.
# =============================================================================
#
# ----------------------------------------------------------------------------
# FILE FORMAT
# ----------------------------------------------------------------------------
# * A spec is a sequence of blocks.  Each block opens with a tag naming a view
#   type -- the name wrapped in angle brackets -- and closes with the matching
#   slash tag (see the real blocks below for the exact syntax).
# * Inside a block, each setting is one  "key: value"  line.
# * Comment lines start with '#'.  Blank lines are ignored.  Any text OUTSIDE
#   a block (like this header) is ignored entirely, so prose between blocks is
#   free.
# * A line with no ':' inside a block is ignored.
# * The FIRST ':' splits key from value, so values may contain ':' freely.
#
# JSON ALTERNATIVE
# * WindowCreator also accepts a JSON spec: a top-level array whose objects each
#   describe one block.  A "type" key names the block ("TextView", "Window",
#   ...) and the remaining keys are its fields.  Auto-detected when the input's
#   first non-space character is '['.  Example:
#       [{"type": "TextView", "name": "t", "origin": "(0,0)",
#         "width": "W", "height": 1, "content": "hi"}]
#   JSON may use native types: numbers for width/height, a [x, y] array for
#   origin, and a real list for SelectView "items".
#
# ----------------------------------------------------------------------------
# COORDINATES & SIZES  (origin / width / height -- required on every view)
# ----------------------------------------------------------------------------
# * origin is the LOWER-LEFT corner as "(x, y)"; y counts up from the bottom.
# * origin/width/height accept arithmetic expressions over the terminal size:
#       W = terminal width, H = terminal height.
#   Allowed: W, H, integer literals, and + - * / %  (and parentheses).
#   '/' is emitted as INTEGER division (screen cells are whole).
#   Nothing else is permitted (no other names, calls, or attribute access).
#   Examples:  origin: (0, 0)   origin: (W/2, H-2)   width: W/4   height: 1
#
# ----------------------------------------------------------------------------
# FORMAT SPECS  (any "...format...", "menu-*", "select-font" value)
# ----------------------------------------------------------------------------
# Space/'|'-separated, case-insensitive tokens.  Unknown tokens are ignored.
#   Colors:     black red green yellow blue magenta (=purple) cyan white
#               default (=none)
#   Foreground: the first color named.  Background: "on <color>" or a 2nd color.
#   Intensity:  "bright" or "light" before a color -> high-intensity variant.
#   Attributes: bold dim reverse standout underline (=under) blink
#               invisible (=invis) italic normal
#   Examples:   "Red | Bold"   "bold green"   "white on blue"
#               "bright cyan | underline"   "reverse"
#
# ----------------------------------------------------------------------------
# KEY SPECS  (activate/deactivate, menu-up, scroll-*, exit, bind, ...)
# ----------------------------------------------------------------------------
# * Modifiers:  Ctrl+  Alt+   (case-insensitive; Control/Meta/Option accepted).
#               Combine like  Ctrl+Alt+x.  Spaces around '+' are tolerated.
# * Named keys: UP DOWN LEFT RIGHT ENTER BACKSPACE DELETE INSERT TAB HOME END
#               PAGEUP PAGEDOWN ESC SPACE F1..F24  (plus aliases: return, ret,
#               cr, escape, bksp, bs, del, ins, spc, pgup, pgdn, ...).
# * Single characters: a  Z  7  ?   (case matters for plain keys; Ctrl folds
#   case, so Ctrl+a == Ctrl+A).
# * Examples:  Ctrl+c   Alt+p   Ctrl+Alt+x   UP   Enter   F5   /
#
# ----------------------------------------------------------------------------
# CALLBACKS & HANDLER OBJECTS
# ----------------------------------------------------------------------------
# * A callback value is  object.method  (dotted).  "object" names a handler
#   object that the generated Window REQUIRES as a constructor argument; the
#   method is looked up on it at runtime.  A bare "method" (no dot) uses the
#   conventional handler object named "handler".
# * Distinct object names mean distinct required objects.  Handlers are wired
#   (and re-wired) via  window.set_handler(name, obj)  so they can be swapped
#   at runtime; an unresolved method leaves the action inert instead of raising.
#
# ----------------------------------------------------------------------------
# RUNTIME-FILLED DATA
# ----------------------------------------------------------------------------
# * A ScrollView's "content" and a SelectView's "items" hold DATA.  In the text
#   format they are normally OMITTED here and populated at runtime with
#       window.set_content("<name>", value)
#   The generated window's docstring lists every view left to fill this way.
#   (In a JSON spec you may instead bake a literal: a string for content, a
#   real list for items.)
#
# =============================================================================
# THE Window BLOCK  (optional; configures the window itself, not a view)
# =============================================================================
<Window>
    # exit: the keystroke that quits the window.  Overrides WindowCreator's
    # quit_key (which itself defaults to Ctrl+c).  Optional.
    exit: Ctrl+q

    # bind: a global key binding "KEY --> object.method".  May appear any number
    # of times; each binds a key (active whenever no modal InputView is focused)
    # to a zero-argument handler method, wired like any other callback.
    bind: Ctrl+f --> window_handler.find
    bind: Alt+p --> window_handler.toggle_preview
</Window>

# =============================================================================
# TextView -- a static (optionally multi-line) label.
# =============================================================================
<TextView>
    # name (optional): used by window.get() / set_content() / set_handler().
    name: banner
    # origin / width / height: required on every view (see COORDINATES above).
    origin: (W/2, H-2)
    width: W/4
    height: 1
    # content: the text to display.
    content: Made with Love by Claude
    # format (optional): a format spec (see FORMAT SPECS above).
    format: Red | Bold | Blink
</TextView>

# =============================================================================
# SeparatorView -- a rule/fill that tiles a string across its extent.
# =============================================================================
<SeparatorView>
    name: rule
    origin: (0, H-3)
    # A wide, 1-tall rule.
    width: W
    height: 1
    # content: the tile string (e.g. '-', '=', or a box-drawing glyph).
    content: =
    format: bright black
</SeparatorView>

# =============================================================================
# ScrollView -- a scrollable text region.
#   * Supply up/down keys for VERTICAL scrolling (text wraps to the width).
#   * Supply left/right keys for HORIZONTAL scrolling (no wrap).
#   * Supply both for both axes.  When vertical, up/down arrows appear at the
#     right edge to show that more text lies above/below.
# =============================================================================
<ScrollView>
    name: output
    origin: (0, 0)
    width: W/2
    height: H-4
    format: white
    # scroll-up / scroll-down (optional): enable vertical scrolling.
    scroll-up: UP
    scroll-down: DOWN
    # scroll-left / scroll-right (optional): enable horizontal scrolling.
    scroll-left: LEFT
    scroll-right: RIGHT
    # content is DATA: omitted here, filled at runtime via
    #   window.set_content("output", some_text)
</ScrollView>

# =============================================================================
# SelectView -- a navigable menu with highlight and multi-selection.
#   Navigation is circular by default (wraps past either end).  Entries can be
#   made "transparent" (shown only while highlighted) at runtime via
#   view.set_transparent(index) / view.set_solid(index).
# =============================================================================
<SelectView>
    name: menu
    origin: (W/2, 0)
    width: W/2
    height: H-4
    # menu-normal: format for ordinary rows.
    menu-normal: white
    # menu-highlighted: format for the highlighted row (default "reverse").
    menu-highlighted: reverse
    # select-font: format for selected rows (default "bold").
    select-font: bold green
    # menu-up / menu-down: move the highlight (defaults UP / DOWN).
    menu-up: UP
    menu-down: DOWN
    # select-item: key that toggles selection of the highlighted row.
    select-item: SPACE
    # scroll-left / scroll-right (optional): horizontal scrolling.
    scroll-left: LEFT
    scroll-right: RIGHT
    # select-callback: fired when a row is toggled ON.
    select-callback: menu_handler.on_select
    # deselect-callback: fired when a row is toggled OFF.
    deselect-callback: menu_handler.on_deselect
    # on-item-callback: fired whenever the highlight moves to a new entry.
    on-item-callback: menu_handler.on_highlight
    # items is DATA: omitted here, filled at runtime via
    #   window.set_content("menu", ["one", "two", "three"])
</SelectView>

# =============================================================================
# InputView -- a modal, multi-line text editor.
#   Inactive until the "activate" key is pressed; then it captures all input
#   until "deactivate", which submits the text to "callback".  The callback
#   returns True on success (text shown in success-format, then cleared on next
#   entry) or False on failure (shown in failure-format, text kept for editing).
# =============================================================================
<InputView>
    name: query
    origin: (0, H-1)
    width: W
    height: 1
    # content (optional): initial text (empty here).
    content:
    # activate: key that focuses/enters the editor.
    activate: Ctrl+e
    # deactivate: key that submits the text and leaves the editor.
    deactivate: Enter
    # format: the normal (editing) format.
    format: white on blue
    # success-format / failure-format: feedback after submit (defaults shown).
    success-format: bold green
    failure-format: bold red
    # callback: invoked with the full text; must return True/False.
    callback: query_handler.submit
</InputView>
