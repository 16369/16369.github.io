#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""把 content/ 里的 Markdown 自动整理成一个完整的静态博客，输出到 public/。

用法：
    .\build.ps1                  # 正常构建
    .\build.ps1 -Drafts          # 连草稿一起构建
    .\.venv\Scripts\python.exe tools\build.py --help
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, time
from email.utils import format_datetime
from html import unescape
from math import ceil
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pygments.formatters import HtmlFormatter

def _force_utf8_stdout() -> None:
    """Windows 控制台/管道默认可能是 GBK，统一改成 UTF-8，中文才不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdout()
ROOT = Path(__file__).resolve().parents[1]
LOCAL_TZ = datetime.now().astimezone().tzinfo

MD_EXTENSIONS = [
    "extra", "codehilite", "toc", "tables", "fenced_code",
    "footnotes", "attr_list", "md_in_html", "sane_lists", "admonition",
]
MD_CONFIGS = {
    "codehilite": {"css_class": "codehilite", "guess_lang": False},
    "toc": {"toc_depth": "2-4"},
}

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
LATIN_RE = re.compile(r"[A-Za-z0-9_']+")
FRONT_MATTER_RE = re.compile(r"^\ufeff?---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)
SLUG_CLEAN_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
TAG_RE = re.compile(r"<[^>]+>")
DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[-_ ]+")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def slugify(text: str, fallback: str = "item") -> str:
    """把任意标题转成可以安全用作文件名/URL 的短名（保留中文）。"""
    text = (text or "").strip().lower()
    text = SLUG_CLEAN_RE.sub("-", text).strip("-")
    return text or fallback


def url_encode(path: str) -> str:
    return quote(path, safe="/-._~")


def split_front_matter(raw: str) -> tuple[dict, str]:
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("front matter 必须是一组 key: value")
    return meta, raw[match.end():]


def to_datetime(value, fallback: datetime | None = None) -> datetime:
    dt = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time(9, 0))
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value)
    elif isinstance(value, str):
        text = value.strip().replace("/", "-").replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        dt = fallback or datetime.now()
    return dt.replace(tzinfo=None)


def date_from_filename(name: str) -> datetime | None:
    match = DATE_PREFIX_RE.match(name)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,，、;；]", value) if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def html_to_text(html: str) -> str:
    text = TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def text_units(text: str) -> int:
    """粗略字数：中日韩字符按字算，英文单词按个算。"""
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


def make_markdown() -> markdown.Markdown:
    return markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_CONFIGS, output_format="html5")


def rfc822(dt: datetime) -> str:
    return format_datetime(dt.replace(tzinfo=LOCAL_TZ))


def validate_output_dir(path: Path) -> Path:
    """只允许写入项目内的独立输出目录，不覆盖源码或未知文件。"""
    root = ROOT.resolve()
    out = path.resolve()
    if out == root or not out.is_relative_to(root):
        raise ValueError(f"拒绝使用输出目录：{out} 必须位于项目目录内")
    # 同时检查原始路径，避免通过符号链接/Windows junction 改写其他目录。
    original = path.absolute()
    for part in (original, *original.parents):
        if part == root:
            break
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError(f"拒绝使用链接作为输出路径：{part}")
    first = out.relative_to(root).parts[0].casefold()
    if first.startswith(".") or first in {"content", "themes", "static", "tools", "tests", "venv", "node_modules"}:
        raise ValueError(f"拒绝使用受保护的输出目录：{out}")
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"输出路径不是目录：{out}")
        if any(out.iterdir()) and not (out / ".blog-build.json").is_file():
            raise ValueError(f"拒绝覆盖非空目录：{out} 没有博客构建标记，请选择空目录")
    return out


# --------------------------------------------------------------------------- #
# 内容读取
# --------------------------------------------------------------------------- #
class Content:
    def __init__(self, cfg: dict, out_dir: Path, include_drafts: bool):
        self.cfg = cfg
        self.out_dir = out_dir
        self.include_drafts = include_drafts
        self.posts: list[dict] = []
        self.pages: list[dict] = []
        self.terms: dict[str, dict] = {}
        self.warnings: list[str] = []

    # -- 文章 ---------------------------------------------------------------- #
    def load_posts(self) -> None:
        posts_dir = ROOT / "content" / "posts"
        if not posts_dir.exists():
            return
        used_slugs: set[str] = set()
        for path in sorted(posts_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta, body = split_front_matter(raw)
            if meta.get("draft") and not self.include_drafts:
                continue

            title = str(meta.get("title") or path.stem).strip()
            fallback_date = date_from_filename(path.name) or datetime.fromtimestamp(path.stat().st_mtime)
            published = to_datetime(meta.get("date") or meta.get("published"), fallback_date)
            updated = to_datetime(meta["updated"], None) if meta.get("updated") else None

            name_for_slug = str(meta.get("slug") or DATE_PREFIX_RE.sub("", path.stem))
            slug = slugify(name_for_slug, fallback=slugify(published.strftime("%Y%m%d-%H%M%S")))
            base_slug, index = slug, 2
            while slug in used_slugs:
                slug = f"{base_slug}-{index}"
                index += 1
            used_slugs.add(slug)

            md = make_markdown()
            content_html = md.convert(body)
            toc_html = getattr(md, "toc", "")
            plain = html_to_text(content_html)
            units = text_units(plain)

            summary = str(meta.get("summary") or meta.get("description") or "").strip()
            if not summary:
                summary = plain[: int(self.cfg.get("excerpt_length", 140))].strip()
                if len(plain) > len(summary):
                    summary += "…"

            self.posts.append({
                "title": title,
                "slug": slug,
                "url": url_encode(f"posts/{slug}.html"),
                "raw_url": f"posts/{slug}.html",
                "source": path,
                "date": published,
                "date_str": published.strftime("%Y-%m-%d"),
                "date_iso": published.strftime("%Y-%m-%d"),
                "month_day": published.strftime("%m-%d"),
                "rfc822": rfc822(published),
                "updated": updated,
                "updated_str": updated.strftime("%Y-%m-%d") if updated else "",
                "updated_iso": updated.strftime("%Y-%m-%d") if updated else "",
                "summary": summary,
                "content": content_html,
                "plain": plain,
                "toc": toc_html,
                "tags": [],
                "categories": [],
                "word_count": units,
                "reading_time": max(1, ceil(units / 400)),
                "draft": bool(meta.get("draft")),
                "cover": meta.get("cover", ""),
            })

        self.posts.sort(key=lambda p: (p["date"], p["title"]), reverse=True)

        for post in self.posts:
            path = post["source"]
            meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
            post["tags"] = [self.register_term("tag", name) for name in as_list(meta.get("tags"))]
            post["categories"] = [self.register_term("category", name) for name in as_list(meta.get("categories") or meta.get("category"))]

        for index, post in enumerate(self.posts):
            newer = self.posts[index - 1] if index > 0 else None
            older = self.posts[index + 1] if index + 1 < len(self.posts) else None
            post["newer"] = {"title": newer["title"], "url": newer["url"]} if newer else None
            post["older"] = {"title": older["title"], "url": older["url"]} if older else None

    # -- 独立页面 ------------------------------------------------------------ #
    def load_pages(self) -> None:
        pages_dir = ROOT / "content" / "pages"
        if not pages_dir.exists():
            return
        for path in sorted(pages_dir.glob("*.md")):
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            if meta.get("draft") and not self.include_drafts:
                continue
            title = str(meta.get("title") or path.stem).strip()
            slug = slugify(str(meta.get("slug") or path.stem), fallback=slugify(title, "page"))
            md = make_markdown()
            content_html = md.convert(body)
            updated = to_datetime(meta["updated"], None) if meta.get("updated") else None
            self.pages.append({
                "title": title,
                "slug": slug,
                "url": url_encode(f"{slug}.html"),
                "raw_url": f"{slug}.html",
                "content": content_html,
                "summary": str(meta.get("summary") or "").strip() or html_to_text(content_html)[:120],
                "updated_str": updated.strftime("%Y-%m-%d") if updated else "",
                "updated_iso": updated.strftime("%Y-%m-%d") if updated else "",
            })

    # -- 标签 / 分类 ---------------------------------------------------------- #
    def register_term(self, kind: str, name: str) -> dict:
        slug = slugify(name)
        key = f"{kind}/{slug}"
        if key not in self.terms:
            folder = "tags" if kind == "tag" else "categories"
            self.terms[key] = {
                "kind": kind,
                "kind_label": "标签" if kind == "tag" else "分类",
                "name": name,
                "slug": slug,
                "raw_url": f"{folder}/{slug}.html",
                "url": url_encode(f"{folder}/{slug}.html"),
                "count": 0,
            }
        return self.terms[key]

    def bump_terms(self) -> None:
        for post in self.posts:
            for term in post["tags"] + post["categories"]:
                term["count"] += 1

    def terms_of(self, kind: str) -> list[dict]:
        items = [t for t in self.terms.values() if t["kind"] == kind]
        return sorted(items, key=lambda t: (-t["count"], t["name"]))

    def posts_of(self, term: dict) -> list[dict]:
        return [p for p in self.posts if term in p["tags"] or term in p["categories"]]


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
class Builder:
    def __init__(self, cfg: dict, out_dir: Path, include_drafts: bool, clean: bool = True, live_reload: bool = False):
        self.cfg = cfg
        self.out_dir = out_dir
        self.clean = clean
        self.live_reload = live_reload
        self.content = Content(cfg, out_dir, include_drafts)
        theme_dir = ROOT / "themes" / str(cfg.get("theme", "default"))
        self.theme_dir = theme_dir
        self.env = Environment(
            loader=FileSystemLoader(str(theme_dir / "templates")),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.written: list[str] = []

    # -- 基础设施 ------------------------------------------------------------ #
    def ctx(self, root: str, page: dict, **extra) -> dict:
        now = datetime.now()
        base = {
            "site": self.cfg,
            "root": root,
            "page": page,
            "build_year": now.year,
            "build_time": now,
            "build_time_rfc822": rfc822(now),
            "quote": url_encode,
            "live_reload": self.live_reload,
            "site_stats": {
                "posts": len(self.content.posts),
                "tags": len(self.content.terms_of("tag")),
                "categories": len(self.content.terms_of("category")),
            },
            "page_urls": {item["raw_url"] for item in self.content.pages},
        }
        base.update(extra)
        return base

    def render(self, template: str, out_path: str, context: dict) -> None:
        html = self.env.get_template(template).render(**context)
        target = self.out_dir / out_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8", newline="\n")
        self.written.append(out_path.replace("\\", "/"))

    def absolute(self, path: str) -> str:
        return f"{str(self.cfg.get('url', '')).rstrip('/')}/{path}"

    # -- 构建 ---------------------------------------------------------------- #
    def run(self) -> None:
        destination = validate_output_dir(self.out_dir)
        content = self.content
        content.load_posts()
        content.load_pages()
        content.bump_terms()
        destination.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=".blog-build-", dir=destination.parent)).resolve()
        backup = work / "previous"
        preserve_backup = False
        try:
            self.out_dir = work / "site"
            if not self.clean and destination.exists():
                shutil.copytree(destination, self.out_dir)
            else:
                self.out_dir.mkdir()
            self.copy_assets()
            self.build_posts()
            self.build_index()
            self.build_archive()
            self.build_terms()
            self.build_pages()
            self.build_feed()
            self.build_sitemap()
            self.build_search_index()
            self.build_extras()

            # 完整生成后才替换旧站点；Windows 不支持直接覆盖非空目录。
            validate_output_dir(destination)
            if destination.exists():
                preserve_backup = True
                destination.rename(backup)
            try:
                self.out_dir.rename(destination)
            except BaseException:
                if backup.exists():
                    try:
                        backup.rename(destination)
                    except BaseException as exc:
                        raise RuntimeError(f"替换失败且无法自动还原，旧站点保存在：{backup}") from exc
                raise
            preserve_backup = False
        finally:
            self.out_dir = destination
            # 只清理本次创建、且确认位于项目内的临时目录。
            if (not preserve_backup or not backup.exists()) and work.parent == destination.parent and work.is_relative_to(ROOT.resolve()):
                shutil.rmtree(work, ignore_errors=True)

    def copy_assets(self) -> None:
        assets_src = self.theme_dir / "assets"
        assets_dst = self.out_dir / "assets"
        if assets_src.exists():
            shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)

        # 高亮样式：浅色 + 深色各生成一份
        formatter = HtmlFormatter(style="default")
        dark = HtmlFormatter(style="monokai")
        css = [
            "/* 由 build.py 自动生成（Pygments），请勿手改 */",
            formatter.get_style_defs(".codehilite"),
            dark.get_style_defs('html[data-theme="dark"] .codehilite'),
            "@media (prefers-color-scheme: dark) {",
            dark.get_style_defs('html:not([data-theme="light"]) .codehilite'),
            "}",
        ]
        assets_dst.mkdir(parents=True, exist_ok=True)
        (assets_dst / "highlight.css").write_text("\n".join(css), encoding="utf-8", newline="\n")
        self.written.append("assets/highlight.css")

        # 用户自己的图片等静态文件
        static_src = ROOT / "static"
        if static_src.exists():
            for item in static_src.iterdir():
                if item.name.startswith("."):
                    continue
                target = self.out_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

    def build_posts(self) -> None:
        for post in self.content.posts:
            page = {
                "title": post["title"],
                "absolute_url": self.absolute(post["url"]),
                "nav_active": "",
                "type": "article",
            }
            self.render("post.html", post["raw_url"], self.ctx("../", page, post=post, toc=post["toc"]))

    def build_index(self) -> None:
        posts = self.content.posts
        per_page = max(1, int(self.cfg.get("posts_per_page", 10)))
        chunks = [posts[i:i + per_page] for i in range(0, len(posts), per_page)] or [[]]
        total = len(chunks)
        for number, chunk in enumerate(chunks, start=1):
            root = "" if number == 1 else "../"
            raw_url = "index.html" if number == 1 else f"page/{number}.html"
            prev_url = None
            if number > 1:
                prev_url = "index.html" if number == 2 else f"page/{number - 1}.html"
            next_url = f"page/{number + 1}.html" if number < total else None
            page = {
                "title": self.cfg.get("title", "博客"),
                "absolute_url": self.absolute(raw_url),
                "nav_active": "index.html",
                "type": "website",
            }
            context = self.ctx(
                root, page, posts=chunk,
                pagination={"page": number, "total_pages": total, "prev_url": prev_url, "next_url": next_url},
            )
            self.render("index.html", raw_url, context)

    def build_archive(self) -> None:
        posts = self.content.posts
        groups: list[dict] = []
        for post in posts:
            year = post["date"].year
            if not groups or groups[-1]["year"] != year:
                groups.append({"year": year, "posts": []})
            groups[-1]["posts"].append(post)
        page = {"title": "归档", "absolute_url": self.absolute("archive.html"), "nav_active": "archive.html", "type": "website"}
        self.render("archive.html", "archive.html", self.ctx("", page, year_groups=groups, total_posts=len(posts)))

    def build_terms(self) -> None:
        tags = self.content.terms_of("tag")
        categories = self.content.terms_of("category")
        page = {"title": "标签", "absolute_url": self.absolute("tags.html"), "nav_active": "tags.html", "type": "website"}
        self.render("terms.html", "tags.html", self.ctx("", page, tag_terms=tags, category_terms=categories))

        for term in self.content.terms.values():
            posts = self.content.posts_of(term)
            term_page = {
                "title": f'{term["kind_label"]}：{term["name"]}',
                "absolute_url": self.absolute(term["url"]),
                "nav_active": "tags.html",
                "type": "website",
            }
            self.render("term.html", term["raw_url"], self.ctx("../", term_page, term=term, posts=posts))

    def build_pages(self) -> None:
        for item in self.content.pages:
            page = {
                "title": item["title"],
                "absolute_url": self.absolute(item["url"]),
                "nav_active": item["raw_url"],
                "type": "website",
            }
            self.render("page.html", item["raw_url"], self.ctx("", page, item=item))

    def build_feed(self) -> None:
        posts = self.content.posts[:20]
        context = self.ctx("", {"absolute_url": self.absolute("feed.xml")}, posts=posts)
        self.render("feed.xml", "feed.xml", context)

    def build_sitemap(self) -> None:
        urls = [("index.html", None)]
        urls += [(p["raw_url"], p["date_str"]) for p in self.content.posts]
        urls += [(p["raw_url"], p["updated_iso"] or None) for p in self.content.pages]
        urls.append(("archive.html", None))
        urls.append(("tags.html", None))
        urls += [(t["raw_url"], None) for t in self.content.terms.values()]
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for path, lastmod in urls:
            entry = [f"  <url>", f"    <loc>{self.absolute(path)}</loc>"]
            if lastmod:
                entry.append(f"    <lastmod>{lastmod}</lastmod>")
            entry.append("  </url>")
            lines.extend(entry)
        lines.append("</urlset>")
        (self.out_dir / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8", newline="\n")
        self.written.append("sitemap.xml")

        robots = "User-agent: *\nAllow: /\n\nSitemap: {}/sitemap.xml\n".format(str(self.cfg.get("url", "")).rstrip("/"))
        (self.out_dir / "robots.txt").write_text(robots, encoding="utf-8", newline="\n")
        self.written.append("robots.txt")

    def build_search_index(self) -> None:
        data = [{
            "title": p["title"],
            "url": p["url"],
            "summary": p["summary"],
            "date": p["date_str"],
            "tags": [t["name"] for t in p["tags"]],
            "content": p["plain"][:2000],
        } for p in self.content.posts]
        (self.out_dir / "search.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":")), encoding="utf-8", newline="\n")
        self.written.append("search.json")

    def build_extras(self) -> None:
        page = {"title": "页面没找到", "absolute_url": self.absolute("404.html"), "nav_active": "", "type": "website"}
        self.render("404.html", "404.html", self.ctx("", page))

        manifest = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "posts": len(self.content.posts),
            "pages": len(self.content.pages),
            "tags": len(self.content.terms_of("tag")),
            "categories": len(self.content.terms_of("category")),
            "files": len(self.written),
        }
        (self.out_dir / ".blog-build.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    path = ROOT / "blog.config.json"
    if not path.exists():
        raise SystemExit("找不到 blog.config.json")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.setdefault("title", "我的博客")
    cfg.setdefault("lang", "zh-CN")
    cfg.setdefault("url", "")
    cfg.setdefault("nav", [])
    cfg.setdefault("theme", "default")
    cfg.setdefault("output_dir", "public")
    cfg.setdefault("posts_per_page", 10)
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建静态博客")
    parser.add_argument("--drafts", action="store_true", help="包含 draft: true 的草稿")
    parser.add_argument("--out", default=None, help="输出目录（默认取配置里的 output_dir）")
    parser.add_argument("--no-clean", action="store_true", help="不清理输出目录，直接覆盖")
    parser.add_argument("--quiet", action="store_true", help="只输出结果摘要")
    parser.add_argument("--live-reload", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    cfg = load_config()
    out_dir = Path(args.out) if args.out else ROOT / str(cfg.get("output_dir", "public"))
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    include_drafts = args.drafts or bool(cfg.get("show_drafts"))
    builder = Builder(cfg, out_dir, include_drafts, clean=not args.no_clean, live_reload=args.live_reload)
    builder.run()

    content = builder.content
    rel_out = out_dir.relative_to(ROOT) if ROOT in out_dir.parents else out_dir
    if not args.quiet:
        print(f"输出目录：{rel_out}")
        for post in content.posts[:5]:
            print(f"  · {post['date_str']}  {post['title']}")
        if len(content.posts) > 5:
            print(f"  · …… 另有 {len(content.posts) - 5} 篇")
    print(
        f"构建完成：{len(content.posts)} 篇文章"
        + (f"（含草稿）" if include_drafts else "")
        + f"，{len(content.pages)} 个独立页面，"
        f"{len(content.terms_of('tag'))} 个标签，共写出 {len(builder.written)} 个文件。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
