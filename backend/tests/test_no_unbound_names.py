"""No function may read a name it never received.

Found in production, on the flagship surface: a customer asked Ally about a broken OJS
upgrade and got **"name 'runbooks' is not defined"** where the answer should have been.

`_handle_message_inner` read `runbooks` at two places. The outer `_handle_message` had it as
a local — but both are module-level functions, so there was no closure to inherit it from
and the name was simply unbound. It shipped in `585e9de` (26 July) and survived two weeks,
because nothing imports-and-calls that websocket path in the suite, and Python only raises
an unbound name at RUNTIME.

That is why this is a sweep and not one regression test. A NameError of this shape passes
import, passes review, and is a hard failure the first time a real person reaches the line.

**A noisy check gets switched off, so this one models Python's scoping properly**: nested
functions are visited in their own scope rather than against their parent's, and the walrus
operator, comprehension targets, lambda arguments and `match` captures all bind. My first
version handled none of those and reported thirty false positives — and, worse, its scope
collector walked into nested bodies, which made it MISS the real bug it was written for.
Both self-tests below exist because of that.
"""
from __future__ import annotations

import ast
import builtins
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
_BUILTINS = set(dir(builtins))

#: A nested function or class starts a scope of its own; it is visited separately.
_NESTED_SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _arg_names(args: ast.arguments) -> set[str]:
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _own_nodes(node: ast.AST):
    """This scope's own nodes — everything except a nested function or class BODY.

    A comprehension and a lambda technically have scopes of their own; they are folded into
    the enclosing one here, with their targets and arguments treated as bound. That is not
    exactly Python, but it is sound for what this checks: it can never invent a missing
    name, only decline to report one.
    """
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, _NESTED_SCOPE):
            yield from _own_nodes(child)


def _bindings(node: ast.AST) -> set[str]:
    """Every name THIS scope binds."""
    names: set[str] = set()
    args = getattr(node, "args", None)
    if isinstance(args, ast.arguments):
        names |= _arg_names(args)

    for child in _own_nodes(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            names.add(child.id)
        elif isinstance(child, _NESTED_SCOPE):
            names.add(child.name)               # the def binds its own name here
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            names.update(child.names)
        elif isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
            names.add(child.target.id)          # walrus
        elif isinstance(child, ast.Lambda):
            names |= _arg_names(child.args)
        elif isinstance(child, ast.comprehension):
            names |= {n.id for n in ast.walk(child.target) if isinstance(n, ast.Name)}
        elif isinstance(child, ast.MatchAs) and child.name:
            names.add(child.name)
        elif isinstance(child, ast.MatchStar) and child.name:
            names.add(child.name)
        elif isinstance(child, ast.MatchMapping) and child.rest:
            names.add(child.rest)
    return names


def _reads(node: ast.AST) -> list[ast.Name]:
    """Names this scope READS, not counting what its nested functions read."""
    return [n for n in _own_nodes(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]


def _unbound_reads(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    module_level = _bindings(tree) | _BUILTINS
    problems: list[str] = []

    def where(lineno: int) -> str:
        try:
            rel = path.relative_to(APP.parent)
        except ValueError:                      # a temp file from the self-tests
            rel = path.name
        return f"{rel}:{lineno}"

    def visit(node: ast.AST, enclosing: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                here = enclosing | _bindings(child)
                for name in _reads(child):
                    if name.id not in here:
                        problems.append(
                            f"{where(name.lineno)} {child.name}() reads '{name.id}', "
                            f"which it never receives")
                visit(child, here)
            elif isinstance(child, ast.ClassDef):
                visit(child, enclosing | _bindings(child))
            else:
                visit(child, enclosing)

    visit(tree, module_level)
    return problems


def test_no_function_reads_a_name_it_never_received():
    """The exact bug a customer hit, generalised to every file we ship."""
    found: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        found.extend(_unbound_reads(path))
    assert not found, "unbound names would raise NameError at runtime:\n  " + \
        "\n  ".join(found)


def test_the_sweep_would_catch_the_bug_it_was_written_for(tmp_path):
    """A check that cannot fail is not a check. This is the real shape: an inner function
    reading a local that belongs to a DIFFERENT module-level function."""
    p = tmp_path / "broken.py"
    p.write_text(
        "async def outer(x):\n"
        "    runbooks = load(x)\n"
        "    return await inner(x)\n"
        "\n"
        "async def inner(x):\n"
        "    return build(x, runbooks=runbooks)\n"
        "\n"
        "def load(x): return []\n"
        "def build(x, runbooks=None): return runbooks\n"
    )
    assert any("inner() reads 'runbooks'" in m for m in _unbound_reads(p))


def test_the_sweep_does_not_flag_a_real_closure(tmp_path):
    """A nested function genuinely CAN see its parent's locals."""
    p = tmp_path / "fine.py"
    p.write_text(
        "def outer(x):\n"
        "    runbooks = [x]\n"
        "    def inner():\n"
        "        return runbooks\n"
        "    return inner()\n"
    )
    assert _unbound_reads(p) == []


def test_the_sweep_understands_ordinary_python(tmp_path):
    """Every construct that made the first version cry wolf. Thirty false positives is the
    same as no check at all, because the next person deletes it."""
    p = tmp_path / "normal.py"
    p.write_text(
        "import re\n"
        "def f(items, text, mapping):\n"
        "    doubled = [x * 2 for x in items]\n"
        "    pairs = {k: v for k, v in mapping.items()}\n"
        "    if (match := re.search('a', text)):\n"
        "        doubled.append(match.group())\n"
        "    key = lambda item: item.name\n"
        "    with open('f') as fh:\n"
        "        data = fh.read()\n"
        "    for i, row in enumerate(items):\n"
        "        data += str(i) + str(row)\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError as exc:\n"
        "        data += str(exc)\n"
        "    match items:\n"
        "        case [first, *rest]:\n"
        "            data += str(first) + str(rest)\n"
        "    return doubled, pairs, key, data\n"
        "\n"
        "async def g(request):\n"
        "    async def handler(response):\n"
        "        return request, response\n"
        "    return handler\n"
    )
    assert _unbound_reads(p) == []


# ── A module may not define the same name twice ──────────────────────────────
#
# Found the hard way: `laravel_service` grew a second `read()` with a different signature,
# which SILENTLY replaced the first. Three callers of the original then raised TypeError, and
# nothing at import time or in review said a word — the whole Laravel section was broken.
#
# Python allows redefinition on purpose (a `try/except ImportError` fallback, a decorator
# rebinding a name, a platform branch), so this only flags redefinitions in the SAME
# unconditional block — where there is no reason to want one.

def _redefinitions(tree) -> list[str]:
    """Top-level defs/classes bound more than once in one straight-line body."""
    import ast

    bad = []

    def scan(body, where):
        seen = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # A decorator may deliberately rebind (`@x.setter`), so only plain ones count.
                if node.name in seen and not node.decorator_list:
                    bad.append(f"{where}{node.name} (lines {seen[node.name]} and {node.lineno})")
                seen[node.name] = node.lineno
            elif isinstance(node, ast.ClassDef):
                pass
        # Class bodies have the same hazard.
        for node in body:
            if isinstance(node, ast.ClassDef):
                scan(node.body, f"{where}{node.name}.")

    scan(tree.body, "")
    return bad


def test_no_module_defines_the_same_name_twice():
    """The second definition wins and the first disappears, taking its callers with it."""
    import ast

    offenders = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for dup in _redefinitions(tree):
            offenders.append(f"{path.relative_to(APP)}: {dup}")
    assert not offenders, "a later definition silently replaces the earlier one:\n" + \
        "\n".join(offenders)


def test_the_redefinition_sweep_would_actually_catch_one():
    """A check that cannot fail is not a check — this is the exact shape of the real bug."""
    import ast

    src = "def read(a, b):\n    pass\n\n\ndef read(a, b, c):\n    pass\n"
    assert _redefinitions(ast.parse(src))


def test_a_conditional_fallback_is_not_flagged():
    """`try: from x import y / except ImportError: def y(): ...` is deliberate and common."""
    import ast

    src = ("try:\n    from x import thing\nexcept ImportError:\n"
           "    def thing():\n        pass\n")
    assert not _redefinitions(ast.parse(src))


# ── A dict literal may not repeat a key ──────────────────────────────────────
#
# Found the hard way, twice in one day. Python keeps the LAST value for a repeated key and
# says nothing — no error, no warning. The site-scan endpoint grew a second `"note"` and the
# first one, which warned that the scan could not read everything, silently disappeared.
#
# Same family as the redefinition sweep above: the language quietly picks a winner, and the
# loser is invisible in review.

def _duplicate_dict_keys(tree) -> list[str]:
    import ast

    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen = {}
        for key in node.keys:
            # Only constant keys can be compared safely; `**spread` shows up as None and a
            # computed key is not something we can judge.
            if not isinstance(key, ast.Constant):
                continue
            if key.value in seen:
                bad.append(f"{key.value!r} (lines {seen[key.value]} and {key.lineno})")
            seen[key.value] = key.lineno
    return bad


def test_no_dict_literal_repeats_a_key():
    import ast

    offenders = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for dup in _duplicate_dict_keys(tree):
            offenders.append(f"{path.relative_to(APP)}: {dup}")
    assert not offenders, "a repeated key silently drops the earlier value:\n" + \
        "\n".join(offenders)


def test_the_duplicate_key_sweep_would_catch_the_real_one():
    """A check that cannot fail is not a check — this is the exact shape of the bug."""
    import ast

    src = 'x = {"server": s, "note": a, "watching": w, "note": b}\n'
    assert _duplicate_dict_keys(ast.parse(src))


def test_a_spread_is_not_mistaken_for_a_duplicate():
    """`{**summary, "note": n}` is normal and correct."""
    import ast

    assert not _duplicate_dict_keys(ast.parse('x = {**a, "note": n}\n'))
