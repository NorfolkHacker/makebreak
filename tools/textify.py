#!/usr/bin/env python3
"""textify — build the plain-text editions of every issue.

For each issues/NN.html this writes:
  issues/NN.txt        raw 72-column ASCII, 2600/Phrack style, links as footnotes
  issues/NN-text.html  calm reading page: no neon, no effects, follows light/dark

It also (idempotently) adds a "text version" link to each colour issue's top bar
and a plain-text line to the archive. Re-run after adding or editing an issue:

  python3 tools/textify.py
"""
import email.utils
import html
import re
import textwrap
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
ISSUES = SITE / "issues"
BASE = "https://makebreak.co.uk"
WIDTH = 72
BR = "\x0b"  # hard line break marker; source newlines are just soft wraps
COFFEE = "https://buymeacoffee.com/androidacid"

VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}
SKIP = {"script", "style", "canvas", "button", "label", "input", "svg"}


# --- a tiny DOM -------------------------------------------------------------

class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs or {}), parent, []

    @property
    def cls(self):
        return set(self.attrs.get("class", "").split())

    def find(self, tag=None, cls=None):
        for k in self.kids:
            if isinstance(k, Node):
                if (tag is None or k.tag == tag) and (cls is None or cls in k.cls):
                    return k
                hit = k.find(tag, cls)
                if hit:
                    return hit
        return None

    def text(self):
        return "".join(k if isinstance(k, str) else k.text() for k in self.kids)


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("#root")

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def parse(src):
    b = Builder()
    b.feed(src)
    return b.root


# --- issue metadata ---------------------------------------------------------

def feed_dates():
    """issue number -> '23 Sep 2026', from feed.xml pubDates."""
    feed = (SITE / "feed.xml").read_text()
    out = {}
    for num, date in re.findall(r"issues/(\d+)\.html</link>.*?<pubDate>(.*?)</pubDate>", feed, re.S):
        d = email.utils.parsedate_to_datetime(date)
        out[num] = f"{d.day} {d:%b %Y}"
    return out


def meta(root, num):
    header = root.find("header", "issue")
    return {
        "num": num,
        "title": " ".join(header.find("h1").text().split()),
        "dek": " ".join(header.find("p", "dek").text().split()),
        "side": " ".join(header.find("span", "badge").text().split()).upper(),
    }


# --- inline rendering -------------------------------------------------------

def absolute(href):
    if href.startswith(("http://", "https://", "mailto:")):
        return href
    if href.startswith("/"):
        return BASE + href
    return f"{BASE}/issues/{href}"


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


ASCII = {
    "—": "--", "–": "-", "→": "->", "←": "<-", "↓": "", "↺": "", "▚": "", "☕": "",
    "·": "-", "×": "x", "°": " deg", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
}


def asciify(s):
    for k, v in ASCII.items():
        s = s.replace(k, v)
    return s


class TxtInline:
    """Flattens inline markup to plain text, collecting links as footnotes."""

    def __init__(self, notes):
        self.notes = notes

    def note(self, url):
        if url not in self.notes:
            self.notes.append(url)
        return self.notes.index(url) + 1

    def __call__(self, node):
        out = []
        for k in node.kids:
            if isinstance(k, str):
                out.append(k)
            elif k.tag in SKIP:
                continue
            elif k.tag == "a":
                label = self(k).strip()
                n = self.note(absolute(k.attrs.get("href", "")))
                out.append(f"{label} [{n}]")
            elif k.tag == "br":
                out.append(BR)
            else:
                out.append(self(k))
        return "".join(out)


def html_inline(node, rewrite=None):
    """Re-emits inline markup, keeping only semantic tags."""
    out = []
    for k in node.kids:
        if isinstance(k, str):
            out.append(html.escape(k, quote=False))
        elif k.tag in SKIP:
            continue
        elif k.tag == "a":
            href = k.attrs.get("href", "")
            if rewrite:
                href = rewrite(href)
            out.append(f'<a href="{html.escape(href)}">{html_inline(k, rewrite)}</a>')
        elif k.tag in ("strong", "b"):
            out.append(f"<strong>{html_inline(k, rewrite)}</strong>")
        elif k.tag in ("em", "i"):
            out.append(f"<em>{html_inline(k, rewrite)}</em>")
        elif k.tag == "code":
            out.append(f"<code>{html.escape(k.text(), quote=False)}</code>")
        elif k.tag == "br":
            out.append("<br>")
        else:
            out.append(html_inline(k, rewrite))
    return "".join(out)


# --- block walk -------------------------------------------------------------
# Blocks: ("h2", node) ("h3", node) ("p", node) ("pre", text)
#         ("card", [blocks]) ("demo", kind) ("nav", node)

def blocks(node):
    out = []
    for k in node.kids:
        if not isinstance(k, Node) or k.tag in SKIP:
            continue
        c = k.cls
        if k.tag == "h2":
            out.append(("h2", k))
        elif k.tag == "h3":
            out.append(("h3", k))
        elif k.tag == "pre":
            out.append(("pre", k.text().strip("\n")))
        elif k.tag == "p":
            out.append(("p", k))
        elif k.tag == "a":  # a standalone link, e.g. the patch download
            p = Node("p", parent=node)
            p.kids.append(k)
            out.append(("p", p))
        elif "demo" in c:
            out.append(("demo", "listen" if k.find("audio") else "demo"))
        elif "card" in c or "tip" in c:
            out.append(("card", blocks(k)))
        elif "sub" in c:
            continue  # replaced by a fixed sign-off
        elif k.tag == "nav":
            out.append(("nav", k))
        else:
            out.extend(blocks(k))
    return out


def heading_text(node):
    parts = []
    for k in node.kids:
        if isinstance(k, str):
            parts.append(k)
        elif "ph" in k.cls:
            continue
        elif "n" in k.cls:
            parts.append(k.text().strip() + ". ")
        else:
            parts.append(k.text())
    return squash("".join(parts))


def project_name(node):
    """'The project — fold the light' -> 'fold the light'."""
    return re.sub(r"^the project\s*[—–:-]+\s*", "", heading_text(node), flags=re.I)


def section_title(node):
    t = heading_text(node)
    return "the project" if "proj" in node.cls else t


# --- .txt renderer ----------------------------------------------------------

def wrap(s, indent="", first=None):
    first = indent if first is None else first
    paras = [squash(p) for p in s.split(BR)]
    lines = []
    for p in paras:
        lines += textwrap.wrap(p, WIDTH, initial_indent=first, subsequent_indent=indent,
                               break_long_words=False, break_on_hyphens=False) or [""]
        first = indent
    return "\n".join(lines)


def render_txt(m, date, bl):
    notes = []
    inl = TxtInline(notes)
    rule, thin = "=" * WIDTH, "-" * WIDTH
    title_line = f"  issue #{m['num']}"
    head = [
        rule,
        "  MAKE / BREAK".ljust(WIDTH - len(title_line)) + title_line,
        f"  {asciify(m['title']).upper()}",
        f"  {m['side']} - {date} - by the Norfolk Hacker",
        rule,
        "",
        wrap(asciify(m["dek"]), "  "),
        "",
        f"  colour edition: {BASE}/issues/{m['num']}.html",
        "",
    ]
    body, sec = [], 0

    def para(node, indent="", first=None):
        return wrap(asciify(inl(node)), indent, first)

    def emit(b, indent=""):
        kind, x = b
        if kind == "h2":
            nonlocal sec
            sec += 1
            body.extend([thin, f"[ {sec}. {asciify(section_title(x)).upper()} ]", ""])
            if "proj" in x.cls:
                body.extend([wrap(asciify(project_name(x))).upper(), ""])
        elif kind == "h3":
            body.extend([f"{indent}>> {asciify(heading_text(x))}", ""])
        elif kind == "p":
            body.extend([para(x, indent), ""])
        elif kind == "pre":
            body.extend([textwrap.indent(x, indent + "    ", lambda _: True), ""])
        elif kind == "demo":
            url = f"{BASE}/issues/{m['num']}.html"
            if x == "listen":
                url = f"{BASE}/issues/seq.wav"
            body.extend([f"{indent}    [ {'listen' if x == 'listen' else 'live demo'}: {url} ]", ""])
        elif kind == "card":
            for i, sub in enumerate(x):
                if sub[0] == "p" and i == 0:
                    body.extend([para(sub[1], indent + "   ", indent + " * "), ""])
                else:
                    emit(sub, indent + "   ")

    for b in bl:
        if b[0] != "nav":
            emit(b)

    nav = [b[1] for b in bl if b[0] == "nav"]
    foot = [thin, "",
            wrap("A new one every other week -- free, no signup needed:"),
            f"  {BASE}/issues/", "",
            wrap("No paywall, no ads, no sponsor telling me what to say. If an issue earned "
                 f"you a brew: {COFFEE}"),
            "", "  -- the Norfolk Hacker", ""]
    if nav:
        links = [a for a in nav[0].kids if isinstance(a, Node) and a.tag == "a"]
        for a in links:
            href = a.attrs["href"]
            if re.fullmatch(r"\d+\.html", href):
                label = squash(a.text())
                way = "prev" if label.startswith("←") else "next"
                label = squash(label.strip("←→"))
                foot.append(f"  {way}: {asciify(label)}")
                foot.append(f"        {BASE}/issues/{href[:-5]}.txt")
        foot.append("")
    if notes:
        foot += [thin, "LINKS", ""] + [f"[{i}] {u}" for i, u in enumerate(notes, 1)] + [""]
    foot.append(rule)
    return "\n".join(head + body + foot) + "\n"


# --- -text.html renderer ----------------------------------------------------

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Issue #{num} — {title} (text edition)</title>
<meta name="description" content="Plain-text edition of MAKE / BREAK #{num}: no bright colours, no effects.">
<link rel="canonical" href="{base}/issues/{num}.html">
<link rel="alternate" type="text/plain" href="{num}.txt">
<link rel="alternate" type="application/rss+xml" title="MAKE / BREAK" href="/feed.xml">
<style>
  :root{{--bg:#fbfaf6;--ink:#1c1c1a;--muted:#4d4d48;--line:#d8d6cf;--code:#f0eee8;--link:#1d3f8f}}
  @media (prefers-color-scheme: dark){{
    :root{{--bg:#161616;--ink:#dcdcd6;--muted:#a9a9a2;--line:#353533;--code:#222221;--link:#9fbcf5}}
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font:1.1rem/1.65 Georgia,"Iowan Old Style","Times New Roman",serif}}
  main,nav.top{{max-width:68ch;margin:0 auto;padding:0 16px}}
  nav.top{{padding-block:14px;border-bottom:1px solid var(--line);font:0.95rem/1.5 system-ui,sans-serif;color:var(--muted);max-width:none}}
  nav.top div{{max-width:calc(68ch - 32px);margin:0 auto;display:flex;flex-wrap:wrap;gap:6px 18px}}
  a{{color:var(--link);text-underline-offset:2px}}
  h1{{font-size:2rem;line-height:1.2;margin:36px 0 6px}}
  .meta{{color:var(--muted);font:0.95rem/1.5 system-ui,sans-serif;margin:0 0 18px}}
  h2{{font-size:1.4rem;margin:44px 0 10px;padding-top:18px;border-top:1px solid var(--line)}}
  h3{{font-size:1.15rem;margin:30px 0 8px}}
  .item{{border-left:3px solid var(--line);padding-left:16px;margin:18px 0}}
  .item p:first-child{{margin-top:0}}
  code,pre{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:0.92em}}
  code{{background:var(--code);padding:1px 4px;border-radius:3px}}
  pre{{background:var(--code);padding:14px 16px;overflow-x:auto;border-radius:4px;line-height:1.5}}
  pre code{{background:none;padding:0}}
  .demo{{color:var(--muted);font-style:italic}}
  footer{{margin:48px 0;padding-top:18px;border-top:1px solid var(--line)}}
  footer nav{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;font-family:system-ui,sans-serif;font-size:0.95rem}}
</style>
</head>
<body>
<nav class="top"><div><a href="/">MAKE / BREAK</a><a href="/issues/text.html">all text editions</a><a href="{num}.html">colour edition</a><a href="{num}.txt">raw .txt</a></div></nav>
<main>
<h1>#{num} — {title}</h1>
<p class="meta">{side} · {date} · by the Norfolk Hacker</p>
<p><em>{dek}</em></p>
{body}
<footer>
<p>A new one every other week — free, no signup needed. Rather it came to you? <a href="/#join">Email</a> or <a href="/feed.xml">RSS</a>.</p>
<p>No paywall, no ads, no sponsor telling me what to say. If an issue earned you a brew, <a href="{coffee}">buy me a coffee</a>.</p>
<p>— the Norfolk Hacker</p>
{nav}
</footer>
</main>
</body>
</html>
"""


def to_text_page(href):
    return re.sub(r"^(\d+)\.html$", r"\1-text.html", href)


def render_html(m, date, bl):
    out = []

    def emit(b):
        kind, x = b
        if kind == "h2":
            name = f"The project: {project_name(x)}" if "proj" in x.cls else section_title(x).capitalize()
            out.append(f"<h2>{html.escape(name)}</h2>")
        elif kind == "h3":
            out.append(f"<h3>{html.escape(heading_text(x))}</h3>")
        elif kind == "p":
            out.append(f"<p>{squash(html_inline(x, to_text_page))}</p>")
        elif kind == "pre":
            out.append(f"<pre><code>{html.escape(x, quote=False)}</code></pre>")
        elif kind == "demo":
            if x == "listen":
                out.append('<p class="demo">[Audio: <a href="seq.wav">listen to the sequencer</a>.]</p>')
            else:
                out.append(f'<p class="demo">[Live demo: the <a href="{m["num"]}.html">colour edition</a> '
                           "runs this in your browser. The full code is below.]</p>")
        elif kind == "card":
            out.append('<div class="item">')
            for sub in x:
                emit(sub)
            out.append("</div>")

    for b in bl:
        if b[0] != "nav":
            emit(b)

    nav = ""
    for b in bl:
        if b[0] == "nav":
            links = []
            for a in b[1].kids:
                if isinstance(a, Node) and a.tag == "a":
                    href = a.attrs["href"]
                    href = "/issues/text.html" if href == "/issues/" else to_text_page(href)
                    links.append(f'<a href="{html.escape(href)}">{html.escape(squash(a.text()))}</a>')
            nav = "<nav>" + "".join(links) + "</nav>"

    e = html.escape
    return PAGE.format(num=m["num"], title=e(m["title"]), dek=e(m["dek"]), side=m["side"],
                       date=date, body="\n".join(out), nav=nav, base=BASE, coffee=COFFEE)


# --- text archive + links into the colour site -----------------------------

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MAKE / BREAK — text editions</title>
<meta name="description" content="Every MAKE / BREAK issue as plain text: no bright colours, no effects.">
<style>
  :root{{--bg:#fbfaf6;--ink:#1c1c1a;--muted:#4d4d48;--line:#d8d6cf;--link:#1d3f8f}}
  @media (prefers-color-scheme: dark){{:root{{--bg:#161616;--ink:#dcdcd6;--muted:#a9a9a2;--line:#353533;--link:#9fbcf5}}}}
  body{{margin:0;background:var(--bg);color:var(--ink);font:1.1rem/1.65 Georgia,"Times New Roman",serif}}
  main{{max-width:68ch;margin:0 auto;padding:24px 16px 48px}}
  a{{color:var(--link);text-underline-offset:2px}}
  h1{{font-size:2rem;line-height:1.2}}
  .muted{{color:var(--muted)}}
  li{{margin:14px 0}}
  .fmt{{font-family:system-ui,sans-serif;font-size:0.9rem}}
</style>
</head>
<body>
<main>
<p class="fmt"><a href="/">MAKE / BREAK</a> · <a href="/issues/">colour archive</a></p>
<h1>Text editions</h1>
<p>Every issue with the neon switched off: plain words, readable type, and it follows your light or dark setting.
Prefer it raw? Each one is also a 72-column <code>.txt</code>, nice for <code>curl</code> and old habits.</p>
<ul>
{rows}
</ul>
<p class="muted">— the Norfolk Hacker</p>
</main>
</body>
</html>
"""


def inject(path, marker, snippet, anchor_re):
    """Place snippet between <!--marker--> comments, replacing any previous copy."""
    src = path.read_text()
    block = f"<!--{marker}-->{snippet}<!--/{marker}-->"
    if f"<!--{marker}-->" in src:
        src = re.sub(rf"<!--{marker}-->.*?<!--/{marker}-->", lambda _: block, src, flags=re.S)
    else:
        src, n = re.subn(anchor_re, lambda mo: mo.group(0) + block, src, count=1, flags=re.S)
        assert n, f"{path.name}: couldn't find where to add the {marker} link"
    path.write_text(src)


def main():
    dates = feed_dates()
    metas = []
    for f in sorted(ISSUES.glob("[0-9][0-9].html")):
        num = f.stem
        root = parse(f.read_text())
        m = meta(root, num)
        date = dates.get(num, "")
        bl = blocks(root.find("article"))
        (ISSUES / f"{num}.txt").write_text(render_txt(m, date, bl))
        (ISSUES / f"{num}-text.html").write_text(render_html(m, date, bl))
        inject(f, "tx", f' · <a href="{num}-text.html">text version</a>',
               r'<span class="barmeta">[^<]*')
        metas.append((m, date))
        print(f"  #{num}  {num}.txt  {num}-text.html")

    rows = "\n".join(
        f'<li><a href="{m["num"]}-text.html">#{m["num"]} — {html.escape(m["title"])}</a>'
        f' <span class="fmt muted">· {date} · <a href="{m["num"]}.txt">.txt</a></span></li>'
        for m, date in reversed(metas))
    (ISSUES / "text.html").write_text(INDEX.format(rows=rows))
    inject(ISSUES / "index.html", "tx",
           '\n  <p class="dek">Bright colours not your thing? '
           '<a href="text.html">Every issue as plain text →</a></p>',
           r'<div class="list">.*?\n  </div>')


if __name__ == "__main__":
    main()
