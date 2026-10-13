#!/usr/bin/env python3
"""Publish local Git commits through the GitHub API.

This is a fallback for networks where `git push` cannot connect to
github.com, while api.github.com remains reachable.

Commits from the remote branch tip to HEAD are replayed one by one through
the Git Data API. Commit messages and author/committer metadata are preserved,
so linear local history normally produces the same commit SHAs remotely.
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


def _force_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdout()


def _git_command(args: list[str]) -> list[str]:
    return ["git", "-c", "core.quotepath=false", *args]


def git(args: list[str]) -> bytes:
    proc = subprocess.run(
        _git_command(args),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(message or f"git {' '.join(args)} 失败")
    return proc.stdout


def git_ok(args: list[str]) -> bool:
    proc = subprocess.run(
        _git_command(args),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def api(path: str, payload: dict | None = None, method: str = "GET") -> dict:
    command = [GH, "api"]
    if payload is not None:
        command += ["--input", "-"]
    command += ["--method", method, f"repos/{OWNER}/{REPO}{path}"]
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(
        command,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(message or f"gh api {path} 失败")
    return json.loads(proc.stdout.decode("utf-8"))


def commit_message(commit_sha: str) -> str:
    raw = git(["cat-file", "commit", commit_sha])
    parts = raw.split(b"\n\n", 1)
    if len(parts) != 2:
        raise SystemExit(f"无法读取提交说明：{commit_sha}")
    return parts[1].decode("utf-8", "replace")


def commit_identity(commit_sha: str) -> tuple[str, str, str, str, str, str]:
    output = git([
        "show",
        "-s",
        "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI",
        commit_sha,
    ]).decode("utf-8", "replace").strip()
    identity = output.split("\x00")
    if len(identity) != 6:
        raise SystemExit(f"无法读取提交作者信息：{commit_sha}")
    return tuple(identity)  # type: ignore[return-value]


def commit_parents(commit_sha: str) -> list[str]:
    output = git(["show", "-s", "--format=%P", commit_sha]).decode("ascii").strip()
    return output.split() if output else []


def changed_entries(parent_sha: str, commit_sha: str) -> list[dict]:
    diff_text = git([
        "diff",
        "--name-status",
        "--no-renames",
        parent_sha,
        commit_sha,
    ]).decode("utf-8", "replace")
    entries: list[dict] = []

    for line in diff_text.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        path = path.strip()
        if status.startswith("D"):
            entries.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": None,
            })
            print(f"删除 {path}")
            continue

        mode_line = git(["ls-tree", commit_sha, "--", path]).decode(
            "utf-8", "replace"
        ).strip()
        if not mode_line:
            raise SystemExit(f"找不到文件对象：{path}")
        mode = mode_line.split()[0]
        content = git(["cat-file", "blob", f"{commit_sha}:{path}"])
        blob = api(
            "/git/blobs",
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
            "POST",
        )
        entries.append({
            "path": path,
            "mode": mode,
            "type": "blob",
            "sha": blob["sha"],
        })
        print(f"更新 {path}")

    return entries


def main() -> int:
    local_head = git(["rev-parse", "HEAD"]).decode("ascii").strip()
    remote_ref = api(f"/git/ref/heads/{BRANCH}")
    remote_head = remote_ref["object"]["sha"]

    if local_head == remote_head:
        print("GitHub 已经是最新版本，无需发布。")
        return 0

    if not git_ok(["cat-file", "-e", f"{remote_head}^{{commit}}"]):
        print("本地缺少远端提交对象，无法通过 API 安全比较。")
        print("请先执行 git fetch origin，再重新运行发布。")
        return 1

    if not git_ok(["merge-base", "--is-ancestor", remote_head, local_head]):
        print("远端 main 不是本地 HEAD 的祖先，分支可能已经分叉。")
        print("为避免覆盖远端内容，已停止发布。")
        print("请先执行 git fetch origin 并检查 git log。")
        return 1

    commits_text = git([
        "rev-list",
        "--reverse",
        "--topo-order",
        f"{remote_head}..{local_head}",
    ]).decode("ascii")
    commits = [line.strip() for line in commits_text.splitlines() if line.strip()]
    if not commits:
        print("没有检测到需要同步的本地提交。")
        return 1

    remote_commit = api(f"/git/commits/{remote_head}")
    mapping: dict[str, str] = {remote_head: remote_head}
    tree_by_sha: dict[str, str] = {remote_head: remote_commit["tree"]["sha"]}

    for commit_sha in commits:
        parents = commit_parents(commit_sha)
        if not parents:
            raise SystemExit(f"待发布提交没有父提交：{commit_sha}")

        mapped_parents: list[str] = []
        for parent in parents:
            mapped = mapping.get(parent)
            if mapped is None:
                raise SystemExit(
                    f"提交 {commit_sha} 的父提交 {parent} 尚未发布，"
                    "当前 API 通道暂不支持这种分支结构。"
                )
            mapped_parents.append(mapped)

        base_tree = tree_by_sha[mapped_parents[0]]
        entries = changed_entries(parents[0], commit_sha)
        tree = api(
            "/git/trees",
            {"base_tree": base_tree, "tree": entries},
            "POST",
        )

        name, email, date, c_name, c_email, c_date = commit_identity(commit_sha)
        new_commit = api(
            "/git/commits",
            {
                "message": commit_message(commit_sha),
                "tree": tree["sha"],
                "parents": mapped_parents,
                "author": {"name": name, "email": email, "date": date},
                "committer": {
                    "name": c_name,
                    "email": c_email,
                    "date": c_date,
                },
            },
            "POST",
        )
        mapping[commit_sha] = new_commit["sha"]
        tree_by_sha[new_commit["sha"]] = tree["sha"]
        print(f"已创建远端提交 {commit_sha} -> {new_commit['sha']}")

    published_head = mapping[commits[-1]]
    api(
        f"/git/refs/heads/{BRANCH}",
        {"sha": published_head, "force": False},
        "PATCH",
    )

    if published_head == local_head:
        git(["update-ref", f"refs/remotes/origin/{BRANCH}", published_head])
        print("本地与 GitHub 提交号完全一致。")
    else:
        print("发布成功，但 API 重建后的提交号与本地不同。")
        print("请先备份内容，再执行 git fetch origin 后检查分支。")

    print(f"REMOTE_COMMIT={published_head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())