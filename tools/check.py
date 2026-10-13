r"""构建自检：检查 public/ 里的内部链接、资源引用和 RSS/站点地图是否正常。

用法：
    .\check.ps1
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import _force_utf8_stdout  # noqa: E402

_force_utf8_stdout()

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ATTR_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)
EXTERNAL = ("http://", "https://", "//", "mailto:", "tel:", "#", "data:", "javascript:")


def check_html(files: list[Path]) -> list[str]:
    problems: list[str] = []
    for page in files:
        html = page.read_text(encoding="utf-8", errors="replace")
        if "<html" not in html.lower():
            continue
        for raw in ATTR_RE.findall(html):
            # Markdown 会把邮箱链接编码成 HTML 实体（防爬虫），先还原再检查
            value = unescape(raw).strip()
            if not value or value.lower().startswith(EXTERNAL):
                continue
            target = unquote(urlparse(value).path)
            if not target:
                continue
            resolved = (page.parent / target).resolve()
            candidates = [resolved]
            if target.endswith("/"):
                candidates.append(resolved / "index.html")
            candidates.append(resolved.with_suffix(".html")) if resolved.suffix == "" else None
            if not any(c.exists() for c in candidates if c):
                problems.append(f"{page.relative_to(PUBLIC)} -> {value}")
    return problems


def main() -> int:
    if not PUBLIC.exists():
        print("还没有 public/，先运行 .\\build.ps1")
        return 1

    html_files = sorted(PUBLIC.rglob("*.html"))
    problems = check_html(html_files)

    for name in ("feed.xml", "sitemap.xml"):
        path = PUBLIC / name
        if not path.exists():
            problems.append(f"缺少 {name}")
            continue
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            problems.append(f"{name} XML 解析失败：{exc}")

    search = PUBLIC / "search.json"
    if not search.exists():
        problems.append("缺少 search.json（站内搜索会失效）")
    else:
        import json
        try:
            json.loads(search.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"search.json 不是合法 JSON：{exc}")

    print(f"检查了 {len(html_files)} 个页面。")
    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for item in problems:
            print(f"  ✗ {item}")
        return 1
    print("内部链接、资源引用、RSS、站点地图、搜索索引：全部正常 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())