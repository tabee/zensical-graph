# Zensical Graph Plugin

Obsidian-style interactive force-directed knowledge graph for Zensical (and MkDocs-compatible) documentation sites.

## Features

- Force-directed graph of all documentation pages
- Node size based on number of connections (degree)
- Color by top-level folder / group
- Search / filter nodes
- Local graph on click (neighbors only)
- Click node to navigate to the page
- Page names drawn below the nodes (fade out when zoomed out)
- **Embedded mode:** the graph sits inside a normal page of your site
  (header, navigation, search stay), works with instant navigation
- Colours from CSS variables (`--zg-*`), defaults follow the theme
- UI in English or German (`language`, default: theme language)
- Generated at build time → fully static, works behind Argo CD / GitOps

## Installation (GitOps / Argo CD friendly)

### Option A – pip install from your private Git

```toml
# In your documentation project's pyproject.toml or requirements
dependencies = [
  "zensical",
  "zensical-graph @ git+https://github.com/tabee/zensical-graph.git",
]
```

### Option B – Copy the files into your docs repo

1. Copy `zensical_graph/` into your project (or install as package).
2. Add to `zensical.toml` / `mkdocs.yml`:

```toml
[project]
plugins = [
  "graph",
]
```

or

```yaml
plugins:
  - graph
```

3. Optional configuration:

```toml
[project.plugins.graph]
enabled = true
page_path = "graph/"
title = "Knowledge Graph"
min_links = 0
include_orphans = true
mentions = false
language = ""        # "en" | "de"; empty = theme language, else English
```

### Embedded mode (recommended)

Create a normal page, e.g. `docs/graph.md`, put it in your `nav` and add the
placeholder where the graph should appear:

```markdown
---
hide: [toc]
---
# Knowledge Graph

<div id="zensical-graph"></div>
```

The page URL must match `page_path` (`graph.md` → `graph/`). After the build
the plugin replaces the placeholder with the graph widget (styles, controls,
canvas, data and script all inline), so the page keeps the theme layout and
also works with `navigation.instant` (the widget re-initialises on every
visit and cleans up when you navigate away). The host page itself is not a
node of the graph. Node labels use the `nav` titles if present, otherwise the
page title.

Without the placeholder (or without such a page) the plugin writes a
stand-alone page to `page_path`, as in 0.1.x.

Colours: override the CSS variables on `.zg`, e.g.

```css
[data-md-color-scheme="slate"] .zg {
  --zg-palette: #ff2bd6, #00e5ff, #9d4dff;  /* node colours */
  --zg-link: rgba(157, 77, 255, .35);
  --zg-link-active: #00e5ff;
  --zg-label: #f5e9ff;
  --zg-halo: #0d0718;                       /* outline around labels */
}
```

With one folder only, nodes are coloured by link count (hubs first colour),
otherwise by top-level folder.

With **MkDocs**, `mkdocs build` writes the page at `/graph/`.

With **Zensical** (tested with 0.0.72) the plugin is *not* executed: Zensical
has no API for third-party plugins yet and silently ignores unknown entries
under `[project.plugins]`. Run the graph as a post-build step instead; it
reads the same config file (`docs_dir`, `site_dir`, `[project.plugins.graph]`):

```sh
zensical build -f zensical.toml
python -m zensical_graph -f zensical.toml   # writes site/graph/
```

Note: in TOML use only the table form (`[project.plugins.search]`,
`[project.plugins.graph]`); a `plugins = [...]` list plus a
`[project.plugins.graph]` table is invalid TOML.

## How it works

1. After the build (MkDocs `on_post_build` or `python -m zensical_graph`) it
   collects all Markdown pages in `docs_dir` (title from front matter or the
   first `# H1`) and their relative Markdown links (`[x](other.md)`, reference
   links). With `mentions = true` a plain mention of another page's file name
   (e.g. `` `docs/setup.md` ``) counts as a link too.
2. It writes `graph.json` into `site/<page_path>` and either fills the
   placeholder of the embedded page or writes a self-contained `index.html`.
3. The frontend uses [force-graph](https://github.com/vasturiano/force-graph) (loaded from CDN, pinned version with Subresource Integrity) for the visualization.

## Extending

- Improve link extraction by walking the Zensical project model (when the stable module API is available).
- Add tags, front-matter based coloring, or 3D mode.
- Vendor `force-graph` instead of CDN if you want full offline builds.

## License

MIT
