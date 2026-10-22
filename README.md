# 个人博客

一个**纯本地、零云依赖**的静态博客：写 Markdown，跑一条命令，生成整站到 `public/`。

- 写作：`content/posts/` 里放 `.md` 文件，文件头写元信息（标题、日期、标签）
- 生成：`.\build.ps1` 自动产出首页、分页、归档、标签页、文章页、RSS、站点地图、搜索索引
- 预览：`.\serve.ps1` 本地起服务，改文件自动重建 + 浏览器自动刷新
- 发布：`public/` 是纯静态文件，扔到任何一个静态托管上就能访问

---

## 一、三条命令就够用

```powershell
.\new-post.ps1 "我的第一篇文章" -Tags 随笔,生活 -Category 生活   # 新建文章
.\serve.ps1                                                    # 本地预览（自动刷新）
.\build.ps1                                                    # 生成整站到 public/
```

> 第一次运行会自动检查虚拟环境。如果 `.venv` 丢了，脚本会重新创建并安装依赖。

构建会先在临时目录生成完整网站，成功后再替换 `public/`。文章或模板出错时，上次成功生成的网站会保留。自定义 `-Out` 必须指向项目内的空目录或已有博客构建目录；文章、主题、工具、隐藏目录和路径链接不能作为输出目录。`-NoClean` 仍会保留旧输出中的额外文件。

## 二、目录结构

```text
Codex123/
├─ blog.config.json          站点配置：标题、副标题、导航、社交链接、每页文章数
├─ content/
│  ├─ posts/                 文章（一篇一个 .md）
│  └─ pages/                 独立页面（关于、友链… 文件名即 URL）
├─ themes/default/
│  ├─ templates/             Jinja2 模板（base / index / post / archive / terms …）
│  └─ assets/                样式 style.css、脚本 main.js、favicon
├─ static/                   你自己的图片等静态资源（原样复制到网站根目录）
├─ tools/
│  ├─ build.py               构建脚本（解析 Markdown → 生成整站）
│  ├─ serve.py               本地预览 + 文件监听
│  ├─ new_post.py            新建文章
│  └─ organize.py            整理文件名、检查元信息
├─ public/                   生成结果（可随时删除，重新构建即可）
├─ build.ps1 / serve.ps1 / new-post.ps1 / organize.ps1
├─ requirements.txt          Python 依赖
└─ .venv/                    虚拟环境（不入版本库）
```

## 三、写一篇文章

`content/posts/2026-10-13-hello-world.md`：

```markdown
---
title: 文章标题
date: 2026-10-13 09:30
updated: 2026-10-13          # 可选
tags: [随笔, 建站]
categories: [生活]
summary: 列表页显示的一句话摘要（不写就自动截取正文开头）
cover: /images/封面.png       # 可选
draft: false                 # true = 草稿，默认构建时跳过
---

正文用 Markdown 写。支持标题、列表、表格、代码高亮、引用、脚注、提示框：

!!! note "小提示"
    这样写会生成一个提示框。
```

常用元信息：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 文章标题 |
| `date` | 建议 | `2026-10-13 09:30` 或 `2026-10-13`；不写则用文件名里的日期 |
| `tags` | 否 | 会生成对应的标签页 |
| `categories` | 否 | 会生成对应的分类页 |
| `summary` | 否 | 列表页摘要，不写自动截取 |
| `draft` | 否 | `true` 时默认不构建，`.\build.ps1 -Drafts` 可以连草稿一起看 |
| `slug` | 否 | 自定义 URL 短名，默认取文件名（去掉日期前缀） |

## 四、命令速查

| 命令 | 作用 |
| --- | --- |
| `.\build.ps1` | 生成 `public/` 整站 |
| `.\build.ps1 -Drafts` | 连草稿一起构建 |
| `.\serve.ps1` | 本地预览（默认 <http://localhost:8000>），改动自动重建 |
| `.\serve.ps1 -Port 9000 -Drafts` | 换端口、带草稿预览 |
| `.\new-post.ps1 "标题" -Tags a,b -Category c` | 新建文章 |
| `.\organize.ps1` | 预览文件整理建议（只读，不改动） |
| `.\organize.ps1 -Apply` | 把文件名统一成 `YYYY-MM-DD-标题.md` |

「自动整理」体现在两处：构建时自动按日期排序、归类到标签/分类、生成归档与分页；`organize.ps1` 负责把散乱的文件名统一成规范格式，并报告缺失的 `title` / `date`。

## 五、改成你自己的样子

- **站点信息**：编辑 `blog.config.json`（标题、副标题、描述、作者、导航、社交链接、每页文章数）
- **首页介绍**：`description` 控制文章列表上方的一句话简介，文章数量自动统计
- **搜索**：点击导航栏搜索框，或按 `/` 开始搜索；按 `Esc` 关闭结果。深浅色按钮会记住你的选择
- **配色**：`themes/default/assets/style.css` 顶部的 `:root` 变量，改 `--accent` 就是换主题色，深色模式在 `html[data-theme="dark"]` 里
- **页面结构**：`themes/default/templates/*.html`，改完重新构建即可
- **图片**：放进 `static/images/`，正文里用 `![说明](/images/文件名.png)` 引用
- **新页面**：在 `content/pages/` 新建 `.md`，再把它加进 `blog.config.json` 的 `nav` 里

## 六、部署

先把 `blog.config.json` 里的 `url` 改成真实网址（RSS 和站点地图会用到它）。

- **GitHub Pages**：把仓库推到 GitHub，用 Actions 运行 `python tools/build.py`，把 `public/` 作为发布目录
- **Cloudflare Pages / Netlify / Vercel**：构建命令 `pip install -r requirements.txt && python tools/build.py`，输出目录 `public`
- **自己的服务器 / 对象存储**：把 `public/` 里的文件整体上传即可

## 七、环境说明

- 需要 Python 3.10+（本机已用 3.12 建好 `.venv`）
- 四个直接依赖为 `markdown`、`jinja2`、`pygments`、`pyyaml`；它们和间接依赖 `markupsafe` 均在 `requirements.txt` 中锁定版本，装在项目内的 `.venv` 里
- `build.ps1` 会检测依赖文件变化，成功安装后才记录版本状态。Markdown 固定为兼容 Python 3.10 的版本
- 重装依赖：`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- `public/` 是构建产物，已加入 `.gitignore`，不用提交
## 八、发布新文章

正式网站：<https://16369.github.io/>

最省事的一套流程：

```powershell
# 1. 新建文章
.\new-post.ps1 "文章标题" -Tags 技术,随笔 -Category 笔记

# 2. 编辑正文
#    文件在 content/posts/ 目录下，用任意文本编辑器打开即可

# 3. 本地预览
.\serve.ps1

# 4. 一键构建、自检、提交并发布
.\publish.ps1
```

`publish.ps1` 会自动执行构建、链接自检、Git 提交和推送。推送成功后，GitHub Actions 会自动重新部署，通常一两分钟后就能在正式网站看到新文章。

如果 `git push` 因网络问题失败，`publish.ps1` 会自动改用 GitHub API 通道完成发布。

也可以手动发布：

```powershell
.\build.ps1
.\check.ps1
git add .
git commit -m "发布新文章"
git push
```

## 九、回归检查

GitHub Actions 会先运行回归测试，再构建并检查整站，全部通过后才部署。可以在本地执行同样的检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
node --test tests/frontend.test.cjs
.\build.ps1
.\check.ps1
```

JavaScript 回归测试使用 Node.js 22+；写文章、构建和预览博客不需要 Node.js。Python 测试使用临时项目副本，不会改动正式文章。测试覆盖目录保护、构建失败与替换失败后的恢复、图片引用、特殊标题、搜索加载与重试，以及预览自动刷新。

自动刷新仅在 `serve.ps1` 预览时启用，普通构建和正式网站不会发出刷新轮询请求；`-NoWatch` 预览也不启用轮询。
