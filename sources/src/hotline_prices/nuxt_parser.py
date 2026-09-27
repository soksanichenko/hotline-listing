"""Parser for hotline.ua's window.__NUXT__ Nuxt SSR hydration payload.

hotline.ua's product page embeds the full per-seller offer list server-side
in a Nuxt SSR payload of the form
``window.__NUXT__=(function(a,b,c,...){return {...}})(v1,v2,...);`` — a
dedup-by-reference IIFE, not JSON, where the function body references its own
parameters for repeated literal values. This walks that payload with a small
hand-written parser instead of executing it with a JS engine, since running
third-party page JS (even sandboxed, e.g. Node's vm module) carries a real
sandbox-escape/RCE risk class that a text parser structurally cannot have.
"""

import re

_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def _read_string(text: str, i: int) -> tuple[str, int]:
    """Decode a quoted JS string literal starting at i; return (value, index after closing quote)."""
    quote = text[i]
    i += 1
    out = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == quote:
            return "".join(out), i + 1
        if c == "\\":
            i += 1
            esc = text[i]
            if esc == "n":
                out.append("\n")
            elif esc == "t":
                out.append("\t")
            elif esc == "r":
                out.append("\r")
            elif esc == "b":
                out.append("\b")
            elif esc == "f":
                out.append("\f")
            elif esc == "u":
                out.append(chr(int(text[i + 1 : i + 5], 16)))
                i += 4
            elif esc == "x":
                out.append(chr(int(text[i + 1 : i + 3], 16)))
                i += 2
            else:
                out.append(esc)
            i += 1
            continue
        out.append(c)
        i += 1
    raise ValueError("Unterminated string in NUXT payload")


def _find_matching(text: str, open_pos: int) -> int:
    """Return the index of the bracket matching text[open_pos], skipping over string literals."""
    open_char = text[open_pos]
    close_char = {"{": "}", "(": ")", "[": "]"}[open_char]
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'"):
            _, i = _read_string(text, i)
            continue
        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"Unbalanced {open_char!r} in NUXT payload")


class _Parser:
    """Recursive-descent parser for a JS value, resolving bare identifiers via `subs`."""

    def __init__(self, text: str, subs: dict[str, object]) -> None:
        self._text = text
        self._subs = subs
        self._pos = 0

    def _skip_ws(self) -> None:
        while self._pos < len(self._text) and self._text[self._pos] in " \t\r\n":
            self._pos += 1

    def parse_value(self):
        self._skip_ws()
        c = self._text[self._pos]
        if c == "{":
            return self._parse_object()
        if c == "[":
            return self._parse_array()
        if c in ('"', "'"):
            value, self._pos = _read_string(self._text, self._pos)
            return value
        if c == "-" or c.isdigit():
            m = _NUMBER_RE.match(self._text, self._pos)
            if not m:
                raise ValueError(f"Invalid number at position {self._pos}")
            s = m.group(0)
            self._pos = m.end()
            return float(s) if ("." in s or "e" in s or "E" in s) else int(s)
        m = _IDENT_RE.match(self._text, self._pos)
        if not m:
            raise ValueError(f"Unexpected character {c!r} at position {self._pos}")
        name = m.group(0)
        self._pos = m.end()
        if name == "true":
            return True
        if name == "false":
            return False
        if name in ("null", "undefined"):
            return None
        if name == "void":
            self.parse_value()  # `void 0` etc. — operand is discarded
            return None
        while self._pos < len(self._text) and self._text[self._pos] == ".":
            m2 = _IDENT_RE.match(self._text, self._pos + 1)
            if not m2:
                break
            name += "." + m2.group(0)
            self._pos = m2.end()
        if self._pos < len(self._text) and self._text[self._pos] == "(":
            # A constructor/static-method call (e.g. `Array(5)`,
            # `Object.assign(...)`) used as a value — not offers-relevant
            # data, so approximate rather than resolve fully.
            call_close = _find_matching(self._text, self._pos)
            call_args = _Parser(
                self._text[self._pos + 1 : call_close], self._subs
            ).parse_top_level_list()
            self._pos = call_close + 1
            if (
                name == "Array"
                and len(call_args) == 1
                and isinstance(call_args[0], int)
            ):
                return [None] * call_args[0]
            if name == "Object.assign":
                merged: dict = {}
                for a in call_args:
                    if isinstance(a, dict):
                        merged.update(a)
                return merged
            return None
        if name in self._subs:
            return self._subs[name]
        raise ValueError(f"Unresolved identifier {name!r} in NUXT payload")

    def _parse_object(self) -> dict:
        self._pos += 1  # consume '{'
        obj: dict = {}
        self._skip_ws()
        if self._text[self._pos] == "}":
            self._pos += 1
            return obj
        while True:
            self._skip_ws()
            if self._text[self._pos] in ('"', "'"):
                key, self._pos = _read_string(self._text, self._pos)
            else:
                m = _IDENT_RE.match(self._text, self._pos)
                if not m:
                    raise ValueError(f"Expected object key at position {self._pos}")
                key = m.group(0)
                self._pos = m.end()
            self._skip_ws()
            if self._text[self._pos] != ":":
                raise ValueError(f"Expected ':' after key {key!r}")
            self._pos += 1
            obj[key] = self.parse_value()
            self._skip_ws()
            c = self._text[self._pos]
            if c == ",":
                self._pos += 1
                self._skip_ws()
                if self._text[self._pos] == "}":
                    self._pos += 1
                    return obj
                continue
            if c == "}":
                self._pos += 1
                return obj
            raise ValueError(f"Expected ',' or '}}' at position {self._pos}")

    def _parse_array(self) -> list:
        self._pos += 1  # consume '['
        arr: list = []
        self._skip_ws()
        if self._text[self._pos] == "]":
            self._pos += 1
            return arr
        while True:
            arr.append(self.parse_value())
            self._skip_ws()
            c = self._text[self._pos]
            if c == ",":
                self._pos += 1
                self._skip_ws()
                if self._text[self._pos] == "]":
                    self._pos += 1
                    return arr
                continue
            if c == "]":
                self._pos += 1
                return arr
            raise ValueError(f"Expected ',' or ']' at position {self._pos}")

    def parse_top_level_list(self) -> list:
        """Parse a bracket-less comma-separated value list (the IIFE's call arguments)."""
        values: list = []
        self._skip_ws()
        if self._pos >= len(self._text):
            return values
        while True:
            values.append(self.parse_value())
            self._skip_ws()
            if self._pos >= len(self._text):
                return values
            if self._text[self._pos] != ",":
                raise ValueError(f"Unexpected character at position {self._pos}")
            self._pos += 1
            self._skip_ws()
            if self._pos >= len(self._text):
                return values


def _split_statements(text: str) -> list[str]:
    """Split top-level `;`-separated statements, respecting nesting and strings."""
    stmts = []
    depth = 0
    start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'"):
            _, i = _read_string(text, i)
            continue
        if c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c == ";" and depth == 0:
            stmts.append(text[start:i])
            start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        stmts.append(tail)
    return stmts


_ARRAY_ASSIGN_RE = re.compile(r"^([A-Za-z_$][A-Za-z0-9_$]*)\[(\d+)\]=(.*)$", re.DOTALL)


def parse_nuxt_payload(html: str) -> dict:
    """Parse the window.__NUXT__ payload embedded in a hotline.ua page into a plain dict."""
    start = html.index("window.__NUXT__=")
    end = html.index("</script>", start)
    src = html[start + len("window.__NUXT__=") : end]

    func_kw = src.index("function(")
    params_open = func_kw + len("function")
    params_close = _find_matching(src, params_open)
    params = [
        p.strip() for p in src[params_open + 1 : params_close].split(",") if p.strip()
    ]

    body_open = src.index("{", params_close)
    body_close = _find_matching(src, body_open)
    body = src[body_open + 1 : body_close].strip()

    args_open = src.index("(", body_close)
    args_close = _find_matching(src, args_open)
    args_text = src[args_open + 1 : args_close]
    args = _Parser(args_text, {}).parse_top_level_list()

    if len(params) != len(args):
        raise ValueError(
            f"NUXT payload parameter/argument count mismatch: {len(params)} vs {len(args)}"
        )
    subs = dict(zip(params, args))

    # The body isn't always a bare `return {...}` — it can prefix a few
    # `ident[index]=value;` statements that fill in a pre-declared array
    # argument before returning (used for a handful of unique strings not
    # worth passing as literals). Apply those mutations, then parse the
    # `return` expression; anything else is ignored — offers data never
    # lives in one of these mutated arrays.
    return_expr = None
    for stmt in _split_statements(body):
        stmt = stmt.strip()
        if not stmt:
            continue
        if stmt.startswith("return "):
            return_expr = stmt[len("return ") :].strip()
            break
        m = _ARRAY_ASSIGN_RE.match(stmt)
        if m:
            ident, index_str, value_text = m.groups()
            target = subs.get(ident)
            if isinstance(target, list):
                index = int(index_str)
                while len(target) <= index:
                    target.append(None)
                target[index] = _Parser(value_text, subs).parse_value()

    if return_expr is None:
        raise ValueError("No 'return' statement found in NUXT payload function body")
    return_expr = return_expr.removesuffix(";")

    return _Parser(return_expr, subs).parse_value()


def _find_offers_edges(node: object) -> list | None:
    """Depth-first search for the offers.edges list inside a parsed NUXT payload."""
    if isinstance(node, dict):
        edges = node.get("edges")
        if (
            isinstance(edges, list)
            and edges
            and all(
                isinstance(e, dict) and isinstance(e.get("node"), dict) for e in edges
            )
            and "price" in edges[0]["node"]
        ):
            return edges
        for value in node.values():
            found = _find_offers_edges(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_offers_edges(item)
            if found is not None:
                return found
    return None


def extract_offer_prices(html: str) -> list[float]:
    """Return per-seller offer prices embedded in a hotline.ua product page's NUXT payload.

    Returns an empty list if the payload can't be found/parsed or has no
    offers — callers should treat that as "no data", not raise.
    """
    nuxt = parse_nuxt_payload(html)
    edges = _find_offers_edges(nuxt)
    if not edges:
        return []
    prices = []
    for edge in edges:
        price = edge["node"].get("price")
        if isinstance(price, (int, float)):
            prices.append(float(price))
    return prices
