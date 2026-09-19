#!/usr/bin/env python3
"""SwiftStore repo builder.

Scans apps/*/app.toml, queries the GitHub API for tags/releases, then
aggregates everything into dist/apps.json plus a minimal static frontend
and light/dark icon PNGs under dist/icons/.
"""

import json
import os
import re
from datetime import datetime, timezone
import shutil
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT / "apps"
DIST_DIR = ROOT / "dist"
ICONS_DIR = DIST_DIR / "icons"
GITHUB_API = "https://api.github.com"


def github_get(url: str) -> list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SwiftStore-Repo-Builder",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  [warn] GET {url} failed: HTTP {e.code}", file=sys.stderr)
        return []
    except urllib.error.URLError as e:
        print(f"  [warn] GET {url} failed: {e.reason}", file=sys.stderr)
        return []


def resolve_parameter(name: str, spec: dict, release: dict):
    """Resolve one [parameters.xxx] entry against a single release.

    Returns the variable's string value, or None when it cannot be resolved.
    """
    ptype = spec.get("type")
    if ptype == "source":
        source = spec.get("source")
        if source == "release.name":
            value = release.get("name")
        elif source == "tag.name":
            value = release.get("tag_name")
        else:
            print(f"  [warn] parameter {name}: unsupported source {source!r}", file=sys.stderr)
            return None
        regex = spec.get("regex")
        group = spec.get("group")
        if (regex is None) != (group is None):
            print(f"  [warn] parameter {name}: regex and group must appear together", file=sys.stderr)
        if regex is not None and group is not None:
            if value is None:
                return None
            m = re.search(regex, value)
            if not m:
                return None
            try:
                return m.group(group)
            except IndexError:
                return None
        return value
    if ptype == "predicated":
        predicate = spec.get("predicate")
        if predicate == "prerelease":
            value = release.get("prerelease")
        else:
            print(f"  [warn] parameter {name}: unsupported predicate {predicate!r}", file=sys.stderr)
            value = None
        if value is None:
            return spec.get("fallback")
        return spec.get("if_true") if value else spec.get("if_false")
    print(f"  [warn] parameter {name}: unsupported type {ptype!r}", file=sys.stderr)
    return None


def render_filename(template: str, parameters: dict, release: dict):
    """Fill {xxx} placeholders in the filename template from [parameters]."""
    if not parameters:
        return template
    variables = {}
    for name, spec in parameters.items():
        value = resolve_parameter(name, spec, release)
        if value is None:
            print(
                f"  [warn] release {release.get('tag_name')}: parameter {name} unresolved, skipped",
                file=sys.stderr,
            )
            return None
        variables[name] = value
    try:
        return template.format(**variables)
    except (KeyError, IndexError) as e:
        print(f"  [warn] filename template error: {e}", file=sys.stderr)
        return None


def collect_versions(repo: str, filename_template: str, parameters: dict) -> list:
    """Return [{name, size, created_at, url, prerelease}] for releases matching
    tags, resolving the asset filename per release via [parameters]."""
    tags = github_get(f"{GITHUB_API}/repos/{repo}/tags")
    tag_names = {t.get("name") for t in tags}

    releases = github_get(f"{GITHUB_API}/repos/{repo}/releases")
    versions = []
    for release in releases:
        if release.get("tag_name") not in tag_names:
            continue
        filename = render_filename(filename_template, parameters, release)
        if filename is None:
            continue
        for asset in release.get("assets", []):
            if asset.get("name") == filename:
                versions.append(
                    {
                        "name": release["tag_name"],
                        "size": asset.get("size"),
                        "created_at": asset.get("created_at"),
                        "url": asset.get("browser_download_url"),
                        "prerelease": bool(release.get("prerelease")),
                    }
                )
                break
    return versions


def copy_icons(app_dir: Path, icons: dict, app_id: str) -> None:
    """Copy light/dark icon PNGs into dist/icons/ as {id}_light.png / {id}_dark.png."""
    for variant in ("light", "dark"):
        name = icons.get(variant)
        src = app_dir / name if name else None
        if not src or not src.is_file():
            print(f"  [warn] {variant} icon not found: {src}", file=sys.stderr)
            continue
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        dst = ICONS_DIR / f"{app_id}_{variant}.png"
        shutil.copyfile(src, dst)
        print(f"  icon copied: {dst.relative_to(ROOT)}")


def main() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    apps = []
    for app_dir in sorted(p for p in APPS_DIR.iterdir() if p.is_dir()):
        toml_path = app_dir / "app.toml"
        if not toml_path.is_file():
            print(f"[skip] {app_dir.name}: no app.toml")
            continue
        print(f"[app] {app_dir.name}")
        with open(toml_path, "rb") as f:
            doc = tomllib.load(f)
        data = doc["app"]
        icons = doc.get("icon", {})

        app_id = data["id"]
        repo = data["repo"]
        versions = collect_versions(repo, data["filename"], doc.get("parameters", {}))
        print(f"  versions: {len(versions)}")

        apps.append(
            {
                "id": app_id,
                "name": data["name"],
                "description": data.get("description", ""),
                "authors": data.get("authors", []),
                "ai-assisted": data.get("ai-assisted", False),
                "repo": f"https://github.com/{repo}",
                "versions": versions,
            }
        )

        copy_icons(app_dir, icons, app_id)

    # GitHub-style UTC timestamp, e.g. 2026-09-19T04:36:11Z
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output = {"updated_at": updated_at, "apps": apps}
    with open(DIST_DIR / "apps.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"wrote {DIST_DIR / 'apps.json'} ({len(apps)} apps)")

    write_frontend()


def write_frontend() -> None:
    (DIST_DIR / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    print(f"wrote {DIST_DIR / 'index.html'}")


# GitHub Pages sets Content-Type by file extension, so the root path can only
# ever serve index.html as text/html. To make the site behave like a real API,
# the root page redirects immediately to apps.json (application/json).
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="0; url=apps.json">
  <title>SwiftStore Repo</title>
  <script>window.location.replace("apps.json");</script>
</head>
<body>
  <p>Redirecting to <a href="apps.json">apps.json</a>...</p>
</body>
</html>
"""


if __name__ == "__main__":
    main()
