"""Build the SlipMold add-in help pages from the user docs: python tools/build_help.py [--check]

The add-in shows these pages in a Fusion window (palette) as they are: the text is embedded in static HTML
files under addin/SlipMold/help/, so Fusion never reads or converts Markdown. Run this after editing a doc;
--check exits 1 when a page is out of date (the unit tests run it).

Markdown subset (what the docs use): ATX headings, paragraphs, nested ordered/unordered lists with wrapped
lines, pipe tables with alignment, fenced code, block quotes, rules, code spans, bold, italics, links and
<http://...> autolinks. Links between the pages stay relative (the palette's Back works); links to other
files, folders or web pages get class "ext" and the add-in opens them outside Fusion.
"""
import html
import os
import re
import sys
from urllib.parse import quote, unquote

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from moldkit.core import htmlpage  # noqa: E402

OUT_DIR = os.path.join(REPO, "addin", "SlipMold", "help")
PAGES = (  # (page file stem, source doc, nav label)
    ("user-guide", "docs/USER_GUIDE.md", "User guide"),
    ("parameters", "docs/PARAMETERS.md", "Parameters"),
    ("validation", "docs/VALIDATION.md", "Tested shapes"),
    ("add-in", "docs/ADDIN.md", "Add-in reference"),
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_LIST = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +|$)(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
_QUOTE = re.compile(r"^\s{0,3}> ?(.*)$")


# ---------------------------------------------------------------------------- inline
def slug(text, seen=None):
    """GitHub-style heading anchor: lower case, punctuation dropped, spaces to hyphens; repeats get -1, -2."""
    s = re.sub(r"<[^>]+>", "", text).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s).replace(" ", "-")
    if seen is not None:
        base, n = s, seen.get(s, 0)
        if n:
            s = "%s-%d" % (base, n)
        seen[base] = n + 1
    return s


def _emphasis(s):
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w\\])_(?=\S)([^_]+?)(?<=\S)_(?!\w)", r"<em>\1</em>", s)
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", s)


def inline(text, resolve=None):
    """Inline Markdown to HTML. resolve(href) -> (url, css_class) rewrites link targets."""
    kept = []  # finished HTML (code spans, links) kept out of the emphasis rules

    def keep(fragment):
        kept.append(fragment)
        return "\x00%d\x00" % (len(kept) - 1)

    s = re.sub(r"(`+)(.+?)\1", lambda m: keep("<code>%s</code>" % html.escape(m.group(2).strip(), quote=False)),
               text)
    s = html.escape(s, quote=False)

    def link(label, href):
        url, cls = resolve(href) if resolve else (href, "")
        attr = ' class="%s"' % cls if cls else ""
        return keep('<a href="%s"%s>%s</a>' % (html.escape(url, quote=True), attr, _emphasis(label)))

    s = re.sub(r"&lt;((?:https?|mailto):[^\s&]+)&gt;", lambda m: link(m.group(1), m.group(1)), s)
    s = re.sub(r"\[([^\]]+)\]\(\s*([^)\s]+)(?:\s+\"[^)]*\")?\s*\)",
               lambda m: link(m.group(1), html.unescape(m.group(2))), s)
    s = _emphasis(s)
    while "\x00" in s:  # a link label can hold a code span
        s = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], s)
    return s


# ---------------------------------------------------------------------------- blocks
def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _starts_block(line):
    return bool(_HEADING.match(line) or _FENCE.match(line) or _QUOTE.match(line) or line.lstrip().startswith("|")
                or _RULE.match(line))


def _cells(row):
    """Cells of a pipe-table row; '|' inside code spans or escaped as '\\|' does not split."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    out, cur, in_code, i = [], "", False, 0
    while i < len(row):
        ch = row[i]
        if ch == "\\" and i + 1 < len(row) and row[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur.strip())
    return out


def _table(lines, i, resolve):
    head = _cells(lines[i])
    aligns = []
    for c in _cells(lines[i + 1]):
        c = c.strip()
        aligns.append("center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":")
                      else "left" if c.startswith(":") else "")
    i += 2

    def cell(tag, text, k):
        a = aligns[k] if k < len(aligns) else ""
        return "<%s%s>%s</%s>" % (tag, ' style="text-align:%s"' % a if a else "", inline(text, resolve), tag)

    out = ["<table>", "<thead><tr>" + "".join(cell("th", c, k) for k, c in enumerate(head)) + "</tr></thead>",
           "<tbody>"]
    while i < len(lines) and lines[i].strip().startswith("|"):
        row = _cells(lines[i])
        row += [""] * (len(head) - len(row))
        out.append("<tr>" + "".join(cell("td", c, k) for k, c in enumerate(row[:len(head)])) + "</tr>")
        i += 1
    out.append("</tbody></table>")
    return "\n".join(out), i


def _list(lines, i, resolve, seen):
    first = _LIST.match(lines[i])
    indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    start = int(first.group(2)[:-1]) if ordered else 1
    items, loose = [], False
    while i < len(lines):
        m = _LIST.match(lines[i])
        if not m or len(m.group(1)) != indent or m.group(2)[0].isdigit() != ordered:
            break
        col = indent + len(m.group(2)) + max(1, min(len(m.group(3)), 4))
        body = [m.group(4)]
        i += 1
        while i < len(lines):
            ln = lines[i]
            if not ln.strip():
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and _indent(lines[j]) > indent:
                    loose = loose or not _LIST.match(lines[j])
                    body.append("")
                    i += 1
                    continue
                if j < len(lines):  # blank line, then a sibling item: a loose list
                    nxt = _LIST.match(lines[j])
                    if nxt and len(nxt.group(1)) == indent and nxt.group(2)[0].isdigit() == ordered:
                        loose = True
                break
            sub = _LIST.match(ln)
            if sub and len(sub.group(1)) <= indent:
                break
            if _indent(ln) > indent:
                body.append(ln[min(_indent(ln), col):])
            elif not _starts_block(ln) and body[-1].strip():
                body.append(ln.strip())  # lazy continuation of the item's paragraph
            else:
                break
            i += 1
        items.append(body)
    out = []
    for body in items:
        inner = _blocks(body, resolve, seen)
        if not loose and inner.startswith("<p>"):
            end = inner.find("</p>")
            inner = inner[3:end] + inner[end + 4:]
        out.append("<li>%s</li>" % inner.strip())
    tag = "ol" if ordered else "ul"
    attr = ' start="%d"' % start if ordered and start != 1 else ""
    return "<%s%s>\n%s\n</%s>" % (tag, attr, "\n".join(out), tag), i


def _blocks(lines, resolve, seen):
    out, i, para = [], 0, []

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(x.strip() for x in para), resolve))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            flush()
            i += 1
            continue
        f = _FENCE.match(ln)
        if f:
            flush()
            fence, code, i = f.group(1), [], i + 1
            pad = _indent(ln)
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code.append(lines[i][min(pad, _indent(lines[i])):])
                i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code), quote=False))
            i += 1
            continue
        h = _HEADING.match(ln)
        if h:
            flush()
            n = len(h.group(1))
            text = inline(h.group(2), resolve)
            out.append('<h%d id="%s">%s</h%d>' % (n, slug(h.group(2), seen), text, n))
            i += 1
            continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            t, i = _table(lines, i, resolve)
            out.append(t)
            continue
        if _RULE.match(ln) and not para:
            out.append("<hr>")
            i += 1
            continue
        q = _QUOTE.match(ln)
        if q:
            flush()
            quoted = []
            while i < len(lines) and lines[i].strip():
                qm = _QUOTE.match(lines[i])
                quoted.append(qm.group(1) if qm else lines[i].strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % _blocks(quoted, resolve, seen))
            continue
        lm = _LIST.match(ln)
        if lm and (not para or not lm.group(2)[0].isdigit() or lm.group(2)[:-1] == "1"):
            flush()
            lst, i = _list(lines, i, resolve, seen)
            out.append(lst)
            continue
        para.append(ln)
        i += 1
    flush()
    return "\n".join(out)


def md_to_html_body(text, resolve=None):
    """The HTML body (no page frame) of a Markdown text."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ").split("\n")
    return _blocks(lines, resolve, {})


# ---------------------------------------------------------------------------- pages
def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def make_resolver(src_path, page_of, out_dir):
    """resolve(href) for links in src_path. page_of {normalised doc path: page stem}: links to those docs become
    relative page links; other relative links become relative file links (class "ext"), web links class "ext"."""
    base = os.path.dirname(os.path.abspath(src_path))

    def resolve(href):
        if href.startswith("#"):
            return href, ""
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.IGNORECASE) and not re.match(r"^[a-z]:[\\/]", href, re.I):
            return href, "ext"
        path, _, frag = href.partition("#")
        target = path if os.path.isabs(path) else os.path.join(base, unquote(path))
        stem = page_of.get(_norm(target))
        if stem:
            return stem + ".html" + ("#" + frag if frag else ""), ""
        rel = os.path.relpath(os.path.abspath(target), out_dir).replace("\\", "/")
        return quote(rel) + ("#" + quote(frag) if frag else ""), "ext"
    return resolve


def _nav(current, pages):
    parts = ['<nav><button onclick="history.back()" title="Back">&#9664; Back</button>']
    for stem, _src, label in pages:
        cls = ' class="on"' if stem == current else ""
        parts.append('<a href="%s.html"%s>%s</a>' % (stem, cls, html.escape(label)))
    parts.append("</nav>")
    return "".join(parts)


def _title(text, fallback):
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def build(repo=REPO, out_dir=OUT_DIR, pages=PAGES):
    """{page path: html} for every page whose source doc exists."""
    pages = [p for p in pages if os.path.isfile(os.path.join(repo, p[1]))]
    page_of = {_norm(os.path.join(repo, src)): stem for stem, src, _label in pages}
    out = {}
    for stem, src, label in pages:
        path = os.path.join(repo, src)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        body = md_to_html_body(text, make_resolver(path, page_of, out_dir))
        out[os.path.join(out_dir, stem + ".html")] = htmlpage.page(
            _title(text, label), body, _nav(stem, pages), foot="From %s (tools/build_help.py)." % src)
    return out


def stale(pages):
    """Paths whose file content differs from the built page."""
    bad = []
    for path, text in pages.items():
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                if fh.read() == text:
                    continue
        except OSError:
            pass
        bad.append(path)
    return bad


def main(argv):
    pages = build()
    if "--check" in argv:
        bad = stale(pages)
        for p in bad:
            print("out of date: %s (run python tools/build_help.py)" % os.path.relpath(p, REPO))
        return 1 if bad else 0
    os.makedirs(OUT_DIR, exist_ok=True)
    for path, text in pages.items():
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("wrote %s (%d chars)" % (os.path.relpath(path, REPO), len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
