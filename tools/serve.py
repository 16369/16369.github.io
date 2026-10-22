#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""本地预览：构建一次，然后在 http://localhost:8000 提供服务。

改文件会自动重新构建，浏览器会自动刷新（靠 /__reload 心跳）。

用法：
    .\serve.ps1                 # 预览，自动重建
    .\serve.ps1 -Port 9000
    .\serve.ps1 -Drafts         # 连草稿一起预览
"""
from __future__ import annotations

import argparse
import http.server
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as blogbuild  # noqa: E402

def _force_utf8_stdout() -> None:
    """Windows 控制台/管道默认可能是 GBK，统一改成 UTF-8，中文才不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdout()
ROOT = Path(__file__).resolve().parents[1]
WATCH_DIRS = ["content", "themes", "static"]
WATCH_FILES = ["blog.config.json"]
STATE = {"version": 0}
LOCK = threading.Lock()


def snapshot() -> dict[str, float]:
    data: dict[str, float] = {}
    for rel in WATCH_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                try:
                    data[str(path)] = path.stat().st_mtime
                except OSError:
                    pass
    for rel in WATCH_FILES:
        path = ROOT / rel
        if path.exists():
            data[str(path)] = path.stat().st_mtime
    return data


def rebuild(drafts: bool, live_reload: bool = True) -> None:
    argv = ["--drafts"] if drafts else []
    if live_reload:
        argv.append("--live-reload")
    code = blogbuild.main(argv + ["--quiet"])
    if code == 0:
        with LOCK:
            STATE["version"] += 1


def watch_loop(drafts: bool) -> None:
    last = snapshot()
    while True:
        time.sleep(1.0)
        current = snapshot()
        if current != last:
            time.sleep(0.4)  # 等文件写完
            last = snapshot()
            print("\n检测到改动，正在重新构建……")
            try:
                rebuild(drafts)
                print("已更新，浏览器会自动刷新。")
            except Exception as exc:  # noqa: BLE001
                print(f"构建失败：{exc}")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "public"), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/__reload":
            with LOCK:
                body = str(STATE["version"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        if str(args[1] if len(args) > 1 else "") not in ("200", "304"):
            super().log_message(fmt, *args)


def free_port(start: int, tries: int = 12) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit(f"{start}~{start + tries} 端口都被占用了，请用 -Port 指定其它端口。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地预览博客")
    parser.add_argument("--port", "-p", type=int, default=8000)
    parser.add_argument("--drafts", action="store_true", help="包含草稿")
    parser.add_argument("--no-watch", action="store_true", help="改动后不自动重建")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    print("正在构建……")
    rebuild(args.drafts, live_reload=not args.no_watch)

    port = free_port(args.port)
    url = f"http://localhost:{port}/"

    if not args.no_watch:
        threading.Thread(target=watch_loop, args=(args.drafts,), daemon=True).start()

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"预览地址：{url}")
        print("按 Ctrl+C 停止。\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
