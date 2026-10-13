#!/usr/bin/env python3
"""Publish the current local Git commit through the GitHub API.

This is a fallback for networks where `git push` cannot connect to
github.com, while api.github.com remains reachable.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = "16369"
REPO = "16369.github.io"
BRANCH = "main"


def find_gh() -> str:
    found = shutil.which("gh")
    if found:
        return found
    local = Path.home() / ".local" / "gh" / "bin" / "gh.exe"
    if local.exists():
        return str(local)
    raise SystemExit("找不到 gh 命令，请先安装 GitHub CLI。")


GH = find_gh()


def git(args: list[str]) -> bytes:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(message or f"git {' '.join(args)} 失败")
    return proc.stdout


def api(path: str, payload: dict | None = None, method: str = "GET") -> dict:
    command = [GH, "api"]
    if payload is not None:
        command += ["--input", "-"]
    command += ["--method", method, f"repos/{OWNER}/{REPO}{path}"]
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(message or f"gh api {path} 失败")
    return json.loads(proc.stdout.decode("utf-8"))


def main() -> int:
    local_head = git(["rev-parse", "HEAD"]).decode("ascii").strip()
    remote_ref = api(f"/git/ref/heads/{BRANCH}")
    remote_head = remote_ref["object"]["sha"]
    if local_head == remote_head:
        print("GitHub 已经是最新版本，无需发布。")
        return 0

    compare = api(f"/compare/{remote_head}...{local_head}")
    if compare.get("status") != "ahead":
        print("\u8fdc\u7a0b main \u4e0e\u672c\u5730\u5206\u652f\u4e0d\u4e00\u81f4\uff0c\u5df2\u505c\u6b62\u53d1\u5e03\u3002")
        print("\u8bf7\u5148\u8fd0\u884c git fetch origin \u5e76\u68c0\u67e5 git log\u3002")
        return 1

    remote_commit = api(f"/git/commits/{remote_head}")
    base_tree = remote_commit["tree"]["sha"]
    message = git(["log", "-1", "--pretty=%B"]).decode("utf-8").strip()
    identity = git([
        "log", "-1", "--pretty=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI"
    ]).decode("utf-8", "replace").strip().split("\x00")
    if len(identity) != 6:
        raise SystemExit("\u65e0\u6cd5\u8bfb\u53d6\u63d0\u4ea4\u4f5c\u8005\u4fe1\u606f\u3002")
    author_name, author_email, author_date, committer_name, committer_email, committer_date = identity
    diff_text = git([
        "diff", "--name-status", "--no-renames", remote_head, local_head
    ]).decode("utf-8", "replace")

    entries: list[dict] = []
    for line in diff_text.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        path = path.strip()
        if status.startswith("D"):
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            print(f"删除 {path}")
            continue

        file_path = ROOT / path
        if not file_path.is_file():
            print(f"跳过不存在的文件：{path}")
            continue
        content = base64.b64encode(file_path.read_bytes()).decode("ascii")
        blob = api("/git/blobs", {"content": content, "encoding": "base64"}, "POST")
        mode_line = git(["ls-tree", "HEAD", "--", path]).decode("utf-8", "replace").strip()
        mode = mode_line.split()[0] if mode_line else "100644"
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})
        print(f"更新 {path}")

    if not entries:
        print("没有检测到需要同步的文件。")
        return 0

    tree = api("/git/trees", {"base_tree": base_tree, "tree": entries}, "POST")
    commit = api(
        "/git/commits",
        {
            "message": message,
            "tree": tree["sha"],
            "parents": [remote_head],
            "author": {
                "name": author_name,
                "email": author_email,
                "date": author_date,
            },
            "committer": {
                "name": committer_name,
                "email": committer_email,
                "date": committer_date,
            },
        },
        "POST",
    )
    api(
        f"/git/refs/heads/{BRANCH}",
        {"sha": commit["sha"], "force": False},
        "PATCH",
    )
    if commit["sha"] == local_head:
        git(["update-ref", f"refs/remotes/origin/{BRANCH}", commit["sha"]])
    else:
        local_tree = git(["rev-parse", "HEAD^{tree}"]).decode("ascii").strip()
        clean = not git(["status", "--porcelain"]).strip()
        if clean and tree["sha"] == local_tree:
            git(["reset", "--hard", commit["sha"]])
            git(["update-ref", f"refs/remotes/origin/{BRANCH}", commit["sha"]])
            print("\u5df2\u5c06\u672c\u5730\u5206\u652f\u540c\u6b65\u5230 API \u53d1\u5e03\u63d0\u4ea4\u3002")
        else:
            print("\u6ce8\u610f\uff1aAPI \u901a\u9053\u7684\u8fdc\u7aef\u63d0\u4ea4\u53f7\u4e0e\u672c\u5730\u4e0d\u540c\u3002")
            print("\u8bf7\u5148\u5907\u4efd\u672a\u63d0\u4ea4\u4fee\u6539\uff0c\u518d\u8fd0\u884c git fetch origin \u540e\u68c0\u67e5\u5206\u652f\u3002")
    print(f"REMOTE_COMMIT={commit['sha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())