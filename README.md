# SwiftStore-Repo

一个托管在 GitHub Pages 上的 iOS 应用源（伪 API）。

每小时自动从各应用的 GitHub Releases 聚合版本信息，生成 `apps.json`、每个应用的版本详情与应用图标。

## 如何添加应用

1. Fork 本仓库，在 `apps/` 下新建以应用 id 命名的目录（小写字母、数字、连字符），例如 `apps/my-app/`。

2. 放入两个图标文件 `light.png` 和 `dark.png`。

3. 创建 `app.toml`，参考下面的完整说明填写。

4. 本地验证（可选但推荐）：运行 `python build.py`（需 Python 3.11+），确认你的应用出现在 `dist/apps.json` 中，且 `dist/app/<id>/versions.json` 的 `versions` 不为空。

5. 提交 PR。合并后一小时内会自动出现在源中。

## app.toml 格式

```toml
[app]
id = "my-app"                                # 必填，与目录名一致
name = "MyApp"                               # 必填，显示名称
description = "一句话介绍"                    # 必填
authors = ["your-github-name"]               # 必填，作者列表
ai-assisted = false                          # 必填，是否有 AI 辅助开发
repo = "owner/repo"                          # 必填，GitHub 仓库（无需 https:// 前缀）
filename = "MyApp.ipa"                       # 必填，Release 中 ipa 的 asset 文件名

[icon]
light = "light.png"                          # 必填，浅色图标文件名
dark = "dark.png"                            # 必填，深色图标文件名
```

脚本会访问 `https://api.github.com/repos/<repo>/releases`，找到 `tag_name` 与 tags 对应、且包含名为 `filename` 的 asset 的 release，将其收录为一个版本。

### 使用 parameters 处理动态文件名

如果 asset 文件名中包含版本号等变动部分，可以用 `[parameters.xxx]` 定义变量，并在 `filename` 中通过 `{xxx}` 引用：

```toml
[app]
filename = "MyApp.{version}+{build}.ipa"

# type = "source"：从 release/tag 信息中提取
[parameters.version]
type = "source"
source = "release.name"                      # 支持 release.name、tag.name
regex = 'MyApp (.+) \(Build ([0-9]+)\)'      # 可选，但必须与 group 成对出现
group = 1                                    # 取正则的第几个分组
                                             # 不写 regex/group 则取 source 完整内容
[parameters.build]
type = "source"
source = "release.name"
regex = 'MyApp (.+) \(Build ([0-9]+)\)'
group = 2
```

```toml
# type = "predicated"：根据条件取值
[parameters.channel]
type = "predicated"
predicate = "prerelease"                     # 目前支持 prerelease（release 的预发布标记）
if_true = "-beta"                            # predicate 为 true 时的值
if_false = ""                                # predicate 为 false 时的值
fallback = ""                                # predicate 取不到值时的兜底值
```

> 注意：TOML 中含 `\` 的正则请使用单引号字面字符串（`regex = '...'`），双引号字符串里的 `\(` 是非法转义。

### 添加额外的源（fork）

如果同一个应用有其他人维护的 fork 仓库也想收录，可以用 `[source.xxx]` 声明（`xxx` 为源的 id）：

```toml
[source.deechael]
name = "DeeChael 源"
repo = "DeeChael/PiliPod"
```

每个源会对自己的 `repo` 执行与默认仓库完全相同的版本收集逻辑（共用同一个 `filename` 模板和 `[parameters]`），生成的版本列表出现在该应用的 `versions.json` 中：

```json
"sources": [
  {
    "id": "deechael",
    "name": "DeeChael 源",
    "repo": "https://github.com/DeeChael/PiliPod",
    "versions": [ ... ]
  }
]
```

## 生成的 API

部署后（`gh-pages` 分支）：

- `GET /apps.json` — 应用列表与每个源的最新版本（`Content-Type: application/json`），访问根路径会自动跳转到这里
- `GET /app/<id>/versions.json` — 单个应用的完整版本列表
- `GET /app/<id>/official/<version>.json` — 默认仓库（official 源）某个版本的下载信息
- `GET /app/<id>/<source-id>/<version>.json` — 非默认源某个版本的下载信息
- `GET /icons/<id>_light.png`、`GET /icons/<id>_dark.png` — 应用图标

`apps.json` 只包含应用元信息与各源的最新版本，完整版本列表放在 `app/<id>/versions.json`：

```json
{
  "updated_at": "2026-09-19T05:27:37Z",
  "apps": [
    {
      "id": "my-app",
      "name": "MyApp",
      "description": "一句话介绍",
      "authors": ["your-github-name"],
      "ai-assisted": false,
      "repo": "https://github.com/owner/repo",
      "latest-version": "v1.1.0-beta.1",
      "latest-release-version": "v1.0.0",
      "sources": [
        {
          "id": "deechael",
          "name": "DeeChael 源",
          "repo": "https://github.com/DeeChael/PiliPod",
          "latest-version": "0.3.6-newui",
          "latest-release-version": "0.3.6-newui"
        }
      ]
    }
  ]
}
```

- `latest-version`：最新的版本（包含 prerelease），没有版本时为 `null`
- `latest-release-version`：最新的非 prerelease 版本，全部是 prerelease 时为 `null`

只想展示最新版的客户端只读 `apps.json` 即可；用户点击下载时再按版本名请求 `app/<id>/official/<version>.json`（非默认源为 `app/<id>/<source-id>/<version>.json`），无需先拉取完整版本列表。

> 版本名作为文件名时会做最小化处理：`< > : " / \ | ? *` 与控制字符替换为 `_`，并去掉末尾的点和空格（例如 `release/1.0` → `release_1.0.json`）。

`app/<id>/versions.json` 格式：

```json
{
  "id": "my-app",
  "name": "MyApp",
  "description": "一句话介绍",
  "authors": ["your-github-name"],
  "ai-assisted": false,
  "repo": "https://github.com/owner/repo",
  "versions": [
    {
      "name": "v1.0.0",
      "size": 12345,
      "created_at": "2026-09-19T04:34:47Z",
      "url": "https://github.com/owner/repo/releases/download/v1.0.0/MyApp.ipa",
      "prerelease": false
    }
  ],
  "sources": [
    {
      "id": "deechael",
      "name": "DeeChael 源",
      "repo": "https://github.com/DeeChael/PiliPod",
      "versions": [ ... ]
    }
  ]
}
```

版本列表按 `created_at` 从新到旧排列。单个版本文件就是 `versions` 数组里的一个对象：

```json
{
  "name": "v1.0.0",
  "size": 12345,
  "created_at": "2026-09-19T04:34:47Z",
  "url": "https://github.com/owner/repo/releases/download/v1.0.0/MyApp.ipa",
  "prerelease": false
}
```
