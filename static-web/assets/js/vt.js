/* ===== 页面切换过渡（View Transitions） =====
   同源多页跳转时用整页推移代替白屏闪烁：
   点侧栏/卡片链接 → 按导航顺序判断方向（向下/向上）→ 新页面滑入。 */
(function () {
  "use strict";

  // 与侧栏导航顺序保持一致；未列出的页面按“向下”处理
  var ORDER = [
    "index", "courses", "outline", "lesson",
    "tasks", "rehearsal", "training",
    "tutor", "review",
    "analytics", "tools",
    "student", "files", "settings", "assistant", "login"
  ];

  function pageKey(pathname) {
    var seg = pathname.split("/").pop().replace(/\.html?$/i, "");
    return seg || "index";
  }

  function indexOfKey(pathname) {
    return ORDER.indexOf(pageKey(pathname));
  }

  function record(targetHref, fromHref) {
    var url;
    try { url = new URL(targetHref, location.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;

    var from = indexOfKey((fromHref ? new URL(fromHref, location.href) : url).pathname);
    var to = indexOfKey(url.pathname);
    var dir = (from >= 0 && to >= 0 && to < from) ? "up" : "down";
    try { sessionStorage.setItem("tc-vt-dir", dir); } catch (err) { /* 隐私模式忽略 */ }
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    if (a.target && a.target !== "_self") return;

    var href = a.getAttribute("href");
    if (!href || /^(#|javascript:|mailto:|tel:)/i.test(href)) return;

    record(a.href, location.href);
  }, true);

  // 移动端顶栏的页面导航下拉框（site.js 动态生成 .nav-mobile）
  document.addEventListener("change", function (e) {
    var sel = e.target;
    if (!sel || !sel.classList || !sel.classList.contains("nav-mobile")) return;
    if (!sel.value) return;
    record(sel.value, location.href);
  }, true);

  // 新页面在首次绘制前套用方向，供 site.css 里的伪元素动画读取
  try {
    var saved = sessionStorage.getItem("tc-vt-dir");
    if (saved === "up" || saved === "down") {
      document.documentElement.setAttribute("data-vt", saved);
    }
    sessionStorage.removeItem("tc-vt-dir"); // 只用一次，避免后续程序化跳转沿用旧方向
  } catch (err) { /* ignore */ }
})();