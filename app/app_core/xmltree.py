"""A small XML reader and writer that keeps the file byte for byte.

VTL's `.speaker` files are plain XML without namespaces, CDATA or entities
in practice, but their layout (indentation, CRLF line ends, double spaces
between attributes, the number of decimals) differs between files. The
reader keeps every piece of text it does not interpret, so writing an
unchanged tree gives the original bytes back, and changing one attribute
changes only the characters of its value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

_NAME = r"[A-Za-z_:][-A-Za-z0-9_.:]*"
_ATTR = re.compile(r"(\s+)(" + _NAME + r")(\s*=\s*)(\"[^\"]*\"|'[^']*')")
_START = re.compile(r"<(" + _NAME + r")")
_END = re.compile(r"</(" + _NAME + r")(\s*)>")
_ESCAPES = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;")]


def escape(text: str) -> str:
    for a, b in _ESCAPES:
        text = text.replace(a, b)
    return text


def unescape(text: str) -> str:
    text = text.replace("&apos;", "'")
    for a, b in reversed(_ESCAPES):
        text = text.replace(b, a)
    return text


@dataclass
class Attr:
    """One attribute with the text around it: `lead name eq "raw"`."""

    lead: str
    name: str
    eq: str
    quote: str
    raw: str  # the value as written in the file, still escaped

    @property
    def value(self) -> str:
        return unescape(self.raw)

    def text(self) -> str:
        return f"{self.lead}{self.name}{self.eq}{self.quote}{self.raw}{self.quote}"


@dataclass
class Element:
    tag: str
    attrs: list[Attr] = field(default_factory=list)
    tail_of_start: str = ""  # whitespace before `>` or `/>`
    self_closing: bool = False
    children: list["Element | str"] = field(default_factory=list)  # str = text between elements
    end_space: str = ""  # whitespace inside `</tag  >`
    parent: "Element | None" = field(default=None, repr=False, compare=False)

    # -- attributes -------------------------------------------------------

    def get(self, name: str, default: str | None = None) -> str | None:
        for a in self.attrs:
            if a.name == name:
                return a.value
        return default

    def attr(self, name: str) -> Attr:
        for a in self.attrs:
            if a.name == name:
                return a
        raise KeyError(f"<{self.tag}> has no attribute {name!r}")

    def set(self, name: str, value: str) -> None:
        """Set an attribute's text. A new attribute goes at the end."""
        raw = escape(value)
        for a in self.attrs:
            if a.name == name:
                a.raw = raw
                return
        self.attrs.append(Attr(" ", name, "=", '"', raw))

    # -- children ---------------------------------------------------------

    def elements(self, tag: str | None = None) -> Iterator["Element"]:
        for c in self.children:
            if isinstance(c, Element) and (tag is None or c.tag == tag):
                yield c

    def find(self, tag: str) -> "Element | None":
        return next(self.elements(tag), None)

    def child(self, tag: str) -> "Element":
        e = self.find(tag)
        if e is None:
            raise KeyError(f"<{self.tag}> has no <{tag}>")
        return e

    # -- writing ----------------------------------------------------------

    def write(self, out: list[str]) -> None:
        out.append("<" + self.tag)
        out.extend(a.text() for a in self.attrs)
        out.append(self.tail_of_start)
        if self.self_closing:
            out.append("/>")
            return
        out.append(">")
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            else:
                c.write(out)
        out.append(f"</{self.tag}{self.end_space}>")


@dataclass
class Document:
    prolog: str  # everything before the root element (declaration, comments, space)
    root: Element
    epilog: str  # everything after it

    def text(self) -> str:
        out = [self.prolog]
        self.root.write(out)
        out.append(self.epilog)
        return "".join(out)


class ParseError(ValueError):
    pass


def parse(text: str) -> Document:
    pos = 0
    n = len(text)
    # The prolog: declarations, comments and space before the root.
    while True:
        m = re.compile(r"\s*(<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^>]*>)?", re.S).match(text, pos)
        if m.group(1) is None:
            prolog_end = m.end()
            break
        pos = m.end()
    pos = prolog_end
    root, pos = _parse_element(text, pos)
    return Document(text[:prolog_end], root, text[pos:])


def _parse_element(text: str, pos: int) -> tuple[Element, int]:
    m = _START.match(text, pos)
    if not m:
        raise ParseError(f"expected an element at offset {pos}")
    e = Element(m.group(1))
    pos = m.end()
    while True:
        a = _ATTR.match(text, pos)
        if not a:
            break
        q = a.group(4)
        e.attrs.append(Attr(a.group(1), a.group(2), a.group(3), q[0], q[1:-1]))
        pos = a.end()
    ws = re.compile(r"\s*").match(text, pos)
    e.tail_of_start = ws.group(0)
    pos = ws.end()
    if text.startswith("/>", pos):
        e.self_closing = True
        return e, pos + 2
    if not text.startswith(">", pos):
        raise ParseError(f"malformed start tag <{e.tag}> at offset {pos}")
    pos += 1
    while True:
        lt = text.find("<", pos)
        if lt < 0:
            raise ParseError(f"<{e.tag}> is not closed")
        if lt > pos:
            e.children.append(text[pos:lt])
        pos = lt
        if text.startswith("</", pos):
            m = _END.match(text, pos)
            if not m or m.group(1) != e.tag:
                raise ParseError(f"mismatched end tag at offset {pos} (open: <{e.tag}>)")
            e.end_space = m.group(2)
            return e, m.end()
        if text.startswith("<!--", pos):
            end = text.find("-->", pos)
            if end < 0:
                raise ParseError("unterminated comment")
            e.children.append(text[pos:end + 3])  # comments are kept as text
            pos = end + 3
            continue
        child, pos = _parse_element(text, pos)
        child.parent = e
        e.children.append(child)
