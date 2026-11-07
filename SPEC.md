# Implementation Spec: Zensical Knowledge Graph Plugin

**Version:** 0.2.0  
**Target:** Zensical ≥ 0.0.70 (compatible with MkDocs plugin system)  
**Deployment:** GitOps / Argo CD – static assets generated at build time

## 1. Goal

Provide an Obsidian-like interactive force-directed graph view of a Zensical documentation site. The graph must be generated during the normal `zensical build` step so that the resulting static files can be served by any GitOps-managed deployment (Argo CD → container or static host).

## 2. Non-Goals

- Real-time collaboration or live editing of the graph
- Server-side graph database
- Full 3D mode in the first version (possible later)

## 3. Architecture

```
zensical build
    │
    ▼
GraphPlugin.on_post_build()
    │
    ├─ Collect pages (from docs_dir or project model)
    ├─ Extract / approximate links
    ├─ Write site/graph/graph.json
    └─ Embedded page with <div id="zensical-graph"></div>?
         ├─ yes: replace placeholder with the inline widget
         └─ no:  write stand-alone site/graph/index.html
         │
         ▼
Argo CD syncs the built site (or the container that serves it)
         │
         ▼
Browser loads /graph/ → force-graph renders interactive network
```

## 4. Plugin Interface

The plugin registers via entry points:

- `zensical.plugins` → `graph = zensical_graph:GraphPlugin`
- `mkdocs.plugins` → `graph = zensical_graph:GraphPlugin` (compatibility)

It implements `on_post_build` (or the equivalent Zensical hook when the stable module API lands).

### Configuration

| Key              | Type   | Default          | Description                          |
|------------------|--------|------------------|--------------------------------------|
| enabled          | bool   | true             | Enable/disable the plugin            |
| page_path        | str    | "graph/"         | Output path under site_dir           |
| title            | str    | "Knowledge Graph"| Page title                           |
| min_links        | int    | 0                | Hide nodes with fewer connections    |
| include_orphans  | bool   | true             | Show pages with zero links           |
| mentions         | bool   | false            | Count file-name mentions as links    |
| language         | str    | ""               | UI language (en, de); empty = theme language, fallback en |

## 5. Graph Data Format (`graph.json`)

```json
{
  "nodes": [
    {
      "id": "/guides/getting-started/",
      "title": "Getting Started",
      "url": "guides/getting-started/",
      "path": "guides/getting-started.md",
      "group": "guides",
      "size": 7
    }
  ],
  "links": [
    { "source": "/", "target": "/guides/getting-started/" }
  ]
}
```

- `size` = degree (number of connections). Frontend multiplies for visual weight.
- `group` = first path segment (used for coloring).

## 6. Frontend Behavior

- Library: `force-graph` (CDN or vendored)
- Node size ∝ connection count
- Node color by group (deterministic hash → palette)
- Search box filters nodes by title/path
- “Local graph on click” shows only the selected node + its neighbors
- Click navigates to the page (when local mode is off)
- Dark theme, minimal UI overlay
- Labels below the nodes at constant screen size; they fade out when zoomed
  out (threshold grows with the number of visible nodes); hovered node and
  neighbours always labelled
- Embedded mode (0.2): placeholder `<div id="zensical-graph"></div>` in the
  page at `page_path` is replaced by the widget; must survive instant
  navigation (idempotent init, teardown on `document$`)
- Mentions match in both directions: `docs/x.md` matches page `x.md` and
  vice versa (docs_dir below the repo root)
- Node titles: `nav` title > front matter `title` > first `# H1`

## 7. GitOps Integration

### Recommended layout in the documentation repository

```
docs-repo/
├── docs/
├── zensical.toml
├── pyproject.toml          # or requirements.txt
└── plugins/                # optional local copy
    └── zensical-graph/
```

### Argo CD Application (example)

The documentation build can be:

1. A container image that runs `zensical build` in CI and serves the `site/` directory, or
2. A job/pipeline that builds and pushes the static site to the deployment target.

In both cases the plugin is installed at build time (`pip install` from private Git or local path). No runtime dependency is introduced.

### Private Git install example

```toml
# pyproject.toml of the docs project
[project]
dependencies = [
  "zensical",
  "zensical-graph @ git+https://github.com/tabee/zensical-graph.git@v0.1.0",
]
```

## 8. Future Improvements

- Use the official Zensical project model / module API for accurate link extraction (instead of best-effort scanning).
- Support tags and front-matter for coloring and filtering.
- Optional 3D mode (`3d-force-graph`).
- Local graph panel on every page (Obsidian-style).
- Vendor the force-graph library for fully offline builds.

## 9. Security & Performance

- Pure static output – no additional attack surface at runtime.
- Graph is generated only at build time.
- Large sites: force-graph handles several thousand nodes; for very large sites add pagination or “local-only” default.

## 10. License

MIT – same as Zensical.
