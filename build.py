#!/usr/bin/env python3
"""SwiftStore repo builder.

Scans apps/*/app.toml, queries the GitHub API for tags/releases, then
aggregates everything into dist/apps.json plus a minimal static frontend
and zipped Icon Composer icons under dist/icons/.
"""

import json
import os
from datetime import datetime, timezone
import shutil
import sys
import tomllib
import urllib.error
import urllib.request
import zipfile
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


def collect_versions(repo: str, filename: str) -> list:
    """Return [{name, size, created_at, url}] for releases matching tags and asset filename."""
    tags = github_get(f"{GITHUB_API}/repos/{repo}/tags")
    tag_names = {t.get("name") for t in tags}

    releases = github_get(f"{GITHUB_API}/repos/{repo}/releases")
    versions = []
    for release in releases:
        if release.get("tag_name") not in tag_names:
            continue
        for asset in release.get("assets", []):
            if asset.get("name") == filename:
                versions.append(
                    {
                        "name": release["tag_name"],
                        "size": asset.get("size"),
                        "created_at": asset.get("created_at"),
                        "url": asset.get("browser_download_url"),
                    }
                )
                break
    return versions


def pack_icon(app_dir: Path, icon_name: str, app_id: str) -> None:
    """Zip the .icon directory as {id}.icon.zip into dist/icons/."""
    src = app_dir / icon_name
    if not src.is_dir():
        print(f"  [warn] icon directory not found: {src}", file=sys.stderr)
        return
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = ICONS_DIR / f"{app_id}.icon.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(src.rglob("*")):
            if file.is_file():
                # rename the root folder to {id}.icon inside the archive
                arcname = Path(f"{app_id}.icon") / file.relative_to(src)
                zf.write(file, arcname.as_posix())
    print(f"  icon packed: {zip_path.relative_to(ROOT)}")


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
            data = tomllib.load(f)["app"]

        app_id = data["id"]
        repo = data["repo"]
        versions = collect_versions(repo, data["filename"])
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

        pack_icon(app_dir, data["icon"], app_id)

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
