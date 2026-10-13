---
title: 这是一篇草稿示例
date: 2026-10-13 21:00
tags: [随笔]
categories: [生活]
draft: true
summary: 草稿不会出现在正式构建里，除非用 .\build.ps1 -Drafts。
---

文件头里有 `draft: true`，所以运行 `.\build.ps1` 时这篇文章会被跳过，不会出现在首页、归档、RSS 和搜索里。

想预览草稿：

```powershell
.\build.ps1 -Drafts
.\serve.ps1 -Drafts
```

写完了就把 `draft: true` 删掉，它会自动进入正式列表。