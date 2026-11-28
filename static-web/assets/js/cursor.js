/* ===== 致壹 智能教育工作台 · 自定义光标 =====
   12px 主题色圆点替换默认光标；圆环带轻微延迟跟随；
   悬停链接/按钮时圆环放大到 48px 半透明；触屏与键盘/减少动效环境不启用。 */
(function () {
  "use strict";

  var mqFine = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : null;
  if (!mqFine || !mqFine.matches) return;              // 触屏 / 粗指针设备：完全不启用
  if (document.documentElement.classList.contains("tc-cursor-on")) return;

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var INTERACTIVE = "a, button, [role='button'], input, select, textarea, label, summary, .btn, [data-cursor='ring']";

  var dot = document.createElement("div");
  var ring = document.createElement("div");
  var spot = document.createElement("div");
  dot.className = "tc-cursor-dot";
  ring.className = "tc-cursor-ring";
  spot.className = "tc-spotlight";
  dot.setAttribute("aria-hidden", "true");
  ring.setAttribute("aria-hidden", "true");
  spot.setAttribute("aria-hidden", "true");

  var mx = 0, my = 0, rx = 0, ry = 0, seen = false, raf = 0;

  // ---- 聚光灯：半径 240px 内的卡片描边被点亮 ----
  var SPOT_R = 240;          // 点亮半径
  var SPOT_OFF = 280;        // 熄灭半径（滞回，防止边缘闪烁）
  var cards = [], rects = [], dirty = true, lastX = -1, lastY = -1;

  function collectCards() {
    cards = Array.prototype.slice.call(document.querySelectorAll(".card, .kpi"));
    dirty = true;
  }

  function refreshRects() {
    rects = [];
    for (var i = 0; i < cards.length; i++) {
      var el = cards[i], r = el.getBoundingClientRect();
      rects.push({ el: el, l: r.left, t: r.top, r: r.right, b: r.bottom, lit: el.classList.contains("is-spotlit") });
    }
    dirty = false;
  }

  function paintCards() {
    if (!cards.length) return;
    if (dirty) refreshRects();
    for (var i = 0; i < rects.length; i++) {
      var o = rects[i];
      var dx = mx < o.l ? o.l - mx : (mx > o.r ? mx - o.r : 0);
      var dy = my < o.t ? o.t - my : (my > o.b ? my - o.b : 0);
      var d = Math.sqrt(dx * dx + dy * dy);
      if (!o.lit && d <= SPOT_R) { o.lit = true; o.el.classList.add("is-spotlit"); }
      else if (o.lit && d >= SPOT_OFF) { o.lit = false; o.el.classList.remove("is-spotlit"); }
    }
  }

  function onMove(e) {
    mx = e.clientX;
    my = e.clientY;
    if (!seen) {
      seen = true;
      rx = mx;
      ry = my;
      document.documentElement.classList.remove("tc-cursor-hidden");
    }
    dot.style.transform = "translate3d(" + mx + "px," + my + "px,0)";
    var t = e.target;
    var hit = t && t.closest ? t.closest(INTERACTIVE) : null;
    var active = !!hit;
    ring.classList.toggle("is-active", active);
    dot.classList.toggle("is-subtle", active);
  }

  function onLeave() {
    document.documentElement.classList.add("tc-cursor-hidden");
  }

  function onEnter() {
    if (seen) document.documentElement.classList.remove("tc-cursor-hidden");
  }

  function loop() {
    var k = reduce ? 1 : 0.16;                          // 圆环跟随的平滑系数，越小越“拖”
    rx += (mx - rx) * k;
    ry += (my - ry) * k;
    ring.style.transform = "translate3d(" + rx + "px," + ry + "px,0)";

    // 鼠标坐标写入 CSS 变量，由样式里的 radial-gradient 实时绘制光圈
    if (mx !== lastX || my !== lastY) {
      lastX = mx;
      lastY = my;
      var root = document.documentElement;
      root.style.setProperty("--tc-mx", mx + "px");
      root.style.setProperty("--tc-my", my + "px");
      paintCards();
    }
    raf = window.requestAnimationFrame(loop);
  }

  function start() {
    if (!document.body) return;
    document.body.appendChild(spot);
    document.body.appendChild(dot);
    document.body.appendChild(ring);
    document.documentElement.classList.add("tc-cursor-on", "tc-cursor-hidden");
    document.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseleave", onLeave);
    document.addEventListener("mouseenter", onEnter);
    document.addEventListener("mouseout", function (e) { if (!e.relatedTarget) onLeave(); });
    window.addEventListener("blur", onLeave);
    window.addEventListener("resize", function () { dirty = true; });
    document.addEventListener("scroll", function () { dirty = true; }, { passive: true, capture: true });
    collectCards();
    if (!raf) loop();
  }

  function stop() {
    if (raf) { window.cancelAnimationFrame(raf); raf = 0; }
    dot.remove();
    ring.remove();
    spot.remove();
    for (var i = 0; i < rects.length; i++) { rects[i].el.classList.remove("is-spotlit"); rects[i].lit = false; }
    document.documentElement.classList.remove("tc-cursor-on", "tc-cursor-hidden");
  }

  // 设备能力变化（如外接鼠标 / 切换平板模式）时自动启停
  function sync() {
    if (mqFine.matches) start();
    else stop();
  }
  if (mqFine.addEventListener) mqFine.addEventListener("change", sync);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync);
  } else {
    sync();
  }
})();