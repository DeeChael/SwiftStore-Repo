#!/usr/bin/env python3

# 已完成人工重写

import json
import os
import re
from datetime import datetime, timezone
import shutil
import sys
import tomllib
import requests
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

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"  [warn] GET {url} failed: HTTP {status}", file=sys.stderr)
        return []
    except requests.RequestException as e:
        print(f"  [warn] GET {url} failed: {e}", file=sys.stderr)
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
    tags, resolving the asset filename per release via [parameters].
    Newest first."""
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
    versions.sort(key=lambda v: v.get("created_at") or "", reverse=True)
    return versions


def latest_version(versions: list):
    """Newest version overall, prereleases included."""
    return versions[0]["name"] if versions else None


def latest_release_version(versions: list):
    """Newest non-prerelease version, or None when every version is a prerelease."""
    for version in versions:
        if not version.get("prerelease"):
            return version["name"]
    return None


# Characters that cannot appear in a file name on Windows; POSIX is more
# permissive but the deployed gh-pages branch may be checked out anywhere.
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def version_filename(name: str) -> str:
    """Turn a version name into a portable file name stem."""
    cleaned = "".join("_" if c in INVALID_FILENAME_CHARS or ord(c) < 32 else c for c in name)
    return cleaned.rstrip(" .")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_version_files(directory: Path, versions: list) -> int:
    """Write one {version_name}.json per version into directory."""
    written = {}
    for version in versions:
        stem = version_filename(version["name"])
        if not stem:
            print(f"  [warn] version {version['name']!r}: empty file name, skipped", file=sys.stderr)
            continue
        if stem in written:
            print(
                f"  [warn] version {version['name']!r}: file name clashes with "
                f"{written[stem]!r}, skipped",
                file=sys.stderr,
            )
            continue
        written[stem] = version["name"]
        write_json(directory / f"{stem}.json", version)
    return len(written)


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
        parameters = doc.get("parameters", {})
        versions = collect_versions(repo, data["filename"], parameters)
        print(f"  versions: {len(versions)}")

        # [source.xxx]: extra repos whose releases are collected with the same
        # filename template and parameters as the default repo.
        sources = []
        for source_id, source in doc.get("source", {}).items():
            source_repo = source["repo"]
            source_versions = collect_versions(source_repo, data["filename"], parameters)
            print(f"  source {source_id} ({source_repo}): {len(source_versions)} versions")
            sources.append(
                {
                    "id": source_id,
                    "name": source["name"],
                    "repo": f"https://github.com/{source_repo}",
                    "versions": source_versions,
                }
            )

        app_repo = f"https://github.com/{repo}"
        app_out = DIST_DIR / "app" / app_id
        write_json(
            app_out / "versions.json",
            {
                "id": app_id,
                "name": data["name"],
                "description": data.get("description", ""),
                "authors": data.get("authors", []),
                "ai-assisted": data.get("ai-assisted", False),
                "repo": app_repo,
                "versions": versions,
                "sources": sources,
            },
        )
        # The default repo is the "official" source; every other source gets its
        # own directory next to it.
        count = write_version_files(app_out / "official", versions)
        for source in sources:
            count += write_version_files(app_out / source["id"], source["versions"])
        print(f"  wrote {count} version files")

        apps.append(
            {
                "id": app_id,
                "name": data["name"],
                "description": data.get("description", ""),
                "authors": data.get("authors", []),
                "ai-assisted": data.get("ai-assisted", False),
                "repo": app_repo,
                "latest-version": latest_version(versions),
                "latest-release-version": latest_release_version(versions),
                "sources": [
                    {
                        "id": source["id"],
                        "name": source["name"],
                        "repo": source["repo"],
                        "latest-version": latest_version(source["versions"]),
                        "latest-release-version": latest_release_version(source["versions"]),
                    }
                    for source in sources
                ],
            }
        )

        copy_icons(app_dir, icons, app_id)

    # GitHub-style UTC timestamp, e.g. 2026-09-19T04:36:11Z
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(DIST_DIR / "apps.json", {"updated_at": updated_at, "apps": apps})
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
