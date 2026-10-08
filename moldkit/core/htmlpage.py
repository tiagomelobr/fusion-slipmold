"""Self-contained HTML pages for SlipMold windows in Fusion (help pages, the process sheet). No adsk.

The page follows the Fusion theme through its URL: <page>.html?theme=dark|light|auto (auto follows the OS);
the theme is carried to links between .html pages. Links with class "ext" (web pages, files, folders) are sent
to the add-in with adsk.fusionSendData("open", <absolute URL>), which opens them outside Fusion; after loading,
the page sends adsk.fusionSendData("loaded", {title, w, h}) (its viewport size) so the add-in can tell it is shown.
"""
import html

CSS = """
:root { --bg:#ffffff; --fg:#1f2328; --muted:#59636e; --line:#d1d9e0; --soft:#f6f8fa; --link:#0969da;
        --nav:#f0f2f4; --on:#ffffff; }
html.dark { --bg:#1e1f22; --fg:#e6e6e6; --muted:#a0a4ab; --line:#3d4046; --soft:#2a2c30; --link:#5aa2ff;
        --nav:#26282c; --on:#3a3d43; }
@media (prefers-color-scheme: dark) {
  html.auto { --bg:#1e1f22; --fg:#e6e6e6; --muted:#a0a4ab; --line:#3d4046; --soft:#2a2c30; --link:#5aa2ff;
          --nav:#26282c; --on:#3a3d43; } }
html, body { margin:0; background:var(--bg); color:var(--fg); }
body { font:14px/1.55 "Segoe UI", Arial, sans-serif; }
nav { position:sticky; top:0; z-index:2; display:flex; flex-wrap:wrap; gap:4px; align-items:center;
      padding:6px 10px; background:var(--nav); border-bottom:1px solid var(--line); }
nav a, nav button { font:13px "Segoe UI", Arial, sans-serif; color:var(--fg); background:none;
      border:1px solid transparent; border-radius:4px; padding:2px 8px; text-decoration:none; cursor:pointer; }
nav a:hover, nav button:hover { border-color:var(--line); text-decoration:none; }
nav a.on { background:var(--on); border-color:var(--line); font-weight:600; }
main { padding:8px 22px 40px; max-width:980px; }
h1 { font-size:1.6em; border-bottom:1px solid var(--line); padding-bottom:.2em; }
h2 { font-size:1.3em; border-bottom:1px solid var(--line); padding-bottom:.15em; margin-top:1.6em; }
h3 { font-size:1.1em; margin-top:1.3em; }
a { color:var(--link); text-decoration:none; } a:hover { text-decoration:underline; }
code { font:12.5px Consolas, "Courier New", monospace; background:var(--soft); padding:1px 4px; border-radius:3px; }
pre { background:var(--soft); border:1px solid var(--line); border-radius:5px; padding:10px 12px; overflow:auto; }
pre code { background:none; padding:0; }
table { border-collapse:collapse; margin:10px 0; display:block; overflow-x:auto; }
th, td { border:1px solid var(--line); padding:4px 9px; vertical-align:top; }
th { background:var(--soft); }
td.num, th.num { text-align:right; }
blockquote { margin:10px 0; padding:2px 14px; border-left:4px solid var(--line); color:var(--muted); }
hr { border:0; border-top:1px solid var(--line); }
li { margin:2px 0; }
.foot { color:var(--muted); font-size:12px; margin-top:30px; }
"""

HEAD_JS = """
(function () {
  var m = /[?&]theme=(dark|light|auto)/.exec(location.search);
  var theme = m ? m[1] : 'auto';
  document.documentElement.className = theme;
  document.addEventListener('DOMContentLoaded', function () {
    if (!m) { return; }
    var links = document.querySelectorAll('a[href]');
    for (var i = 0; i < links.length; i++) {
      var h = links[i].getAttribute('href');
      if (/^[^:?#]+\\.html(#.*)?$/i.test(h)) {
        var p = h.split('#');
        links[i].setAttribute('href', p[0] + '?theme=' + theme + (p[1] ? '#' + p[1] : ''));
      }
    }
  });
})();
"""

BODY_JS = """
document.addEventListener('click', function (e) {
  var a = e.target.closest ? e.target.closest('a.ext') : null;
  if (!a) { return; }
  e.preventDefault();
  try { adsk.fusionSendData('open', a.href); }
  catch (err) { window.location.href = a.href; }
});
window.addEventListener('load', function () {
  setTimeout(function () { try { adsk.fusionSendData('loaded', JSON.stringify({title: document.title, w: window.innerWidth, h: window.innerHeight})); } catch (err) {} }, 300);
});
"""


def esc(text):
    return html.escape(str(text), quote=False)


def page(title, body_html, nav_html="", foot=None):
    """A complete HTML document: title, optional nav bar, body and an optional footer line."""
    foot_html = '<p class="foot">%s</p>' % esc(foot) if foot else ""
    return ("<!DOCTYPE html>\n<html class=\"auto\"><head><meta charset=\"utf-8\"><title>%s</title>"
            "<script>%s</script><style>%s</style></head>\n<body>%s<main>\n%s\n%s</main><script>%s</script>"
            "</body></html>\n" % (esc(title), HEAD_JS, CSS, nav_html, body_html, foot_html, BODY_JS))


def table(headers, rows, numeric=()):
    """An HTML table; cells are escaped text; column indices in numeric are right-aligned."""
    def cells(tag, values):
        return "".join("<%s%s>%s</%s>" % (tag, ' class="num"' if k in numeric else "", esc(v), tag)
                       for k, v in enumerate(values))
    body = "".join("<tr>%s</tr>" % cells("td", r) for r in rows)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (cells("th", headers), body)
