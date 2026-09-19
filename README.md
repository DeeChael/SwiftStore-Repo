# SwiftStore-Repo

一个托管在 GitHub Pages 上的 iOS 应用源（伪 API）。

每小时自动从各应用的 GitHub Releases 聚合版本信息，生成 `apps.json` 与应用图标。

## 如何添加应用

1. Fork 本仓库，在 `apps/` 下新建以应用 id 命名的目录（小写字母、数字、连字符），例如 `apps/my-app/`。

2. 放入两个图标文件 `light.png` 和 `dark.png`。

3. 创建 `app.toml`，参考下面的完整说明填写。

4. 本地验证（可选但推荐）：运行 `python build.py`（需 Python 3.11+），确认你的应用出现在 `dist/apps.json` 中且 `versions` 不为空。

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

## 生成的 API

部署后（`gh-pages` 分支）：

- `GET /apps.json` — 应用列表（`Content-Type: application/json`），访问根路径会自动跳转到这里
- `GET /icons/<id>_light.png`、`GET /icons/<id>_dark.png` — 应用图标

`apps.json` 格式：

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
      "versions": [
        {
          "name": "v1.0.0",
          "size": 12345,
          "created_at": "2026-09-19T04:34:47Z",
          "url": "https://github.com/owner/repo/releases/download/v1.0.0/MyApp.ipa",
          "prerelease": false
        }
      ]
    }
  ]
}
```
