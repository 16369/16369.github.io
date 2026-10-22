"""Regression tests run only against disposable project copies."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import build
import check
import new_post


class BlogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="blog-tests-")
        self.root = Path(temporary.name).resolve()
        assert self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        self.addCleanup(temporary.cleanup)
        for module in (build, check, new_post):
            patcher = patch.object(module, "ROOT", self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.posts = self.root / "content" / "posts"
        self.posts.mkdir(parents=True)
        pages = self.root / "content" / "pages"
        pages.mkdir()
        (pages / "about.md").write_text("---\ntitle: About\n---\nAbout this blog.", encoding="utf-8")
        self.post = self.posts / "2026-10-19-example.md"
        self.post.write_text("---\ntitle: Example\ndate: 2026-10-19\ntags: [Python]\n---\n## Hello\nBody.", encoding="utf-8")
        (self.posts / "2026-10-19-draft.md").write_text("---\ntitle: Draft\ndraft: true\n---\nDraft body.", encoding="utf-8")
        shutil.copytree(PROJECT / "themes", self.root / "themes")
        self.cfg = json.loads((PROJECT / "blog.config.json").read_text(encoding="utf-8"))
        self.out = self.root / "public"
        for module, name, value in ((check, "PUBLIC", self.out), (new_post, "POSTS_DIR", self.posts)):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def build_site(self, **kwargs):
        builder = build.Builder(self.cfg, self.out, kwargs.pop("include_drafts", False), **kwargs)
        builder.run()
        return builder

    def snapshot(self):
        return {str(p.relative_to(self.out)): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}

    def assert_no_staging(self):
        self.assertEqual(list(self.root.rglob(".blog-build-*")), [])

    def test_full_build_and_drafts(self):
        self.build_site()
        self.assertEqual(check.main(), 0)
        self.assertFalse((self.out / "posts" / "draft.html").exists())
        self.build_site(include_drafts=True)
        self.assertTrue((self.out / "posts" / "draft.html").is_file())
        self.assertEqual(check.main(), 0)
        self.assert_no_staging()

    def test_rejects_protected_and_unrecognized_directories(self):
        for relative in ("content", "content/posts", "themes", "static", "tools", "tests", ".git", ".github", ".venv", "notes"):
            target = self.root / relative
            target.mkdir(parents=True, exist_ok=True)
            sentinel = target / "keep.txt"
            sentinel.write_text("do not delete", encoding="utf-8")
            with self.subTest(path=relative), self.assertRaises(ValueError):
                build.Builder(self.cfg, target, False).run()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not delete")
        for target in (self.root, self.root.parent, self.post):
            with self.subTest(path=target), self.assertRaises(ValueError):
                build.Builder(self.cfg, target, False).run()
        self.assert_no_staging()

    def test_protected_directory_rejected_even_with_build_marker_and_no_clean(self):
        target = self.root / "content"
        (target / ".blog-build.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            build.Builder(self.cfg, target, False, clean=False).run()
        self.assertTrue(self.post.exists())

    def test_rejects_symlink_output_and_parent(self):
        self.build_site()
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.out, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this host")
        before = self.snapshot()
        for target in (alias, alias / "child"):
            with self.subTest(path=target), self.assertRaises(ValueError):
                build.Builder(self.cfg, target, False).run()
        self.assertEqual(self.snapshot(), before)

    def test_new_custom_output_directory(self):
        destination = self.root / "dist" / "site"
        build.Builder(self.cfg, destination, False).run()
        self.assertTrue((destination / "index.html").is_file())
        self.assert_no_staging()

    def test_bad_front_matter_preserves_previous_site(self):
        self.build_site()
        before = self.snapshot()
        self.post.write_text("---\ntitle: Python: broken\n---\nBody", encoding="utf-8")
        with self.assertRaises(build.yaml.YAMLError):
            self.build_site()
        self.assertEqual(self.snapshot(), before)
        self.assert_no_staging()

    def test_template_failure_preserves_previous_site(self):
        self.build_site()
        before = self.snapshot()
        (self.root / "themes/default/templates/post.html").write_text("{% invalid %}", encoding="utf-8")
        from jinja2 import TemplateSyntaxError
        with self.assertRaises(TemplateSyntaxError):
            self.build_site()
        self.assertEqual(self.snapshot(), before)
        self.assert_no_staging()

    def test_output_swap_failure_restores_previous_site(self):
        self.build_site()
        before = self.snapshot()
        rename = Path.rename

        for failure in (OSError, KeyboardInterrupt):
            def fail_install(source, target):
                if source.name == "site" and target == self.out:
                    raise failure("Simulated interrupted swap")
                return rename(source, target)

            with self.subTest(failure=failure), patch.object(Path, "rename", fail_install), self.assertRaises(failure):
                self.build_site()
            self.assertEqual(self.snapshot(), before)
            self.assert_no_staging()

    def test_failed_restore_keeps_backup_for_recovery(self):
        self.build_site()
        old_index = (self.out / "index.html").read_bytes()
        rename = Path.rename

        def fail_install_and_restore(source, target):
            if source.name in {"site", "previous"} and target == self.out:
                raise OSError("Simulated file lock")
            return rename(source, target)

        with patch.object(Path, "rename", fail_install_and_restore), self.assertRaisesRegex(RuntimeError, "旧站点保存在"):
            self.build_site()
        backups = list(self.root.glob(".blog-build-*/previous/index.html"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), old_index)

    def test_no_clean_retains_extra_files_and_clean_removes_them(self):
        self.build_site()
        extra = self.out / "extra.txt"
        extra.write_text("keep", encoding="utf-8")
        self.build_site(clean=False)
        self.assertEqual(extra.read_text(encoding="utf-8"), "keep")
        self.build_site()
        self.assertFalse(extra.exists())
        self.assert_no_staging()

    def test_reload_marker_only_in_preview_build(self):
        self.build_site(live_reload=True)
        self.assertIn('data-live-reload="true"', (self.out / "index.html").read_text(encoding="utf-8"))
        self.build_site()
        self.assertNotIn("data-live-reload", (self.out / "index.html").read_text(encoding="utf-8"))

    def test_root_relative_and_encoded_image_links(self):
        self.build_site()
        images = self.out / "images"
        images.mkdir()
        (images / "图片.png").write_bytes(b"fixture")
        page = self.out / "posts" / "example.html"
        page.write_text('<html><img src="/images/%E5%9B%BE%E7%89%87.png?v=1#image"><img src="../images/图片.png"><a href="/">Home</a></html>', encoding="utf-8")
        self.assertEqual(check.check_html([page]), [])
        (images / "图片.png").unlink()
        self.assertEqual(len(check.check_html([page])), 2)

    def test_checker_rejects_links_outside_site_and_empty_directories(self):
        self.build_site()
        (self.root / "outside.txt").write_text("not served", encoding="utf-8")
        (self.out / "empty").mkdir()
        page = self.out / "posts" / "example.html"
        page.write_text('<html><a href="../../outside.txt">Outside</a><a href="/empty/">Empty</a></html>', encoding="utf-8")
        self.assertEqual(len(check.check_html([page])), 2)

    def test_new_post_preserves_special_titles_and_metadata(self):
        titles = ["Python: learning notes", "Notes #1", "[中文] 标题", 'A "quote"', "true", "第一行\n第二行"]
        for number, title in enumerate(titles):
            with self.subTest(title=title):
                self.assertEqual(new_post.main([title, "--slug", f"special-{number}", "--tags", "true,Python: notes,tag #1", "--category", "[notes]", "--draft", "--date", "2026-10-19"]), 0)
                path = self.posts / f"2026-10-19-special-{number}.md"
                meta, body = build.split_front_matter(path.read_text(encoding="utf-8"))
                self.assertEqual(meta["title"], title)
                self.assertEqual(meta["tags"], ["true", "Python: notes", "tag #1"])
                self.assertEqual(meta["categories"], ["[notes]"])
                self.assertIs(meta["draft"], True)
                self.assertIn("## 小标题", body)
        self.build_site(include_drafts=True)
        self.assertEqual(check.main(), 0)


if __name__ == "__main__":
    unittest.main()
