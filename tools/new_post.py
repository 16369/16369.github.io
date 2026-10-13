#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""新建一篇文章：填好 front matter，正文留给你写。

用法：
    .\new-post.ps1 "文章标题" -Tags 技术,随笔 -Category 笔记
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import DATE_PREFIX_RE, as_list, slugify  # noqa: E402

def _force_utf8_stdout() -> None:
    """Windows 控制台/管道默认可能是 GBK，统一改成 UTF-8，中文才不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdout()
ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "content" / "posts"

TEMPLATE = """---
title: {title}
date: {date}
tags: [{tags}]
categories: [{categories}]
summary: 
draft: {draft}
---

在这里开始写正文。写完这一段就可以删掉它。

## 小标题

正文支持 Markdown 的全部常用语法，参考 `content/posts/2026-10-12-markdown-cheatsheet.md`。
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="新建一篇文章")
    parser.add_argument("title", help="文章标题（也用来生成文件名）")
    parser.add_argument("--tags", "-t", default="", help="标签，逗号分隔")
    parser.add_argument("--category", "-c", default="", help="分类，可写多个（逗号分隔）")
    parser.add_argument("--slug", "-s", default="", help="自定义 URL 短名（默认由标题生成）")
    parser.add_argument("--date", "-d", default="", help="发布日期，默认今天（YYYY-MM-DD）")
    parser.add_argument("--draft", action="store_true", help="标记为草稿")
    parser.add_argument("--force", action="store_true", help="同名文件已存在时覆盖")
    args = parser.parse_args(argv)

    date_text = args.date.strip() or datetime.now().strftime("%Y-%m-%d")
    try:
        date = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        print(f"日期格式不对：{date_text}（应该像 2026-10-13）")
        return 1

    slug = slugify(args.slug or args.title, fallback=f"post-{date.strftime('%Y%m%d')}")
    path = POSTS_DIR / f"{date.strftime('%Y-%m-%d')}-{slug}.md"
    if path.exists() and not args.force:
        print(f"文件已存在：{path.relative_to(ROOT)}")
        print("换一个标题，或者加 --force 覆盖。")
        return 1

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.format(
        title=args.title.strip(),
        date=f"{date.strftime('%Y-%m-%d')} {datetime.now().strftime('%H:%M')}",
        tags=", ".join(as_list(args.tags)),
        categories=", ".join(as_list(args.category)),
        draft="true" if args.draft else "false",
    ), encoding="utf-8")

    print(f"已创建：{path.relative_to(ROOT)}")
    print("用编辑器打开它开始写，然后运行 .\\serve.ps1 本地预览。")
    return 0


if __name__ == "__main__":
    sys.exit(main())