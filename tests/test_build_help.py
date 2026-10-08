"""tools/build_help.py: Markdown docs to the add-in's static help pages (no adsk)."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "addin", "SlipMold"))

import build_help as D  # noqa: E402
import slipmold_helpers as H  # noqa: E402


def body(md, resolve=None):
    return D.md_to_html_body(md, resolve)


class InlineTest(unittest.TestCase):
    def test_code_bold_italic_escape(self):
        s = D.inline("Set **`mold_seamClearance`** to *0.2* in <repo>\\molds_dir & go")
        self.assertIn("<strong><code>mold_seamClearance</code></strong>", s)
        self.assertIn("<em>0.2</em>", s)
        self.assertIn("&lt;repo&gt;\\molds_dir &amp; go", s)  # underscores inside words stay literal

    def test_code_span_is_literal(self):
        self.assertEqual(D.inline("`a*b*c <x>`"), "<code>a*b*c &lt;x&gt;</code>")

    def test_links_and_autolinks(self):
        s = D.inline("[guide](USER_GUIDE.md#9-calibration) and <https://example.com/a_b_c>",
                     lambda h: (h.replace(".md", ".html"), "ext" if h.startswith("http") else ""))
        self.assertIn('<a href="USER_GUIDE.html#9-calibration">guide</a>', s)
        self.assertIn('<a href="https://example.com/a_b_c" class="ext">https://example.com/a_b_c</a>', s)

    def test_slug(self):
        seen = {}
        self.assertEqual(D.slug("9. Calibration with the `coupons`", seen), "9-calibration-with-the-coupons")
        self.assertEqual(D.slug("Notes", seen), "notes")
        self.assertEqual(D.slug("Notes", seen), "notes-1")


class BlockTest(unittest.TestCase):
    def test_headings_paragraphs_rule(self):
        h = body("# Title\n\nline one\nline two\n\n---\n\n## Sub")
        self.assertIn('<h1 id="title">Title</h1>', h)
        self.assertIn("<p>line one line two</p>", h)
        self.assertIn("<hr>", h)
        self.assertIn('<h2 id="sub">Sub</h2>', h)

    def test_nested_lists_with_wrapped_lines(self):
        md = ("1. **Select model.** Pick the body.\n   Wrapped line.\n2. Second\n   - nested a\n     wrapped\n"
              "   - nested b\n3. Third\n\nAfter.")
        h = body(md)
        self.assertEqual(h.count("<ol>"), 1)
        self.assertIn("<li><strong>Select model.</strong> Pick the body. Wrapped line.</li>", h)
        self.assertIn("<ul>\n<li>nested a wrapped</li>\n<li>nested b</li>\n</ul>", h)
        self.assertIn("<li>Third</li>", h)
        self.assertTrue(h.endswith("<p>After.</p>"))

    def test_ordered_start_and_loose(self):
        h = body("3. a\n\n4. b")
        self.assertIn('<ol start="3">', h)
        self.assertIn("<li><p>a</p></li>", h)

    def test_table_alignment_and_pipes_in_code(self):
        h = body("| Part | g |\n|---|---:|\n| `a|b` | 1.5 |\n| c \\| d | 2 |")
        self.assertIn('<th style="text-align:right">g</th>', h)
        self.assertIn("<td><code>a|b</code></td>", h)
        self.assertIn("<td>c | d</td>", h)
        self.assertEqual(h.count("<tr>"), 3)

    def test_fence_and_quote(self):
        h = body("```\npowershell -File x.ps1 <arg>\n```\n\n> quoted **text**")
        self.assertIn("<pre><code>powershell -File x.ps1 &lt;arg&gt;</code></pre>", h)
        self.assertIn("<blockquote><p>quoted <strong>text</strong></p></blockquote>", h)


class BuildTest(unittest.TestCase):
    def test_build_pages_links_nav_and_ext(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = os.path.join(tmp, "docs")
            os.makedirs(docs)
            with open(os.path.join(docs, "USER_GUIDE.md"), "w", encoding="utf-8") as fh:
                fh.write("# SlipMold user guide\n\nSee [params](PARAMETERS.md#casing), [other](../README.txt) "
                         "and [web](https://example.com).\n")
            with open(os.path.join(docs, "PARAMETERS.md"), "w", encoding="utf-8") as fh:
                fh.write("# Parameters\n\n## Casing\n")
            out_dir = os.path.join(tmp, "addin", "SlipMold", "help")
            pages = D.build(tmp, out_dir, D.PAGES)
            self.assertEqual(sorted(os.path.basename(p) for p in pages), ["parameters.html", "user-guide.html"])
            page = pages[os.path.join(out_dir, "user-guide.html")]
            self.assertIn("<title>SlipMold user guide</title>", page)
            self.assertIn('<a href="parameters.html#casing">params</a>', page)
            self.assertIn('<a href="../../../README.txt" class="ext">other</a>', page)
            self.assertIn('<a href="https://example.com" class="ext">web</a>', page)
            self.assertIn('<a href="user-guide.html" class="on">User guide</a>', page)
            self.assertNotIn("Tested shapes", page)  # the nav lists only pages that exist
            self.assertIn("adsk.fusionSendData('open', a.href)", page)
            self.assertEqual(sorted(D.stale(pages)), sorted(pages))  # nothing written yet

    def test_shipped_help_pages_are_current(self):
        self.assertEqual(D.stale(D.build()), [], "run python tools/build_help.py")

    def test_repo_docs_render_without_leftover_markup(self):
        import re
        for path, h in D.build().items():
            text = re.sub(r"<pre>.*?</pre>|<code>.*?</code>", "", h[h.find("<main>"):], flags=re.S)
            self.assertNotIn("**", text, path)
            self.assertNotIn("<p>|", text, path)


class HelperTest(unittest.TestCase):
    def test_friendly_error_names_the_window_when_shown(self):
        err = {"message": "boom", "hint": "fix it", "report": "C:/m/runs/s8.json"}
        self.assertIn("Report: C:/m/runs/s8.json", H.friendly_error(err, "C:/m/runs/addin.log"))
        shown = H.friendly_error(err, "C:/m/runs/addin.log", shown=True)
        self.assertIn("SlipMold window", shown)
        self.assertNotIn("s8.json", shown)
        self.assertNotIn("addin.log", shown)

    def test_strip_report_lines_and_view_dir(self):
        self.assertEqual(H.strip_report_lines("s8: pass\nReport: C:/x.json\nsaved version 3"), "s8: pass\nsaved version 3")
        self.assertEqual(H.strip_report_lines(None), "")
        self.assertEqual(H.view_dir("C:/T"), "C:/T/SlipMold/view")

    def test_open_target(self):
        self.assertEqual(H.open_target("https://x.org/a"), ("url", "https://x.org/a"))
        url = "file:///" + os.path.join(ROOT, "docs").replace("\\", "/")
        kind, path = H.open_target(url + "#frag")
        self.assertEqual(kind, "path")
        self.assertEqual(os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.join(ROOT, "docs")))
        self.assertIsNone(H.open_target("javascript:alert(1)"))

    def test_theme_name(self):
        enum = type("T", (), {"DarkBlueUserInterfaceTheme": 2, "DarkGrayUserInterfaceTheme": 3,
                              "DeviceUserInterfaceTheme": 4})
        self.assertEqual([H.theme_name(v, enum) for v in (1, 2, 3, 4)], ["light", "dark", "dark", "auto"])

    def test_page_url(self):
        u = H.page_url(os.path.join(ROOT, "addin", "SlipMold", "help", "user-guide.html"), "dark")
        self.assertTrue(u.startswith("file:///"), u)
        self.assertTrue(u.endswith("/addin/SlipMold/help/user-guide.html?theme=dark"), u)


if __name__ == "__main__":
    unittest.main()
