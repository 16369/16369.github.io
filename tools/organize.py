#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""整理 content/posts/：把文件名统一成 YYYY-MM-DD-标题.md，并报告缺失的元信息。

默认只预览（dry-run），确认没问题再加 --apply 真正改名。

用法：
    .\organize.ps1            # 预览会改哪些文件
    .\organize.ps1 -Apply     # 真的改
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import DATE_PREFIX_RE, date_from_filename, slugify, split_front_matter  # noqa: E402

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="整理文章文件名与元信息")
    parser.add_argument("--apply", action="store_true", help="真正执行改名（默认只预览）")
    args = parser.parse_args(argv)

    if not POSTS_DIR.exists():
        print("还没有 content/posts/ 目录。")
        return 0

    files = sorted(POSTS_DIR.glob("*.md"))
    if not files:
        print("content/posts/ 里还没有文章。")
        return 0

    renames: list[tuple[Path, Path]] = []
    notes: list[str] = []
    today = datetime.now()

    for path in files:
        try:
            meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"⚠ {path.name}：front matter 解析失败（{exc}）")
            continue

        if not meta.get("title"):
            notes.append(f"⚠ {path.name}：缺少 title")

        # 日期：front matter > 文件名前缀 > 文件修改时间
        date = None
        raw_date = meta.get("date") or meta.get("published")
        if isinstance(raw_date, datetime):
            date = raw_date
        elif raw_date is not None:
            text = str(raw_date).strip().replace("/", "-").replace("T", " ")[:10]
            try:
                date = datetime.strptime(text, "%Y-%m-%d")
            except ValueError:
                notes.append(f"⚠ {path.name}：date 格式无法识别（{raw_date}）")
        if date is None:
            date = date_from_filename(path.name) or datetime.fromtimestamp(path.stat().st_mtime)
            notes.append(f"· {path.name}：缺少 date，暂用 {date.strftime('%Y-%m-%d')}")

        if date > today:
            notes.append(f"· {path.name}：日期在未来（{date.strftime('%Y-%m-%d')}）")

        stem = DATE_PREFIX_RE.sub("", path.stem)
        slug = slugify(str(meta.get("slug") or stem), fallback=f"post-{date.strftime('%Y%m%d')}")
        target = POSTS_DIR / f"{date.strftime('%Y-%m-%d')}-{slug}.md"
        if target != path:
            renames.append((path, target))

    if renames:
        print("建议重命名：" if not args.apply else "正在重命名：")
        reserved: set[Path] = set()
        for src, dst in renames:
            while dst.exists() and dst != src or dst in reserved:
                dst = dst.with_name(f"{dst.stem}-2{dst.suffix}")
            reserved.add(dst)
            print(f"  {src.name}  ->  {dst.name}")
            if args.apply:
                src.rename(dst)
    else:
        print("文件名已经是统一格式，无需整理。")

    if notes:
        print("\n需要留意：")
        for note in notes:
            print(f"  {note}")

    if renames and not args.apply:
        print("\n上面只是预览。确认无误后运行：.\\organize.ps1 -Apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())