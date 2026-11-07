"""Post-build step for Zensical: python -m zensical_graph [-f zensical.toml].

Reads docs_dir, site_dir, use_directory_urls and [project.plugins.graph]
from the same config file as `zensical build`. Relative paths are resolved
against the directory of the config file (like Zensical does).
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from . import DEFAULTS, write_graph


def _load(config_file: Path) -> tuple[dict, dict]:
    if config_file.suffix == ".toml":
        project = tomllib.loads(config_file.read_text(encoding="utf-8")).get("project", {})
    else:
        import yaml  # mkdocs.yml (PyYAML comes with Zensical/MkDocs)

        project = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    plugins = project.get("plugins", {})
    options: dict = {}
    if isinstance(plugins, dict):
        options = plugins.get("graph") or {}
    else:  # list form: ["graph"] or [{"graph": {...}}]
        for entry in plugins:
            if isinstance(entry, dict) and "graph" in entry:
                options = entry["graph"] or {}
    unknown = set(options) - set(DEFAULTS)
    if unknown:
        raise SystemExit(f"zensical_graph: unknown option(s): {', '.join(sorted(unknown))}")
    return project, {**DEFAULTS, **options}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zensical_graph", description=__doc__)
    parser.add_argument("-f", "--config-file", default="zensical.toml")
    args = parser.parse_args(argv)
    config_file = Path(args.config_file).resolve()
    project, options = _load(config_file)
    base = config_file.parent
    docs_dir = base / project.get("docs_dir", "docs")
    site_dir = base / project.get("site_dir", "site")
    if not docs_dir.is_dir() or not site_dir.is_dir():
        print(f"zensical_graph: {docs_dir} or {site_dir} missing (run zensical build first)",
              file=sys.stderr)
        return 1
    theme = project.get("theme") or {}
    out = write_graph(docs_dir, site_dir, options, bool(project.get("use_directory_urls", True)),
                      theme.get("language") if isinstance(theme, dict) else None,
                      project.get("nav"))
    if out is None:
        print("zensical_graph: disabled (enabled = false)")
    else:
        print(f"zensical_graph: wrote {out.relative_to(base)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
