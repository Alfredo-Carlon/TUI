"""WindowCreator -- parse a text layout spec and generate a Window subclass.

Spec format (``#`` starts a comment line; blank lines ignored)::

    <TextView>
    name: banner
    origin: (W/2, H-2)
    width: W/4
    height: 1
    content: "Made with Love by Claude"
    format: Red | Bold | Blink
    </TextView>

``W`` and ``H`` are the terminal width/height and may appear in arithmetic
expressions in ``origin`` / ``width`` / ``height``.  Those expressions are
validated with a *restricted* AST walker (only ``W``, ``H``, integer constants
and ``+ - * / %`` are allowed -- no attribute access, calls, or names) and then
emitted into the generated file as runtime expressions, so the generated Window
computes real coordinates from the actual terminal size.  ``/`` is emitted as
integer ``//`` since screen coordinates are whole cells.

A callback value such as ``handler.trace_selected`` names a *handler object*
(``handler``) and a method on it (``trace_selected``).  The generated Window
requires each distinct handler object as a constructor argument and wires its
methods onto the views via ``set_handler``, which can be called again at run
time to swap a handler.  Data views whose content the spec leaves blank
(``ScrollView`` content, ``SelectView`` items) start empty and are populated at
run time with ``Window.set_content(name, value)`` -- they are never required
constructor arguments.  The generated module also carries an
``if __name__ == "__main__"`` demo runner wired to stub handlers, with ``TODO``
comments marking what to bind.

A JSON spec is also accepted: a top-level array whose objects each describe one
view.  A ``"type"`` key names the view type (``TextView``, ``SeparatorView``,
...) and the remaining keys are its fields, mirroring the tag-based format::

    [{"type": "TextView", "name": "banner", "origin": "(W/2, H-2)",
      "width": "W/4", "height": 1, "content": "Made with Love by Claude",
      "format": "Red | Bold | Blink"}]

Field values may use JSON-native types: a number or a ``W``/``H`` expression
string for ``origin``/``width``/``height``, a ``[x, y]`` array for ``origin``,
and an array of strings for ``SelectView`` items.  ``parse_spec`` auto-detects
JSON (input whose first non-space character is ``[``) versus the tag format.

An optional ``Window`` block configures the window itself rather than a view.
It accepts ``exit`` -- the keystroke that quits the window, overriding the
``quit_key`` passed to ``WindowCreator`` -- and any number of ``bind`` lines of
the form ``KEY --> handler.method`` that bind a global key to a handler method.
A binding is wired exactly like a view callback: ``handler`` names a callback
object required at construction time (distinct names mean distinct objects),
and the method is invoked (with no arguments) when the key is pressed::

    <Window>
    exit: Ctrl + q
    bind: Ctrl+f --> window_handler.fold
    bind: Alt+p  --> window_handler.print
    </Window>

The JSON form is an object with ``"type": "Window"``; its ``bind`` value is a
single ``"KEY --> handler.method"`` string or a list of them, e.g.
``{"type": "Window", "exit": "Ctrl+q", "bind": ["Ctrl+f --> h.fold"]}``.
"""

import ast
import json
import re

_BLOCK_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)

VIEW_TYPES = ("TextView", "ScrollView", "SelectView", "InputView", "SeparatorView")

# The special, non-view block that configures the window itself, and the config
# fields it understands (mapped to a human note used only in error messages).
WINDOW_TYPE = "Window"
_WINDOW_KEYS = {"exit": "quit keystroke", "bind": "key binding"}

# AST node types permitted inside a W/H expression.
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.USub, ast.UAdd,
)


class _DivToFloor(ast.NodeTransformer):
    """Rewrite ``/`` as ``//`` -- screen coordinates are integer cells."""

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Div):
            node.op = ast.FloorDiv()
        return node


def compile_expr(expr):
    """Validate a ``W``/``H`` arithmetic expression and return safe Python
    source using integer division.  Raises ``ValueError`` on anything else.
    A non-string ``expr`` (e.g. a JSON number) is stringified first."""
    tree = ast.parse(str(expr), mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in ("W", "H"):
                raise ValueError("only W and H are allowed, got %r" % node.id)
        elif not isinstance(node, _ALLOWED_NODES):
            raise ValueError("disallowed element %s in %r"
                             % (type(node).__name__, expr))
    tree = _DivToFloor().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree.body)


def parse_origin(value):
    """Split an ``(x, y)`` origin into two validated expression sources.
    Accepts either the ``"(x, y)"`` string form or a two-element ``[x, y]``
    array (as a JSON spec may supply), each element itself an expression."""
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise ValueError("origin must be a pair, got %r" % (value,))
        return compile_expr(value[0]), compile_expr(value[1])
    v = value.strip()
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1]
    if "," not in v:
        raise ValueError("origin must be a pair, got %r" % value)
    x, y = v.split(",", 1)
    return compile_expr(x.strip()), compile_expr(y.strip())


def _literal(value):
    """Interpret a raw spec value.  A non-string value (e.g. a number or list
    from a JSON spec) is already a literal and returned unchanged.  A string is
    trimmed and, if wrapped in matching quotes, unquoted (processing escapes
    like ``\\u21A0`` via ``literal_eval``)."""
    if not isinstance(value, str):
        return value
    v = value.strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v[1:-1]
    return v


def parse_spec(text):
    """Parse a layout spec into a list of ``(view_type, fields)`` tuples,
    auto-detecting the format: a spec whose first non-space character is ``[``
    is read as JSON, otherwise as the tag-based text format."""
    if text.lstrip().startswith("["):
        return parse_json_spec(text)
    return parse_text_spec(text)


def parse_text_spec(text):
    """Parse the tag-based text spec into a list of ``(view_type, fields)``
    tuples."""
    blocks = []
    for match in _BLOCK_RE.finditer(text):
        vtype = match.group(1)
        fields = {}
        for raw in match.group(2).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            # ``bind`` may appear repeatedly (one global binding each), so it
            # accumulates into a list; every other key is single-valued.
            if key == "bind":
                fields.setdefault(key, []).append(val)
            else:
                fields[key] = val
        blocks.append((vtype, fields))
    return blocks


def parse_json_spec(text):
    """Parse a JSON spec into a list of ``(view_type, fields)`` tuples.  The
    top level is an array of view objects; each object's ``"type"`` names the
    view and its remaining keys are the view's fields (kept as their native
    JSON types)."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("JSON spec must be a top-level array of views")
    blocks = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each JSON view must be an object, got %s"
                             % type(item).__name__)
        if "type" not in item:
            raise ValueError('JSON view is missing required "type": %r' % (item,))
        fields = {k: v for k, v in item.items() if k != "type"}
        blocks.append((item["type"], fields))
    return blocks


def resolve_callback(handlers, path):
    """Resolve a dotted ``path`` (e.g. ``handler.trace_selected``) against the
    ``handlers`` object.  Tries the full path, then the path minus its first
    segment (the spec's leading name is conventionally the handler object), then
    a dict lookup.  Returns ``None`` if unresolvable."""
    if handlers is None or not path:
        return None
    parts = path.split(".")
    for start in (0, 1):
        obj = handlers
        ok = True
        for p in parts[start:]:
            try:
                obj = getattr(obj, p)
            except AttributeError:
                ok = False
                break
        if ok and parts[start:]:
            return obj
    if isinstance(handlers, dict) and path in handlers:
        return handlers[path]
    return None


def resolve_handler_method(handler, path):
    """Resolve dotted ``path`` (e.g. ``trace_selected`` or ``sub.on_click``)
    against a single ``handler`` object and return the bound callable.

    Returns ``None`` when ``handler`` is ``None``, the attribute chain is
    missing, or the resolved attribute is not callable.  Views treat a ``None``
    callback as "ignore the action", so an unbound (or partially bound) handler
    makes the corresponding action inert instead of raising -- and because the
    generated window resolves methods through this helper every time a handler
    is (re)bound, swapping a handler at runtime takes effect immediately."""
    if handler is None or not path:
        return None
    obj = handler
    for part in path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if callable(obj) else None


def _normalize_key(spec):
    """Tidy a key spec such as ``"Ctrl + q"`` into the canonical ``"Ctrl+q"``
    form by trimming whitespace around the ``+`` joints, so specs written with
    spaces still parse.  Non-strings are returned unchanged."""
    if not isinstance(spec, str):
        return spec
    return "+".join(part.strip() for part in spec.split("+"))


def _ident(text):
    """Turn ``text`` into a safe Python identifier for a generated parameter."""
    safe = re.sub(r"\W", "_", text)
    if not safe or safe[0].isdigit():
        safe = "_" + safe
    return safe


# Per-view mapping of spec keys to constructor kwargs for plain (string) values.
_STRING_FIELDS = {
    "TextView": [("content", "content"), ("format", "format")],
    "SeparatorView": [("content", "content"), ("format", "format")],
    "ScrollView": [
        ("format", "format"),
        ("scroll-up", "scroll_up"), ("scroll-down", "scroll_down"),
        ("scroll-left", "scroll_left"), ("scroll-right", "scroll_right"),
    ],
    "SelectView": [
        ("menu-normal", "fmt_normal"), ("menu-highlighted", "fmt_highlight"),
        ("select-font", "fmt_selected"), ("menu-up", "key_up"),
        ("menu-down", "key_down"), ("select-item", "key_select"),
        ("scroll-left", "key_left"), ("scroll-right", "key_right"),
    ],
    "InputView": [
        ("content", "content"), ("activate", "activate"),
        ("deactivate", "deactivate"), ("format", "format"),
        ("success-format", "fmt_success"), ("failure-format", "fmt_failure"),
    ],
}

# Per-view mapping of spec keys to callback kwargs.  These are *not* baked into
# the view constructor call: each one names a method on a handler object that is
# required by the generated ``__init__`` and wired (and re-wired) by
# ``set_handler`` so the handler can be swapped at runtime.
_CALLBACK_FIELDS = {
    "SelectView": [("select-callback", "on_select"),
                   ("deselect-callback", "on_deselect"),
                   ("on-item-callback", "on_item")],
    "InputView": [("callback", "on_submit")],
}

# View types whose *data* content is filled at runtime rather than at build
# time: the view kwarg that carries it, and a short human description of its
# Python type.  When the spec provides the field its literal is baked in; when
# it is omitted the view keeps its own empty default and is populated later via
# ``Window.set_content(name, value)`` -- never a required constructor argument.
_CONTENT_PARAM = {
    "ScrollView": ("content", "str"),
    "SelectView": ("items", "list[str]"),
}


def _split_callback(path):
    """Split ``handler.trace_selected`` into ``("handler", "trace_selected")``.

    The first dotted segment names the *handler object* the constructor will
    require; the remainder is the method path resolved against it.  A bare name
    with no dot is treated as a method on the conventional ``handler`` object."""
    head, sep, tail = path.partition(".")
    if not sep:
        return "handler", path
    return head, tail


def _split_binding(spec):
    """Parse a window binding ``"Ctrl+f --> handler.method"`` into the triple
    ``(key_spec, handler_name, method)``.  The key is normalized (so spaces
    around ``+`` are fine) and the callback path is split like any other
    handler callback.  Raises ``ValueError`` if the ``-->`` separator, the key,
    or the callback path is missing."""
    if "-->" not in spec:
        raise ValueError("window binding must be 'KEY --> handler.method', "
                         "got %r" % (spec,))
    key_part, path_part = spec.split("-->", 1)
    key = _normalize_key(key_part.strip())
    path = path_part.strip()
    if not key:
        raise ValueError("window binding is missing a key: %r" % (spec,))
    if not path:
        raise ValueError("window binding is missing a callback: %r" % (spec,))
    hname, method = _split_callback(path)
    return key, hname, method


def _as_binding_list(raw):
    """Normalize a ``bind`` field value into a list of binding spec strings.
    Accepts a single string or a list/tuple of strings (a JSON spec may supply
    either; the text parser always supplies a list)."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return list(raw)
    raise ValueError("window 'bind' must be a string or a list of strings, "
                     "got %s" % type(raw).__name__)


class WindowCreator:
    def __init__(self, class_name="GeneratedWindow", quit_key="Ctrl+c"):
        self.class_name = class_name
        self.quit_key = quit_key

    def parse(self, text):
        return parse_spec(text)

    # --- spec analysis -------------------------------------------------------
    def _extract_window_config(self, blocks):
        """Split the optional ``Window`` config block(s) out of ``blocks``.

        Returns ``(quit_key, bindings, view_blocks)``.  The window's exit
        keystroke defaults to this creator's ``quit_key`` and is overridden by
        an ``exit`` field; ``bindings`` is the list of ``(key, handler_name,
        method)`` triples parsed from the ``bind`` field(s).  Raises
        ``ValueError`` on more than one ``Window`` block or an unrecognized
        config key."""
        quit_key = self.quit_key
        bindings = []
        views = []
        seen = False
        for vtype, fields in blocks:
            if vtype != WINDOW_TYPE:
                views.append((vtype, fields))
                continue
            if seen:
                raise ValueError("only one %s config block is allowed"
                                 % WINDOW_TYPE)
            seen = True
            for key in fields:
                if key not in _WINDOW_KEYS:
                    raise ValueError("unknown %s config key: %s"
                                     % (WINDOW_TYPE, key))
            if "exit" in fields:
                quit_key = _normalize_key(_literal(fields["exit"]))
            if "bind" in fields:
                for item in _as_binding_list(fields["bind"]):
                    bindings.append(_split_binding(item))
        return quit_key, bindings, views

    @staticmethod
    def _view_name(fields):
        return _literal(fields.get("name", "")) or "view"

    def _analyze(self, blocks):
        """Walk the parsed blocks once, collecting everything code emission
        needs: per-view content bindings, the ordered list of distinct handler
        objects, the callback wiring table, and the required content params."""
        handler_names = []           # ordered, distinct handler-object names
        callbacks = []               # (view_name, kwarg, handler_name, method)
        content_todos = []           # (view_name, kwarg, type_desc) left blank
        view_infos = []              # (vtype, fields, content_binding)

        for vtype, fields in blocks:
            if vtype not in VIEW_TYPES:
                raise ValueError("unknown view type: %s" % vtype)
            vname = self._view_name(fields)

            for spec_key, kwarg in _CALLBACK_FIELDS.get(vtype, []):
                if spec_key in fields:
                    hname, method = _split_callback(fields[spec_key].strip())
                    callbacks.append((vname, kwarg, hname, method))
                    if hname not in handler_names:
                        handler_names.append(hname)

            binding = {}
            if vtype in _CONTENT_PARAM:
                kwarg, type_desc = _CONTENT_PARAM[vtype]
                if kwarg in fields:
                    binding[kwarg] = ("literal", _literal(fields[kwarg]))
                else:
                    # Left to the view's empty default; fill via set_content.
                    content_todos.append((vname, kwarg, type_desc))

            view_infos.append((vtype, fields, binding))

        return view_infos, handler_names, callbacks, content_todos

    # --- code emission -------------------------------------------------------
    def _emit_view(self, vtype, fields, binding):
        parts = ["name=%r" % self._view_name(fields)]

        ox, oy = parse_origin(fields["origin"])
        parts.append("origin=(%s, %s)" % (ox, oy))
        parts.append("width=%s" % compile_expr(fields["width"]))
        parts.append("height=%s" % compile_expr(fields["height"]))

        for kwarg, (kind, value) in binding.items():
            parts.append("%s=%r" % (kwarg, value))           # baked literal
        for spec_key, kwarg in _STRING_FIELDS.get(vtype, []):
            if spec_key in fields:
                parts.append("%s=%r" % (kwarg, _literal(fields[spec_key])))
        # Callbacks are intentionally left unset here; set_handler wires them.
        return "        self.add(%s(%s))" % (vtype, ", ".join(parts))

    def _emit_docstring(self, handler_names, callbacks, bindings, content_todos):
        lines = ['    """Window generated from a layout spec.', ""]
        if handler_names:
            lines.append("    Required handler objects (constructor arguments) --")
            lines.append("    each must provide the listed method(s):")
            for hname in handler_names:
                lines.append("      %s:" % hname)
                for vname, kwarg, h, method in callbacks:
                    if h == hname:
                        lines.append("        .%s(value)   # %s of view %r"
                                     % (method, kwarg, vname))
                for key_spec, h, method in bindings:
                    if h == hname:
                        lines.append("        .%s()   # bound to key %r"
                                     % (method, key_spec))
            lines.append("")
        if content_todos:
            lines.append("    These views start empty; populate them at runtime")
            lines.append("    with set_content(name, value):")
            for vname, kwarg, type_desc in content_todos:
                lines.append("      %r: %s   # %s" % (vname, type_desc, kwarg))
            lines.append("")
        lines.append("    At runtime, set_content(name, value) updates a view's")
        lines.append("    content and set_handler(name, obj) swaps a handler.")
        lines.append('    """')
        return lines

    def _emit_set_handler(self):
        return [
            "    def set_handler(self, name, handler):",
            '        """Bind or replace the handler object *name* and (re)wire',
            "        every view callback and window key binding that references",
            "        it.  Safe to call at runtime; a method that will not resolve",
            "        leaves the view callback unset (its action ignored) and the",
            '        key binding removed, rather than raising."""',
            "        self._handlers[name] = handler",
            "        for view_name, attr, hname, method in self._CALLBACKS:",
            "            if hname != name:",
            "                continue",
            "            view = self.get(view_name)",
            "            if view is not None:",
            "                setattr(view, attr,",
            "                        resolve_handler_method(handler, method))",
            "        for key_spec, hname, method in self._BINDINGS:",
            "            if hname != name:",
            "                continue",
            "            bound = resolve_handler_method(handler, method)",
            "            if bound is not None:",
            "                self.bind(key_spec, bound)",
            "            else:",
            "                self.unbind(key_spec)",
        ]

    def _emit_main(self, handler_names, callbacks, bindings, content_todos):
        lines = [
            'if __name__ == "__main__":',
            "    # -----------------------------------------------------------------",
            "    # Demo runner.  REPLACE the stubs below with your real bindings",
            "    # before using this window for anything real.",
            "    # -----------------------------------------------------------------",
        ]
        for hname in handler_names:
            stub = "_Stub_%s" % _ident(hname)
            lines.append("    class %s:" % stub)
            # Method name (first dotted segment) -> TODO note, from both view
            # callbacks and window bindings, deduped so a method used more than
            # once is emitted only once.
            todo = {}
            for vname, kwarg, h, method in callbacks:
                if h == hname:
                    todo.setdefault(method.split(".")[0],
                                    "%s of view %r" % (kwarg, vname))
            for key_spec, h, method in bindings:
                if h == hname:
                    todo.setdefault(method.split(".")[0],
                                    "bound to key %r" % (key_spec,))
            if not todo:
                lines.append("        pass")
            for top, note in todo.items():
                lines.append("        def %s(self, *args):   # TODO: %s"
                             % (top, note))
                lines.append("            pass")
            lines.append("")
        lines.append("    window = %s(" % self.class_name)
        for hname in handler_names:
            lines.append("        %s=_Stub_%s(),   # TODO: bind your real %r handler"
                         % (hname, _ident(hname), hname))
        lines.append("    )")
        for vname, kwarg, type_desc in content_todos:
            default = "[]" if type_desc.startswith("list") else '""'
            lines.append("    window.set_content(%r, %s)   # TODO: %s"
                         % (vname, default, kwarg))
        lines.append("    window.run()")
        return lines

    def generate(self, text):
        """Return the Python source for a Window subclass built from ``text``."""
        blocks = parse_spec(text)
        quit_key, bindings, view_blocks = self._extract_window_config(blocks)
        view_infos, handler_names, callbacks, content_todos = \
            self._analyze(view_blocks)
        # Window bindings may reference handler objects not used by any view;
        # add them so they are required constructor args and get stubs too.
        for key_spec, hname, method in bindings:
            if hname not in handler_names:
                handler_names.append(hname)

        signature = "self"
        if handler_names:
            signature += ", " + ", ".join(handler_names)
        signature += ", quit_key=%r" % quit_key

        out = [
            "# Auto-generated by tui.WindowCreator. Do not edit by hand.",
            "import shutil",
            "",
            "from tui import (Window, TextView, ScrollView, SelectView,",
            "                 InputView, SeparatorView)",
            "from tui.creator import resolve_handler_method",
            "",
            "",
            "class %s(Window):" % self.class_name,
        ]
        out += self._emit_docstring(handler_names, callbacks, bindings,
                                    content_todos)
        out.append("")
        out.append("    _CALLBACKS = (")
        for vname, kwarg, hname, method in callbacks:
            out.append("        (%r, %r, %r, %r)," % (vname, kwarg, hname, method))
        out.append("    )")
        out.append("")
        out.append("    _BINDINGS = (")
        for key_spec, hname, method in bindings:
            out.append("        (%r, %r, %r)," % (key_spec, hname, method))
        out.append("    )")
        out.append("")
        out.append("    def __init__(%s):" % signature)
        out.append("        super().__init__(quit_key=quit_key)")
        out.append("        W, H = shutil.get_terminal_size((80, 24))")
        out.append("        self._handlers = {}")
        if not view_infos:
            out.append("        pass")
        for vtype, fields, binding in view_infos:
            out.append(self._emit_view(vtype, fields, binding))
        for hname in handler_names:
            out.append("        self.set_handler(%r, %s)" % (hname, hname))
        out.append("")
        out += self._emit_set_handler()
        out.append("")
        out.append("")
        out += self._emit_main(handler_names, callbacks, bindings,
                               content_todos)
        out.append("")
        return "\n".join(out)

    def generate_source(self, source_text):
        """Alias for :meth:`generate` -- generate a Window from spec *text*."""
        return self.generate(source_text)

    def write(self, spec_path, out_path):
        """Read a layout spec from ``spec_path``, generate the Window source,
        write it to ``out_path``, and return the generated source.

        Note both arguments are *file paths*.  To generate from an in-memory
        spec string instead, call :meth:`generate` directly."""
        with open(spec_path) as handle:
            spec_text = handle.read()
        source = self.generate(spec_text)
        with open(out_path, "w") as handle:
            handle.write(source)
        return source
