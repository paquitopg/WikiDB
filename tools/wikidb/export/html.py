"""Convert the limited HTML that XWiki renders for rich-text fields into simple blocks (U13, KTD18).

Supported: paragraphs, headings, bold and italic, links, bulleted and numbered lists (nested lists are flattened with a
level), tables, line breaks. Anything else keeps its text. Links become absolute on the wiki's public origin, because
XWiki renders internal links as paths, which would be dead in a downloaded file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    href: str | None = None


@dataclass
class Paragraph:
    runs: list[Run] = field(default_factory=list)
    heading: bool = False
    list_kind: str | None = None      # "bullet" or "number" for a list item
    level: int = 0

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class Table:
    rows: list[list[str]] = field(default_factory=list)
    header: bool = False


Block = Paragraph | Table


def absolute_url(href: str, public_origin: str, internal_origins: tuple[str, ...] = ()) -> str:
    """Make a wiki link usable outside the browser: paths and in-cluster hosts move to the public origin."""
    parts = urlsplit(href)
    if not parts.scheme and not parts.netloc:
        return urljoin(public_origin.rstrip("/") + "/", href)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin in internal_origins or parts.hostname in ("localhost", "127.0.0.1"):
        return public_origin.rstrip("/") + href[len(origin):]
    return href


class _Parser(HTMLParser):
    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}

    def __init__(self, public_origin: str, internal_origins: tuple[str, ...]):
        super().__init__(convert_charrefs=True)
        self.public_origin, self.internal_origins = public_origin, internal_origins
        self.blocks: list[Block] = []
        self.current: Paragraph | None = None
        self.bold = self.italic = 0
        self.href: list[str | None] = []
        self.lists: list[str] = []
        self.table: Table | None = None
        self.cell: list[str] | None = None
        self.row: list[str] | None = None

    def _paragraph(self) -> Paragraph:
        if self.current is None:
            self.current = Paragraph()
        return self.current

    def _close(self):
        if self.current is not None and self.current.text.strip():
            self.blocks.append(self.current)
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.table is not None and tag in ("tr", "td", "th"):
            if tag == "tr":
                self.row = []
            else:
                self.cell = []
                self.table.header = self.table.header or (tag == "th" and not self.table.rows)
            return
        if tag in self.BLOCK_TAGS:
            self._close()
            self.current = Paragraph(heading=tag.startswith("h") and tag != "hr")
        elif tag in ("ul", "ol"):
            self._close()
            self.lists.append("number" if tag == "ol" else "bullet")
        elif tag == "li":
            self._close()
            self.current = Paragraph(list_kind=self.lists[-1] if self.lists else "bullet",
                                     level=max(len(self.lists) - 1, 0))
        elif tag == "table":
            self._close()
            self.table = Table()
        elif tag in ("strong", "b"):
            self.bold += 1
        elif tag in ("em", "i"):
            self.italic += 1
        elif tag == "a":
            href = attrs.get("href")
            self.href.append(absolute_url(href, self.public_origin, self.internal_origins) if href else None)
        elif tag == "br":
            self.handle_data("\n")

    def handle_endtag(self, tag):
        if self.table is not None and tag in ("td", "th", "tr", "table"):
            if tag in ("td", "th") and self.cell is not None and self.row is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.table.rows.append(self.row)
                self.row = None
            elif tag == "table":
                if self.table.rows:
                    self.blocks.append(self.table)
                self.table = None
            return
        if tag in self.BLOCK_TAGS or tag == "li":
            self._close()
        elif tag in ("ul", "ol") and self.lists:
            self._close()
            self.lists.pop()
        elif tag in ("strong", "b"):
            self.bold = max(self.bold - 1, 0)
        elif tag in ("em", "i"):
            self.italic = max(self.italic - 1, 0)
        elif tag == "a" and self.href:
            self.href.pop()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
            return
        if self.table is not None:
            return
        if self.current is None and not data.strip():
            return
        href = next((h for h in reversed(self.href) if h), None)
        self._paragraph().runs.append(Run(data, bold=self.bold > 0, italic=self.italic > 0, href=href))

    def close(self):
        super().close()
        self._close()


def parse(html: str, public_origin: str, internal_origins: tuple[str, ...] = ()) -> list[Block]:
    parser = _Parser(public_origin, internal_origins)
    parser.feed(html or "")
    parser.close()
    return parser.blocks
