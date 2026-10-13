/* 主题切换 + 站内搜索 + 代码复制 + 本地预览热刷新 */
(function () {
  "use strict";

  /* ---------- 深浅色 ---------- */
  var root = document.documentElement;
  var toggle = document.getElementById("theme-toggle");
  function currentTheme() {
    return root.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  }

  /* ---------- 代码复制 ---------- */
  document.querySelectorAll(".post-content pre").forEach(function (pre) {
    var wrap = document.createElement("div");
    wrap.className = "code-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.textContent = "复制";
    btn.addEventListener("click", function () {
      var code = pre.querySelector("code");
      var text = code ? code.innerText : pre.innerText;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = "已复制";
        setTimeout(function () { btn.textContent = "复制"; }, 1400);
      }).catch(function () { btn.textContent = "复制失败"; });
    });
    wrap.appendChild(btn);
  });

  /* ---------- 站内搜索 ---------- */
  var searchBox = document.querySelector(".search");
  var input = document.getElementById("search-input");
  var results = document.getElementById("search-results");
  if (searchBox && input && results) {
    var base = searchBox.getAttribute("data-root") || "";
    var index = null;
    var loading = false;

    function loadIndex() {
      if (index || loading) return;
      loading = true;
      fetch(base + "search.json")
        .then(function (r) { return r.json(); })
        .then(function (data) { index = data; })
        .catch(function () { index = []; });
    }

    function render(list, query) {
      results.innerHTML = "";
      if (!list.length) {
        var empty = document.createElement("div");
        empty.className = "no-result";
        empty.textContent = "没有找到包含「" + query + "」的文章";
        results.appendChild(empty);
      } else {
        list.slice(0, 12).forEach(function (item) {
          var a = document.createElement("a");
          a.href = base + item.url;
          var strong = document.createElement("strong");
          strong.textContent = item.title;
          var span = document.createElement("span");
          span.textContent = (item.date || "") + " · " + (item.summary || "");
          a.appendChild(strong);
          a.appendChild(span);
          results.appendChild(a);
        });
      }
      results.hidden = false;
    }

    function search(query) {
      var q = query.trim().toLowerCase();
      if (!q) { results.hidden = true; return; }
      if (!index) {
        loadIndex();
        setTimeout(function () { if (index) search(query); }, 300);
        return;
      }
      var matched = index.filter(function (item) {
        return (item.title + " " + (item.summary || "") + " " + (item.tags || []).join(" ") + " " + (item.content || ""))
          .toLowerCase().indexOf(q) !== -1;
      });
      render(matched, query);
    }

    input.addEventListener("focus", loadIndex);
    input.addEventListener("input", function () { search(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; results.hidden = true; input.blur(); }
      if (e.key === "Enter") {
        var first = results.querySelector("a");
        if (first) { window.location.href = first.href; }
      }
    });
    document.addEventListener("click", function (e) {
      if (!searchBox.contains(e.target)) results.hidden = true;
    });
  }

  /* ---------- 本地预览自动刷新（仅 serve.py 预览时生效） ---------- */
  if (location.protocol.indexOf("http") === 0) {
    var stamp = null;
    setInterval(function () {
      fetch("/__reload", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (v) {
          if (v === null) return;
          if (stamp === null) { stamp = v; }
          else if (v !== stamp) { location.reload(); }
        })
        .catch(function () {});
    }, 1200);
  }
})();