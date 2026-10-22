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
    function updateThemeButton() {
      var dark = currentTheme() === "dark";
      var label = dark ? "切换到浅色模式" : "切换到深色模式";
      toggle.setAttribute("aria-label", label);
      toggle.setAttribute("title", label);
      toggle.setAttribute("aria-pressed", String(dark));
    }
    updateThemeButton();
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      updateThemeButton();
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
    var loading = null;
    var searchVersion = 0;

    function loadIndex() {
      if (index !== null) return Promise.resolve(index);
      if (!loading) {
        loading = fetch(base + "search.json")
          .then(function (r) {
            if (!r.ok) throw new Error("搜索索引加载失败");
            return r.json();
          })
          .then(function (data) {
            if (!Array.isArray(data)) throw new Error("搜索索引格式错误");
            index = data;
            loading = null;
            return data;
          })
          .catch(function (error) {
            loading = null;
            throw error;
          });
      }
      return loading;
    }

    function dismissResults() {
      searchVersion += 1;
      results.hidden = true;
    }

    function showMessage(message) {
      results.innerHTML = "";
      var status = document.createElement("div");
      status.className = "no-result";
      status.textContent = message;
      results.appendChild(status);
      results.hidden = false;
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
      var version = ++searchVersion;
      var q = query.trim().toLowerCase();
      if (!q) { dismissResults(); return; }
      if (index === null) showMessage("正在搜索…");
      loadIndex()
        .then(function (data) {
          if (version !== searchVersion) return;
          var matched = data.filter(function (item) {
            return (item.title + " " + (item.summary || "") + " " + (item.tags || []).join(" ") + " " + (item.content || ""))
              .toLowerCase().indexOf(q) !== -1;
          });
          render(matched, query);
        })
        .catch(function () {
          if (version === searchVersion) showMessage("搜索暂时不可用，请重新输入重试");
        });
    }

    input.addEventListener("focus", function () {
      if (input.value.trim()) search(input.value);
      else loadIndex().catch(function () {});
    });
    input.addEventListener("input", function () { search(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; dismissResults(); input.blur(); }
      if (e.key === "Enter" && !results.hidden) {
        var first = results.querySelector("a");
        if (first) { window.location.href = first.href; }
      }
    });
    document.addEventListener("click", function (e) {
      if (!searchBox.contains(e.target)) dismissResults();
    });
    document.addEventListener("keydown", function (e) {
      var target = e.target;
      var editing = target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable);
      if (e.key === "/" && !editing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        input.focus();
      }
    });
  }

  /* ---------- 本地预览自动刷新（仅 serve.py 预览时生效） ---------- */
  var localHost = ["localhost", "127.0.0.1", "[::1]"].indexOf(location.hostname) !== -1;
  if (localHost && root.getAttribute("data-live-reload") === "true" && location.protocol.indexOf("http") === 0) {
    var stamp = null;
    var reloadTimer = setInterval(function () {
      fetch("/__reload", { cache: "no-store" })
        .then(function (r) {
          if (!r.ok) { clearInterval(reloadTimer); return null; }
          return r.text();
        })
        .then(function (v) {
          if (v === null) return;
          if (stamp === null) { stamp = v; }
          else if (v !== stamp) { location.reload(); }
        })
        .catch(function () {});
    }, 1200);
  }
})();
