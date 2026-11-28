/* Optional pointer effects. Native pointers and reduced-motion preferences win. */
(function () {
  "use strict";
  if (window.EduCursor || !window.matchMedia) return;
  var fine = window.matchMedia("(hover: hover) and (pointer: fine)");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var key = "edu.cursor", enabled = false, running = false, seen = false, paused = false;
  var mx = 0, my = 0, rx = 0, ry = 0, raf = 0, dirty = true, cards = [];
  var ring, spot, observer;
  var root = document.documentElement;
  var nativeZone = "input, textarea, select, [contenteditable]:not([contenteditable='false']), [disabled]";
  var interactive = "a, button, [role='button'], label, summary, .btn";
  try { enabled = localStorage.getItem(key) === "on"; } catch (e) {}

  function clearCards() {
    cards.forEach(function (o) { o.el.classList.remove("is-spotlit"); });
    cards = [];
  }
  function cancel() {
    if (raf) window.cancelAnimationFrame(raf);
    raf = 0;
  }
  function hide() {
    seen = false;
    cancel();
    root.classList.add("tc-cursor-hidden");
    clearCards();
    dirty = true;
  }
  function schedule() {
    if (running && seen && !paused && !document.hidden && !raf) raf = window.requestAnimationFrame(paint);
  }
  function paint() {
    raf = 0;
    if (!running || !seen || paused || document.hidden) return;
    rx += (mx - rx) * 0.2;
    ry += (my - ry) * 0.2;
    if (Math.abs(mx - rx) + Math.abs(my - ry) < 0.25) { rx = mx; ry = my; }
    ring.style.transform = "translate3d(" + rx + "px," + ry + "px,0)";
    root.style.setProperty("--tc-mx", mx + "px");
    root.style.setProperty("--tc-my", my + "px");
    if (dirty) {
      clearCards();
      cards = Array.prototype.map.call(document.querySelectorAll(".card, .kpi"), function (el) {
        return { el: el, rect: el.getBoundingClientRect() };
      });
      dirty = false;
    }
    cards.forEach(function (o) {
      var r = o.rect;
      var dx = Math.max(r.left - mx, mx - r.right, 0);
      var dy = Math.max(r.top - my, my - r.bottom, 0);
      o.el.classList.toggle("is-spotlit", dx * dx + dy * dy <= 240 * 240);
    });
    if (rx !== mx || ry !== my) schedule();
  }
  function move(e) {
    if (paused || document.hidden) return;
    if (e.target && e.target.closest && e.target.closest(nativeZone)) { hide(); return; }
    mx = e.clientX; my = e.clientY;
    if (!seen) { rx = mx; ry = my; seen = true; }
    ring.classList.toggle("is-active", !!(e.target && e.target.closest && e.target.closest(interactive)));
    root.classList.remove("tc-cursor-hidden");
    schedule();
  }
  function leave(e) { if (!e.relatedTarget) hide(); }
  function blur() { paused = true; hide(); }
  function focus() { paused = false; }
  function visibility() { if (document.hidden) hide(); }
  function keyboard(e) { if (e.key === "Tab") hide(); }
  function invalidate() { dirty = true; schedule(); }
  var bindings = [
    [document, "mousemove", move], [document, "mouseout", leave],
    [document, "keydown", keyboard], [document, "scroll", invalidate, true],
    [document, "visibilitychange", visibility], [window, "blur", blur],
    [window, "focus", focus], [window, "resize", invalidate]
  ];
  function start() {
    if (running || !document.body) return;
    running = true; paused = !document.hasFocus();
    ring = document.createElement("div"); ring.className = "tc-cursor-ring";
    spot = document.createElement("div"); spot.className = "tc-spotlight";
    [ring, spot].forEach(function (el) { el.setAttribute("aria-hidden", "true"); document.body.appendChild(el); });
    root.classList.add("tc-cursor-on", "tc-cursor-hidden");
    bindings.forEach(function (b) { b[0].addEventListener(b[1], b[2], b[3] || false); });
    if (window.MutationObserver) {
      observer = new MutationObserver(invalidate);
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }
  function stop() {
    if (!running) return;
    running = false;
    hide();
    if (observer) { observer.disconnect(); observer = null; }
    bindings.forEach(function (b) { b[0].removeEventListener(b[1], b[2], b[3] || false); });
    ring.remove(); spot.remove();
    root.classList.remove("tc-cursor-on", "tc-cursor-hidden");
    root.style.removeProperty("--tc-mx"); root.style.removeProperty("--tc-my");
  }
  function sync() {
    if (enabled && fine.matches && !reduced.matches) start(); else stop();
    ["lookCursor", "pfCursor"].forEach(function (id) {
      var input = document.getElementById(id);
      if (input) { input.checked = enabled; input.disabled = reduced.matches || !fine.matches; }
    });
  }
  function setEnabled(value) {
    enabled = !!value;
    try { localStorage.setItem(key, enabled ? "on" : "off"); } catch (e) {}
    sync();
  }
  function storage(e) {
    if (e.key === key || e.key === null) {
      try { enabled = localStorage.getItem(key) === "on"; } catch (err) { enabled = false; }
      sync();
    }
  }
  function init() {
    ["lookCursor", "pfCursor"].forEach(function (id) {
      var input = document.getElementById(id);
      if (input) input.addEventListener("change", function () { setEnabled(input.checked); });
    });
    sync();
  }
  window.EduCursor = { setEnabled: setEnabled, isEnabled: function () { return enabled; } };
  [fine, reduced].forEach(function (mq) {
    if (mq.addEventListener) mq.addEventListener("change", sync);
  });
  window.addEventListener("storage", storage);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
