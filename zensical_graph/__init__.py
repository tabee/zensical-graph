"""
Zensical Graph Plugin
Generates an interactive force-directed graph view of documentation links
(Obsidian-style) for Zensical / MkDocs-compatible sites.

Zensical (<= 0.0.72) has no API for third-party plugins yet: unknown entries
under [project.plugins] are ignored silently. Therefore the graph is built by
a post-build step:

    zensical build -f zensical.toml
    python -m zensical_graph -f zensical.toml

With MkDocs the class GraphPlugin still works as a regular plugin.

Embedded mode: if the site already has a page at `page_path` (e.g. a
Markdown page `graph.md` with `use_directory_urls`) that contains
`<div id="zensical-graph"></div>`, the graph is injected into that page, so it
keeps the theme's header, navigation, search and footer. Otherwise a
standalone page is written (as before).
"""

from __future__ import annotations

import html
import json
import posixpath
import re
from pathlib import Path
from typing import Any

__all__ = ["DEFAULTS", "GraphPlugin", "build_graph", "write_graph"]

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "page_path": "graph/",
    "title": "Knowledge Graph",
    "min_links": 0,
    "include_orphans": True,
    # Also count plain mentions of another page's file name (e.g. `docs/x.md`
    # in a code span) as a link. Off by default: real Markdown links only.
    "mentions": False,
    # UI language of the controls ("en", "de"). Empty: the theme language
    # (theme.language), falling back to English.
    "language": "",
}

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "search": "Filter pages…",
        "local": "Local graph on click",
        "min": "Min. links",
        "reset": "Show all",
        "legend": "Node size = number of links · Hover: highlight neighbours · "
                  "Click: local graph, click again: open page · Scroll: zoom",
        "noscript": "The graph needs JavaScript.",
        "link": "link",
        "links": "links",
    },
    # de-CH friendly: no sharp s
    "de": {
        "search": "Seiten filtern …",
        "local": "Lokaler Graph beim Klick",
        "min": "Min. Verweise",
        "reset": "Alles zeigen",
        "legend": "Knotengrösse = Anzahl Verweise · Maus darüber: Nachbarn hervorheben · "
                  "Klick: lokaler Graph, nochmals klicken: Seite öffnen · Mausrad: Zoom",
        "noscript": "Der Graph braucht JavaScript.",
        "link": "Verweis",
        "links": "Verweise",
    },
}

MARKER_ID = "zensical-graph"
_MARKER = re.compile(r'<div\b[^>]*\bid="' + MARKER_ID + r'"[^>]*>.*?</div>', re.S)
_ASSETS = Path(__file__).parent / "assets"

# Pinned frontend library with Subresource Integrity (no floating CDN version).
FORCE_GRAPH_URL = "https://unpkg.com/force-graph@1.52.0/dist/force-graph.min.js"
FORCE_GRAPH_SRI = "sha384-isW4dF8tfo3t+I2iiIdnz1MFV+hW1Vn3YyY2PmAgPbRQaW7Biahepz8fTRR+nLxm"

_FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.M | re.S)
_INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_REF_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", re.M)
_MENTION = re.compile(r"[A-Za-z0-9_./-]+\.md\b")
_H1 = re.compile(r"^#[ \t]+(.+?)[ \t#]*$", re.M)
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n(?:---|\.\.\.)\s*\n", re.S)


def _page_url(src: str, use_directory_urls: bool) -> str:
    """Site-relative URL of a page, like Zensical/MkDocs build it."""
    stem = posixpath.splitext(src)[0]
    parent, name = posixpath.split(stem)
    if name.lower() in ("index", "readme"):
        return parent + "/" if parent else ""
    if use_directory_urls:
        return stem + "/"
    return stem + ".html"


def _title(text: str, src: str) -> str:
    fm = _FRONT_MATTER.match(text)
    if fm:
        m = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", fm.group(1), re.M)
        if m:
            return m.group(1)
        text = text[fm.end():]
    m = _H1.search(_FENCE.sub("", text))
    if m:
        return m.group(1).strip()
    stem = Path(src).stem
    if stem.lower() in ("index", "readme"):
        stem = Path(src).parent.name or "Home"
    return stem.replace("-", " ").replace("_", " ").title()


def _collect_pages(docs_dir: Path, use_directory_urls: bool) -> list[dict]:
    pages = []
    for md in sorted(docs_dir.rglob("*.md")):
        src = md.relative_to(docs_dir).as_posix()
        if any(part.startswith(".") for part in Path(src).parts):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        pages.append(
            {
                "src": src,
                "url": _page_url(src, use_directory_urls),
                "title": _title(text, src),
                "text": text,
            }
        )
    return pages


def _link_targets(page: dict, by_src: dict[str, dict], mentions: bool) -> set[str]:
    """Source paths of all pages this page links to."""
    body = _FENCE.sub("", page["text"])
    base = posixpath.dirname(page["src"])
    found: set[str] = set()
    for href in _INLINE_LINK.findall(body) + _REF_LINK.findall(body):
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("#"):
            continue  # external link or same-page anchor
        path = href.split("#", 1)[0].split("?", 1)[0]
        if not path.endswith(".md"):
            continue
        target = posixpath.normpath(posixpath.join(base, path)).lstrip("/")
        if target in by_src:
            found.add(target)
    if mentions:
        for name in set(_MENTION.findall(page["text"])):
            name = name.lstrip("./")
            # unique path-suffix match in both directions: "docs/x.md" matches
            # "ansible/docs/x.md" and, with docs_dir = docs, also "x.md"
            hits = [s for s in by_src
                    if s == name or s.endswith("/" + name) or name.endswith("/" + s)]
            if len(hits) == 1:
                found.add(hits[0])
    found.discard(page["src"])
    return found


def _group_from_path(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if len(parts) > 1 else "root"


def nav_titles(nav: Any) -> dict[str, str]:
    """Page titles from a MkDocs/Zensical `nav` ({"Title": "page.md"} entries)."""
    titles: dict[str, str] = {}
    def walk(items: Any) -> None:
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                for title, target in item.items():
                    if isinstance(target, str) and target.endswith(".md"):
                        titles.setdefault(target.removeprefix("./"), str(title))
                    else:
                        walk(target)
    walk(nav)
    return titles


def build_graph(docs_dir: Path, options: dict, use_directory_urls: bool = True,
                titles: dict[str, str] | None = None) -> dict:
    """Nodes (pages) and links (page -> page) as plain data.

    The Markdown page that hosts the graph (URL = page_path) is no node.
    Node titles: `titles` (e.g. from nav) first, then front matter / H1.
    """
    titles = titles or {}
    host = str(options.get("page_path", DEFAULTS["page_path"])).strip("/")
    pages = [p for p in _collect_pages(Path(docs_dir), use_directory_urls)
             if p["url"].strip("/").removesuffix(".html") != host]
    by_src = {p["src"]: p for p in pages}
    links = []
    degree: dict[str, int] = {}
    for page in pages:
        for target in sorted(_link_targets(page, by_src, bool(options["mentions"]))):
            src, dst = "/" + page["url"], "/" + by_src[target]["url"]
            links.append({"source": src, "target": dst})
            degree[src] = degree.get(src, 0) + 1
            degree[dst] = degree.get(dst, 0) + 1
    nodes = [
        {
            "id": "/" + p["url"],
            "title": titles.get(p["src"], p["title"]),
            "url": p["url"],
            "path": p["src"],
            "group": _group_from_path(p["src"]),
            "size": max(1, degree.get("/" + p["url"], 0)),
            "degree": degree.get("/" + p["url"], 0),
        }
        for p in pages
        if options["include_orphans"] or degree.get("/" + p["url"], 0) > 0
    ]
    return {"nodes": nodes, "links": links}


def _language(opts: dict, theme_language: str | None) -> str:
    lang = str(opts.get("language") or theme_language or "en").lower()
    lang = lang.replace("_", "-").split("-")[0]
    return lang if lang in TEXTS else "en"


def write_graph(docs_dir: Path, site_dir: Path, options: dict | None = None,
                use_directory_urls: bool = True,
                theme_language: str | None = None,
                nav: Any = None) -> Path | None:
    """Write <site>/<page_path>/graph.json and the graph page.

    Embedded into an existing page with <div id="zensical-graph"></div>,
    else a standalone <site>/<page_path>/index.html.
    """
    opts = {**DEFAULTS, **(options or {})}
    if not opts["enabled"]:
        return None
    page_path = str(opts["page_path"]).strip("/") or "graph"
    data = build_graph(Path(docs_dir), opts, use_directory_urls, nav_titles(nav))
    out_dir = Path(site_dir) / page_path
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "graph.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    lang = _language(opts, theme_language)

    candidates = [(out_dir / "index.html", "../" * len(page_path.split("/")))]
    if not use_directory_urls:
        candidates.append((Path(site_dir) / (page_path + ".html"),
                           "../" * (len(page_path.split("/")) - 1)))
    for page, root in candidates:
        if page.is_file():
            text = page.read_text(encoding="utf-8")
            if _MARKER.search(text):
                widget = _widget(data, root, opts, lang)
                page.write_text(_MARKER.sub(lambda _m: widget, text, count=1), encoding="utf-8")
                return out_dir
    root = "../" * len(page_path.split("/"))
    _write_standalone(out_dir, str(opts["title"]), _widget(data, root, opts, lang), lang)
    return out_dir


def _widget(data: dict, root: str, opts: dict, lang: str) -> str:
    """Container, controls, data and script: one self-contained HTML block.

    Everything is inline, so Zensical's instant navigation (which re-runs the
    scripts of the new page content) initialises the graph as well.
    """
    t = TEXTS[lang]
    esc = html.escape
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    css = (_ASSETS / "graph.css").read_text(encoding="utf-8")
    js = (_ASSETS / "graph.js").read_text(encoding="utf-8")
    min_links = int(opts["min_links"])
    attrs = {
        "data-root": root,
        "data-lib": FORCE_GRAPH_URL,
        "data-sri": FORCE_GRAPH_SRI,
        "data-min": str(min_links),
        "data-text": json.dumps({"link": t["link"], "links": t["links"]}),
    }
    attr = " ".join(f'{k}="{esc(v, quote=True)}"' for k, v in attrs.items())
    return f"""<div class="zg" id="{MARKER_ID}" data-zg {attr}>
<style>{css}</style>
<div class="zg-controls">
<input class="zg-search" type="search" placeholder="{esc(t['search'])}" aria-label="{esc(t['search'])}">
<label><input class="zg-local" type="checkbox" checked> {esc(t['local'])}</label>
<label>{esc(t['min'])} <input class="zg-min" type="number" min="0" value="{min_links}"></label>
<button class="zg-reset" type="button">{esc(t['reset'])}</button>
</div>
<div class="zg-canvas"></div>
<p class="zg-legend">{esc(t['legend'])}</p>
<noscript><p>{esc(t['noscript'])}</p></noscript>
<script type="application/json" class="zg-data">{payload}</script>
<script>{js}</script>
</div>"""


def _write_standalone(out_dir: Path, title: str, widget: str, lang: str) -> None:
    title = html.escape(title)
    page = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <style>
    html, body {{ margin: 0; background: #0f1115; color: #e6e6e6; font-family: system-ui, sans-serif; }}
    main {{ padding: 12px 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 1.2rem; font-weight: 600; }}
    h1 a {{ color: inherit; }}
    .zg {{ font-size: 16px; }}
    .zg-canvas {{ height: calc(100vh - 150px); }}
  </style>
</head>
<body>
<main>
  <h1><a href="../">{title}</a></h1>
  {widget}
</main>
</body>
</html>
"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")


try:  # MkDocs: regular plugin (Zensical ignores it, see module docstring)
    from mkdocs.config import config_options as _c
    from mkdocs.plugins import BasePlugin as _MkDocsBasePlugin
except ImportError:  # pragma: no cover - no MkDocs installed
    _MkDocsBasePlugin = None

if _MkDocsBasePlugin is not None:

    class GraphPlugin(_MkDocsBasePlugin):
        """MkDocs plugin: writes the graph after the build."""

        config_scheme = (
            ("enabled", _c.Type(bool, default=True)),
            ("page_path", _c.Type(str, default="graph/")),
            ("title", _c.Type(str, default="Knowledge Graph")),
            ("min_links", _c.Type(int, default=0)),
            ("include_orphans", _c.Type(bool, default=True)),
            ("mentions", _c.Type(bool, default=False)),
            ("language", _c.Type(str, default="")),
        )

        def on_post_build(self, config: Any, **kwargs: Any) -> None:
            write_graph(
                Path(config["docs_dir"]),
                Path(config["site_dir"]),
                dict(self.config),
                bool(config.get("use_directory_urls", True)),
                (config.get("theme") or {}).get("language"),
                config.get("nav"),
            )

else:

    class GraphPlugin:  # type: ignore[no-redef]
        """Placeholder without MkDocs; use `python -m zensical_graph`."""

        def __init__(self) -> None:
            self.config = dict(DEFAULTS)

        def on_post_build(self, config: dict, **kwargs: Any) -> None:
            write_graph(Path(config["docs_dir"]), Path(config["site_dir"]), self.config,
                        bool(config.get("use_directory_urls", True)))
