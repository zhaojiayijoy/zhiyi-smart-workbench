/* ===== 致壹 智能教育工作台 · 静态站公共脚本 ===== */
(function () {
  "use strict";

  var ICONS = {
    home: '<path d="M2.5 7.5 8 2.5l5.5 5V14h-4v-4h-3v4h-4z"/>',
    studentHome: '<path d="M2.9 6.9 8 2.3l5.1 4.6v4.5a1 1 0 0 1-1 1H3.9a1 1 0 0 1-1-1z"/>' +
      '<circle cx="8" cy="8.2" r="1.15"/>' +
      '<path d="M3 13.6h10"/>' +
      '<circle cx="3" cy="13.6" r=".9" fill="currentColor" stroke="none"/>' +
      '<circle cx="13" cy="13.6" r=".9" fill="currentColor" stroke="none"/>',
    openbook: '<path d="M2.8 4.4c1.8-.8 3.6-.7 5.2.2 1.6-.9 3.4-1 5.2-.2v7.1c-1.8-.8-3.6-.7-5.2.2-1.6-.9-3.4-1-5.2-.2z"/>' +
      '<path d="M8 4.6v7.3"/><path d="M4.6 6.4c.9-.3 1.8-.3 2.6.1"/>',
    book: '<path d="M4 2.5h5.5a2 2 0 0 1 2 2V14H6a2 2 0 0 1-2-2z"/><path d="M4 2.5V14"/>',
    spark: '<path d="M8 2.5 9.2 6l3.5 1.2L9.2 8.4 8 12 6.8 8.4 3.3 7.2 6.8 6z"/>',
    prep: '<path d="M10.2 2.6 12.6 5 6.4 11.2 3.4 11.9 4.1 8.9z"/><path d="M9 3.8 11.4 6.2"/>' +
      '<rect x="8.2" y="8.6" width="5.8" height="4.2" rx="1.2"/><path d="M9.6 10.7h2.8"/>' +
      '<path d="M4.6 2.4 5 3.5 6.1 3.9 5 4.3 4.6 5.4 4.2 4.3 3.1 3.9 4.2 3.5z"/>',
    lab: '<rect x="2.2" y="3.4" width="9.4" height="7.2" rx="1.2"/><path d="M3.4 4.6h7"/>' +
      '<path d="M10.6 7.6h1.8v2.2l1.4 2.3c.3.6-.1 1.2-.8 1.2h-3c-.7 0-1.1-.6-.8-1.2l1.4-2.3z"/>' +
      '<path d="M9.9 11.4h3.2"/>',
    tool: '<path d="M10.5 2.5 13.5 5.5 11.6 7.4 8.6 4.4z"/><path d="M8.6 6.2 3 11.8V13h1.2l5.6-5.6"/>',
    ask: '<rect x="2.6" y="3.2" width="10.8" height="7.2" rx="2.2"/><path d="M6.4 10.4 5.2 13.1 8.9 10.4"/>' +
      '<path d="M6.9 5.5a1.3 1.3 0 1 1 1.8 1.2c-.4.2-.5.5-.5.9"/>' +
      '<circle cx="8.1" cy="9.1" r="0.55" fill="currentColor" stroke="none"/>',
    chat: '<path d="M2.8 3h10.4v7.2H7L3.4 13V3z"/>',
    reviewpen: '<path d="M11.4 2.6 13.4 4.6 6.2 11.8 3.4 12.5 4.1 9.7z"/><path d="M10.3 3.7 12.3 5.7"/>' +
      '<circle cx="11.8" cy="11.8" r="2.2"/><path d="M10.8 11.8l.8.8 1.5-1.5"/>',
    feedbackNote: '<rect x="2.4" y="3.1" width="8.3" height="8.9" rx="1.5"/>' +
      '<circle cx="4.4" cy="3.1" r=".85" fill="currentColor" stroke="none"/>' +
      '<path d="M5.6 6.9 7.6 8.9M7.6 6.9 5.6 8.9"/>' +
      '<path d="M14 11.4a2.2 2.2 0 1 1-2.2-2.2"/><path d="M11.8 9.2v2.2h2.2"/>',
    check: '<path d="M3 8.4 6.2 11.6 13 4.8"/>',
    chartline: '<rect x="2.6" y="2.6" width="10.8" height="10.8" rx="1.7"/>' +
      '<path d="M4.5 10.2 6.5 8 7.9 9.1 11.4 5.4"/>' +
      '<path d="M4.5 11.6h6.6"/>',
    chart: '<path d="M3 13V8.2M6.7 13V4.5M10.4 13V9.4M13.5 13V6.6"/><path d="M2 13.6h12"/>',
    grid: '<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/>',
    outlineDoc: '<path d="M3 2.6h6.1l3.1 3.1v7.7H3z"/><path d="M9.1 2.6v3.1h3.1"/>' +
      '<path d="M4.8 6.4h4"/><path d="M4.8 8.6h3"/>' +
      '<path d="M11.4 4.6 13.3 6.5 9.9 9.9 8.5 10.2 8.8 8.8z"/><path d="M10.6 5.4 12.5 7.3"/>',
    file: '<path d="M4 2.5h5.5L12.5 5.5V13.5H4z"/><path d="M9.3 2.6v3h3"/>',
    resources: '<path d="M2.4 6.6h3.2l1.2 1.6h6.8v5a1.2 1.2 0 0 1-1.2 1.2H3.6a1.2 1.2 0 0 1-1.2-1.2z"/>' +
      '<path d="M7.2 8.2V2.9h3.6L12.4 4.5v3.7"/>' +
      '<path d="M8.4 5h2.4"/><path d="M8.4 6.4h1.6"/>',
    clock: '<circle cx="8" cy="8" r="5.4"/><path d="M8 5v3.2l2.2 1.4"/>',
    gear: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M12.4 3.6l-1.1 1.1M4.7 11.3l-1.1 1.1"/>',
    user: '<circle cx="8" cy="5.6" r="2.6"/><path d="M3.2 13.5c.6-2.3 2.5-3.6 4.8-3.6s4.2 1.3 4.8 3.6"/>',
    plus: '<path d="M8 3v10M3 8h10"/>'
  };

  function ic(name, size) {
    var s = size || 16;
    return '<svg class="ic" width="' + s + '" height="' + s + '" viewBox="0 0 16 16" fill="none" ' +
      'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (ICONS[name] || ICONS.grid) + "</svg>";
  }

  var GROUPS = [
    {
      label: "课前准备",
      items: [
        { href: "courses.html", icon: "openbook", text: "课程项目", page: "courses" },
        { href: "files.html", icon: "resources", text: "课程资源", page: "files" },
        { href: "outline.html", icon: "outlineDoc", text: "备课大纲", page: "outline" },
        { href: "lesson.html", icon: "prep", text: "一键备课", page: "lesson" }
      ]
    },
    {
      label: "发布与课堂",
      items: [
        { href: "tasks.html", icon: "clock", text: "任务中心", page: "tasks" },
        { href: "rehearsal.html", icon: "eye", text: "课堂预演", page: "rehearsal" },
        { href: "training.html", icon: "lab", text: "创建实训", page: "training" }
      ]
    },
    {
      label: "答疑与批改",
      items: [
        { href: "tutor.html", icon: "ask", text: "学生答疑", page: "tutor" },
        { href: "review.html", icon: "reviewpen", text: "作业评审", page: "review" }
      ]
    },
    {
      label: "分析与工具",
      items: [
        { href: "analytics.html", icon: "chartline", text: "学情分析", page: "analytics" },
        { href: "tools.html", icon: "tool", text: "教学工具", page: "tools" }
      ]
    }
  ];

  var STUDENT_GROUPS = [
    {
      label: "我的学习",
      items: [
        { href: "student.html#home", icon: "studentHome", text: "学生首页", page: "student" },
        { href: "student.html#tasks", icon: "clock", text: "我的任务", page: "student" },
        { href: "student.html#qa", icon: "chat", text: "我的答疑", page: "student" },
        { href: "student.html#feedback", icon: "feedbackNote", text: "教师反馈", page: "student" },
        { href: "student.html#review", icon: "book", text: "错题回顾", page: "student" },
        { href: "student.html#settings", icon: "user", text: "设置", page: "student" }
      ]
    }
  ];

  var TITLES = {
    index: "工作台首页", courses: "课程项目", outline: "备课大纲", lesson: "一键备课", training: "创建实训",
    tutor: "学生答疑", review: "作业评审", analytics: "学情分析", assistant: "AI 助手",
    files: "课程资源", tasks: "任务中心", settings: "设置", student: "学生空间", tools: "教学工具"
  };

  var page = document.body.getAttribute("data-page") || "index";
  var isStudent = document.body.getAttribute("data-mode") === "student";

  /* ---------- 全局课程状态（唯一真相源） ---------- */
  function applyPrefs() {
    var p = {};
    try { p = JSON.parse(localStorage.getItem("edu.prefs") || "{}"); } catch (e) {}
    var root = document.documentElement;
    applyPrefs._syncing = true;
    if (p.theme === "dark") {
      if (root.getAttribute("data-theme") !== "dark") root.setAttribute("data-theme", "dark");
    } else {
      if (root.hasAttribute("data-theme")) root.removeAttribute("data-theme");
    }
    applyPrefs._syncing = false;
    root.style.setProperty("--edu-font", (p.fontSize || 13.5) + "px");
    syncThemeToggle();
  }

  /* ---------- 明暗主题：一键切换 ---------- */
  function isDarkTheme() { return document.documentElement.getAttribute("data-theme") === "dark"; }
  function syncThemeToggle() {
    var btn = document.getElementById("themeToggle");
    if (!btn) return;
    var dark = isDarkTheme();
    btn.textContent = dark ? "☽" : "☀";
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.setAttribute("title", dark ? "切换到亮色" : "切换到暗色");
  }
  function toggleTheme() {
    var next = isDarkTheme() ? "light" : "dark";
    var p = {};
    try { p = JSON.parse(localStorage.getItem("edu.prefs") || "{}"); } catch (e) { p = {}; }
    p.theme = next;
    try { localStorage.setItem("edu.prefs", JSON.stringify(p)); } catch (e) {}
    // 设置页「外观」读的是 edu.look，这里保持同步，避免两个入口互相覆盖
    try {
      var look = JSON.parse(localStorage.getItem("edu.look") || "{}");
      look.theme = next;
      localStorage.setItem("edu.look", JSON.stringify(look));
    } catch (e) {}
    applyPrefs();
    syncThemeToggle();
  }
  // 用 MutationObserver 兜底：任何其他脚本/工具把 data-theme 改错了，立刻拉回
  (function guardTheme() {
    var root = document.documentElement;
    var obs = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].type === "attributes" && mutations[i].attributeName === "data-theme") {
          // 防抖：不在 applyPrefs 自己执行期间触发
          if (applyPrefs._syncing) return;
          // 检查当前值是否与 localStorage 一致
          var p = {};
          try { p = JSON.parse(localStorage.getItem("edu.prefs") || "{}"); } catch (e) {}
          var want = p.theme === "dark" ? "dark" : null;
          var have = root.getAttribute("data-theme");
          if (want !== have) applyPrefs();
          return;
        }
      }
    });
    obs.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  })();
  // 不再在解析时立即调用——改在 DOMContentLoaded 中统一调度

  window.Edu = window.Edu || {};
  window.Edu.applyPrefs = applyPrefs;
  window.Edu.toggleTheme = toggleTheme;
  Edu.state = {
    live: false,
    selectedCourseId: null,  // 全局唯一课程标识
    draftCourse: null,        // 新建课程的草稿状态 {name, class, totalHours, ...}
    courses: []
  };

  /* ---------- 演示模式自定义课程（localStorage 持久化） ---------- */
  var CUSTOM_COURSES_KEY = "edu.customCourses";

  function readCustomCourses() {
    try {
      var raw = localStorage.getItem(CUSTOM_COURSES_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function writeCustomCourses(list) {
    try { localStorage.setItem(CUSTOM_COURSES_KEY, JSON.stringify(list || [])); } catch (e) {}
  }

  Edu.addCustomCourse = function (course) {
    if (!course || !course.id) return;
    var list = readCustomCourses().filter(function (c) {
      return String(c.id) !== String(course.id);
    });
    list.push(course);
    writeCustomCourses(list);
  };

  /** 从课程列表派生当前选中课程对象 */
  function getSelectedCourse() {
    var list = currentCourses();
    if (!list || !list.length) return null;
    var found = list.filter(function (c) {
      return String(c.id) === String(Edu.state.selectedCourseId);
    })[0];
    if (found) return found;

    // 没有有效选中：收敛到第一门，并同步状态与下拉框，避免"顶栏与页面数据错位"
    var fallback = list[0];
    Edu.state.selectedCourseId = String(fallback.id);
    try { localStorage.setItem("edu.course", String(fallback.id)); } catch (e) {}
    var pick = document.querySelector("#coursePick");
    if (pick) pick.value = String(fallback.id);
    return fallback;
  }
  Edu.getSelectedCourse = getSelectedCourse;
  Edu.isLive = function () { return !!Edu.state.live; };
  Edu.renderTopCourseSummary = renderTopCourseSummary;

  /** 把数字或带单位的字符串清洗成纯数字 */
  function normalizeNumber(input) {
    if (input === null || input === undefined || input === "") return null;
    if (typeof input === "number") return input > 0 ? Math.floor(input) : null;
    var matched = String(input).match(/\d+/);
    if (!matched) return null;
    var v = Number(matched[0]);
    return v > 0 ? Math.floor(v) : null;
  }
  Edu.normalizeNumber = normalizeNumber;

  /** 格式化课程摘要（数字字段 + 单位后缀） */
  function courseSummary(c) {
    if (!c) return null;
    var hours = c.totalHours ? c.totalHours + " 课时" : "未填写课时";
    var progress = (c.currentSession && c.totalSessions)
      ? "第 " + c.currentSession + " 次课 / 共 " + c.totalSessions + " 次课"
      : "进度待完善";
    return {
      courseName: c.name || "未命名课程",
      className: c.class || "未填写班级",
      classSize: c.classSize ? c.classSize + " 人" : "",
      totalHours: hours,
      progress: progress,
      resourceCount: (c.resourceCount || 0) + " 份"
    };
  }
  Edu.courseSummary = courseSummary;

  /** 当前可用课程：内存/接口课程 + 演示模式持久化的自定义课程（按 id 去重） */
  function currentCourses() {
    var base = (Edu.state.courses && Edu.state.courses.length) ? Edu.state.courses : [];
    base = base || [];
    var custom = readCustomCourses();
    if (!custom.length) return base;
    var ids = {};
    base.forEach(function (c) { ids[String(c.id)] = 1; });
    return base.concat(custom.filter(function (c) { return !ids[String(c.id)]; }));
  }
  Edu.currentCourses = currentCourses;

  /** 切换课程（全局） */
  function selectCourse(id) {
    Edu.state.selectedCourseId = id ? String(id) : null;
    try { localStorage.setItem("edu.course", id || ""); } catch (e) {}
    emitCourseChange();
  }
  Edu.selectCourse = selectCourse;

  var _courseListeners = [];
  Edu.onCourseChange = function (fn) { _courseListeners.push(fn); };
  function emitCourseChange() {
    _courseListeners.forEach(function (fn) { try { fn(Edu.state.selectedCourseId); } catch (e) {} });
  }

  /* ---------- 侧栏 ---------- */
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- 项目右键菜单：分享 / 删除（侧栏「课程项目」子项目） ---------- */
  var projMenuEl = null;

  function closeProjMenu() {
    if (projMenuEl && projMenuEl.parentNode) projMenuEl.parentNode.removeChild(projMenuEl);
    projMenuEl = null;
  }

  function copyText(text, cb) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { cb(true); }, function () { cb(fallbackCopy(text)); });
      return;
    }
    cb(fallbackCopy(text));
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  }

  function confirmDialog(title, text, okLabel, onOk) {
    var mask = document.createElement("div");
    mask.className = "modal-mask on";
    mask.innerHTML =
      '<div class="modal" style="max-width:440px">' +
        '<div class="modal-h"><b>' + escHtml(title) + '</b><button class="x" type="button" data-cb-cancel>×</button></div>' +
        '<div class="modal-b"><p class="sub" style="white-space:pre-line;line-height:1.7">' + escHtml(text) + '</p></div>' +
        '<div class="modal-f">' +
          '<button class="btn" type="button" data-cb-cancel>取消</button>' +
          '<button class="btn primary" type="button" data-cb-ok style="background:#9C3A34;border-color:#9C3A34">' +
            escHtml(okLabel) + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    function close() {
      if (mask.parentNode) mask.parentNode.removeChild(mask);
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    mask.addEventListener("click", function (e) {
      if (e.target === mask || e.target.closest("[data-cb-cancel]")) { close(); return; }
      if (e.target.closest("[data-cb-ok]")) { close(); onOk(); }
    });
    document.addEventListener("keydown", onKey);
  }

  function shareProjectInfo(proj) {
    var url = location.origin + location.pathname.replace(/[^/]*$/, "") + "courses.html";
    var text = "课程项目：" + proj.name + "\n教学轮次：第 " + (proj.round || 1) + " 轮\n查看地址：" + url;
    copyText(text, function (ok) {
      toast(ok ? "分享内容已复制到剪贴板" : "分享内容：" + text.replace(/\n/g, " · "));
    });
  }

  function deleteProjectById(proj, onDone) {
    if (!Edu.isLive() || !window.EduAPI || !EduAPI.courses || typeof EduAPI.courses.remove !== "function") {
      toast("未连接本地接口，暂不能删除项目");
      return;
    }
    confirmDialog("删除项目",
      "确认删除项目「" + proj.name + "」？\n\n删除后该项目下的资料与任务会保留在课程库中（不再归属此项目），其下的历史轮次会转为独立项目。",
      "确认删除",
      function () {
        EduAPI.courses.remove(proj.id).then(function () {
          return EduAPI.courses.list();
        }).then(function (list) {
          Edu.state.courses = list || [];
          if (String(Edu.state.selectedCourseId) === String(proj.id)) {
            Edu.selectCourse(list && list.length ? list[0].id : null);
          }
          var pick = document.querySelector("#coursePick");
          if (pick) {
            var visible = currentCourses();
            pick.innerHTML = visible.length ? visible.map(function (c) {
              return '<option value="' + c.id + '">' + escHtml(c.name) +
                (c.class || c.class_name ? " · " + escHtml(c.class || c.class_name) : "") + '</option>';
            }).join("") : '<option value="">（暂无课程）</option>';
            if (Edu.state.selectedCourseId) pick.value = String(Edu.state.selectedCourseId);
          }
          renderTopCourseSummary();
          toast("已删除「" + proj.name + "」");
          if (typeof onDone === "function") onDone();
        }).catch(function (err) {
          toast("删除失败：" + (err && err.message ? err.message : err));
        });
      });
  }

  function openProjMenu(x, y, proj, onDone) {
    closeProjMenu();
    var m = document.createElement("div");
    m.className = "ctx-menu";
    m.innerHTML =
      '<div class="ctx-h">' + escHtml(proj.name || "未命名项目") + '</div>' +
      '<button type="button" class="ctx-item" data-ctx="share">分享项目</button>' +
      '<button type="button" class="ctx-item danger" data-ctx="del">删除项目</button>';
    m.style.left = Math.max(8, Math.min(x, window.innerWidth - 190)) + "px";
    m.style.top = Math.max(8, Math.min(y, window.innerHeight - 130)) + "px";
    document.body.appendChild(m);
    projMenuEl = m;
    m.addEventListener("click", function (e) {
      var b = e.target.closest("[data-ctx]");
      if (!b) return;
      var act = b.getAttribute("data-ctx");
      closeProjMenu();
      if (act === "share") shareProjectInfo(proj);
      else deleteProjectById(proj, onDone);
    });
  }

  document.addEventListener("click", closeProjMenu);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeProjMenu(); });
  window.addEventListener("resize", closeProjMenu);
  window.addEventListener("scroll", closeProjMenu, true);

  /* 侧栏「课程项目」：可展开/收起，展开后列出当前课程的项目轮次 */
  var SIDE_PROJ_KEY = "edu.sideProjects";

  function initSideProjects(sec) {
    var head = sec.querySelector("[data-proj-toggle]");
    var body = sec.querySelector(".nav-sec-b");
    var countEl = sec.querySelector("[data-proj-count]");
    if (!head || !body) return;

    function isActive(c) { return c && c.status !== "archived" && !c.archived; }

    // 初始视觉判定：有没有活跃课程 → 决定是否显示可收缩
    function applyVisual(list) {
      var hasActive = (list || []).some(isActive);
      sec.classList.toggle("no-caret", !hasActive);
      if (!hasActive) {
        body.innerHTML = "";
        body.style.display = "none";
        head.removeAttribute("aria-expanded");
        head.style.cursor = "pointer";
        // 把 ▾ caret 去掉
        var caret = head.querySelector(".caret");
        if (caret) caret.style.display = "none";
        return false;
      }
      body.style.display = "";
      var caret = head.querySelector(".caret");
      if (caret) caret.style.display = "";
      return true;
    }

    // 先尝试用缓存判定；没缓存就 fetch 一次
    var cached = (Edu.state && Edu.state.courses) || [];
    var visualReady = cached.length > 0 ? applyVisual(cached) : false;
    if (!visualReady && window.EduAPI && EduAPI.courses && typeof EduAPI.courses.list === "function") {
      EduAPI.courses.list(true).then(function (list) {
        Edu.state = Edu.state || {}; Edu.state.courses = list || [];
        applyVisual(list);
      }).catch(function () {});
    }

    // 监听课程变化：有/无活跃课程切换时更新外观
    Edu.onCourseChange(function () {
      var cur = (Edu.state && Edu.state.courses) || [];
      if (cur.length) applyVisual(cur);
      else if (window.EduAPI && EduAPI.courses) {
        EduAPI.courses.list(true).then(function (list) {
          Edu.state.courses = list || []; applyVisual(list);
        }).catch(function () {});
      }
    });

    function load() {
      var c = getSelectedCourse();
      if (!c) {
        if (countEl) countEl.hidden = true;
        body.innerHTML = '<div class="nav-sec-empty">还没有课程项目，<a href="courses.html">新建一个</a></div>';
        return;
      }
      if (!Edu.isLive() || !window.EduAPI || !EduAPI.courses || typeof EduAPI.courses.rounds !== "function") {
        if (countEl) countEl.hidden = true;
        body.innerHTML = '<div class="nav-sec-empty">未连接本地接口，暂无法读取项目</div>' +
          '<a class="nav-sec-all" href="courses.html">查看课程项目 ›</a>';
        return;
      }
      EduAPI.courses.rounds(c.id).then(function (res) {
        var rounds = (res && res.rounds) || [];
        if (countEl) { countEl.textContent = rounds.length; countEl.hidden = !rounds.length; }
        var html = rounds.map(function (r) {
          var on = String(r.id) === String(c.id);
          var prog = (r.current_session && r.total_sessions)
            ? "第 " + r.current_session + "/" + r.total_sessions + " 次课"
            : "进度待完善";
          return '<button type="button" class="nav-proj' + (on ? " on" : "") + '" data-proj-id="' + escHtml(r.id) +
              '" data-proj-name="' + escHtml(r.name || "未命名项目") + '" data-proj-round="' + (r.round || 1) + '">' +
              '<span class="p-name">' + escHtml(r.name || "未命名课程") + '</span>' +
              '<span class="p-meta">第 ' + (r.round || 1) + ' 轮 · ' + prog +
                (r.status === "archived" ? " · 已归档" : "") + '</span>' +
            '</button>';
        }).join("");
        body.innerHTML = (html || '<div class="nav-sec-empty">还没有可展示的项目</div>') +
          '<a class="nav-sec-all" href="courses.html">全部课程项目 ›</a>';
      }).catch(function () {
        body.innerHTML = '<div class="nav-sec-empty">课程项目加载失败</div>' +
          '<a class="nav-sec-all" href="courses.html">查看课程项目 ›</a>';
      });
    }

    function setOpen(on, persist) {
      sec.classList.toggle("open", on);
      head.setAttribute("aria-expanded", on ? "true" : "false");
      if (persist !== false) { try { localStorage.setItem(SIDE_PROJ_KEY, on ? "1" : "0"); } catch (e) {} }
      if (on) load();
    }

    head.addEventListener("click", function () {
      // 课程项目入口：直接打开课程项目页面；已在该页时才展开/收起项目列表
      var onCourses = (document.body && document.body.getAttribute("data-page") === "courses");
      if (!onCourses) {
        location.href = "courses.html";
        return;
      }
      setOpen(!sec.classList.contains("open"));
    });

    body.addEventListener("click", function (e) {
      var b = e.target.closest("[data-proj-id]");
      if (!b) return;
      var id = b.getAttribute("data-proj-id");
      Edu.selectCourse(id);
      var onCourses = (document.body && document.body.getAttribute("data-page") === "courses");
      if (onCourses) {
        var name = b.querySelector(".p-name");
        toast("已切换到「" + (name ? name.textContent : "") + "」");
      } else {
        location.href = "courses.html";
      }
    });

    // 右键：分享 / 删除该项目
    body.addEventListener("contextmenu", function (e) {
      var b = e.target.closest("[data-proj-id]");
      if (!b) return;
      e.preventDefault();
      openProjMenu(e.clientX, e.clientY, {
        id: b.getAttribute("data-proj-id"),
        name: b.getAttribute("data-proj-name") || "",
        round: b.getAttribute("data-proj-round") || ""
      }, load);
    });

    Edu.onCourseChange(function () {
      if (sec.classList.contains("open")) load();
    });

    var saved;
    try { saved = localStorage.getItem(SIDE_PROJ_KEY); } catch (e) {}
    setOpen(saved !== "0", false);
  }

  /* ---------- 空课程引导弹窗 ---------- */
  function showEmptyCoursesModal() {
    var mask = document.getElementById("modalEmptyCourses");
    if (!mask) {
      mask = document.createElement("div");
      mask.className = "modal-mask";
      mask.id = "modalEmptyCourses";
      mask.innerHTML =
        '<div class="modal" style="max-width:460px">' +
        '<div class="modal-h"><b>还没有课程项目</b><button class="x" type="button" data-close-modal>×</button></div>' +
        '<div class="modal-b">' +
        '<div class="state is-warn" style="margin-bottom:12px">' +
        '<div class="state-ic">+</div>' +
        '<div><b>先建一门课程</b><span>所有教学环节（备课、实训、评审）都要挂在一门课程项目之下。</span></div>' +
        '</div>' +
        '<p class="sub">现在点击侧栏上方的 <b style="color:var(--acc)">「＋ 新建教学任务」</b> 按钮，在弹出的表单中填写课程名称、班级等信息即可开始。</p>' +
        '</div>' +
        '<div class="modal-f">' +
        '<button class="btn" type="button" data-close-modal>稍后再说</button>' +
        '<button class="btn primary" type="button" id="ecGoNewTask">去新建教学任务</button>' +
        '</div>' +
        '</div>';
      document.body.appendChild(mask);
    }
    mask.classList.add("on");
    var go = mask.querySelector("#ecGoNewTask");
    if (go) {
      go.onclick = function () {
        mask.classList.remove("on");
        var m = document.getElementById("modalNewCourse");
        if (!m) { initModal(); m = document.getElementById("modalNewCourse"); }
        if (m) m.classList.add("on");
      };
    }
  }


  function refreshSideFoot(nu) {
    var f = document.querySelector(".side-foot");
    if (!f || !nu) return;
    var label = nu.display_name || nu.username || "";
    var av = f.querySelector(".avatar");
    if (av) av.innerHTML = nu.avatar ? '<img src="' + nu.avatar + '" alt="">' : escHtml((label || "师").slice(-2));
    var b = f.querySelector("b");
    if (b && label) b.textContent = label;
  }
  // /auth/me 返回后刷新侧栏用户信息（头像、名字）
  document.addEventListener("edu-auth-ready", function (e) { refreshSideFoot(e.detail); });

  /* ---------- AI 助手浮动按钮（可缩放 = 点击展开小面板） ---------- */
  function initAssistantFab() {
    // assistant.html 本身不需要 FAB（它就是 AI 助手页面）
    if ((document.body && document.body.getAttribute("data-page") === "assistant")) return;
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "assist-fab"; btn.id = "assistFab";
    btn.title = "AI 助手"; btn.setAttribute("aria-label", "AI 助手");
    btn.innerHTML =
      '<span class="fab-ic">' + ic("spark", 22) + '</span>' +
      '<span class="fab-panel">' +
        '<div class="fab-h"><b>AI 助手</b><button class="x" type="button" data-fab-close>×</button></div>' +
        '<div class="fab-body">' +
          '<div class="fab-sub">围绕当前课程资料快速提问</div>' +
          '<textarea id="fabInput" placeholder="输入问题，Enter 发送" rows="2"></textarea>' +
          '<div class="fab-actions">' +
            '<button class="btn sm" type="button" data-fab-send>发送</button>' +
            '<a class="btn sm ghost" href="assistant.html">打开完整助手页面 ›</a>' +
          '</div>' +
          '<div class="fab-prompts">' +
            '<button class="fab-prompt" type="button" data-fab-prompt="生成一组练习题" data-prompt="生成一组练习题">生成练习</button>' +
            '<button class="fab-prompt" type="button" data-fab-prompt="压缩教案" data-prompt="把当前教案压缩成 45 分钟版本">压缩教案</button>' +
            '<button class="fab-prompt" type="button" data-fab-prompt="总结学情" data-prompt="总结近 30 天学情中最需要干预的三个问题">总结学情</button>' +
          '</div>' +
        '</div>' +
      '</span>';
    document.body.appendChild(btn);

    // 液态玻璃：注入 SVG 折射滤镜（供 .fab-panel::before 的 backdrop-filter 引用）
    if (!document.getElementById("lgLensDefs")) {
      var defs = document.createElement("div");
      defs.id = "lgLensDefs";
      defs.setAttribute("aria-hidden", "true");
      defs.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
      defs.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0">' +
          '<filter id="lgLens" x="-15%" y="-15%" width="130%" height="130%" color-interpolation-filters="sRGB">' +
            '<feTurbulence type="fractalNoise" baseFrequency="0.004 0.009" numOctaves="2" seed="7" result="noise"/>' +
            '<feGaussianBlur in="noise" stdDeviation="1.6" result="soft"/>' +
            '<feDisplacementMap in="SourceGraphic" in2="soft" scale="28" xChannelSelector="R" yChannelSelector="G"/>' +
          '</filter>' +
        '</svg>';
      document.body.appendChild(defs);
    }

    var panel = btn.querySelector(".fab-panel");
    var ta = btn.querySelector("#fabInput");
    function hasDraft() { return !!(ta && ta.value && ta.value.trim()); }
    var leaveTimer = null, lastX = null, lastY = null, KEEP_R = 100;
    function stopWatch() { if (leaveTimer) { clearInterval(leaveTimer); leaveTimer = null; } }
    function distToBtn(x, y) {
      var r = btn.getBoundingClientRect();
      var dx = Math.max(r.left - x, 0, x - r.right);
      var dy = Math.max(r.top - y, 0, y - r.bottom);
      return Math.sqrt(dx * dx + dy * dy);
    }
    function shouldKeep() {
      if (hasDraft()) return true;                 // 输入过文字 → 一直保留
      if (lastX === null) return true;             // 没有鼠标信息（键盘操作）→ 保留
      if (panel.matches(":hover")) return true;    // 光标在卡片上
      if (distToBtn(lastX, lastY) <= KEEP_R) return true; // 光标在按钮周围 100px 内
      return false;
    }
    function startWatch() {
      stopWatch();
      leaveTimer = setInterval(function () {
        if (!btn.classList.contains("open")) { stopWatch(); return; }
        if (shouldKeep()) return;
        close();
      }, 200);
    }
    function open() { btn.classList.add("open"); startWatch(); setTimeout(function () { if (ta) ta.focus(); }, 50); }
    function close() { btn.classList.remove("open"); stopWatch(); }
    // 光标在按钮 100px 范围内或卡片上时保持；超出且无内容则收起
    document.addEventListener("pointermove", function (e) {
      lastX = e.clientX; lastY = e.clientY;
      if (!btn.classList.contains("open") || hasDraft()) return;
      if (panel.contains(e.target)) return;
      if (distToBtn(e.clientX, e.clientY) <= KEEP_R) return;
      close();
    }, { passive: true });

    btn.addEventListener("click", function (e) {
      if (e.target.closest("[data-fab-close]")) { close(); return; }
      if (e.target.closest(".fab-panel")) return; // 点面板内部不触发 toggle
      // 点按钮本体 → toggle
      if (e.target.closest(".fab-ic")) {
        if (btn.classList.contains("open")) close(); else open();
      }
    });

    // 发送按钮
    btn.addEventListener("click", function (e) {
      var send = e.target.closest("[data-fab-send]");
      if (!send) return;
      var text = (ta && ta.value || "").trim();
      if (!text) return;
      // 跳到 assistant.html ?q=xxx
      location.href = "assistant.html?q=" + encodeURIComponent(text);
    });
    // 快捷 prompt
    btn.addEventListener("click", function (e) {
      var p = e.target.closest(".fab-prompt");
      if (!p) return;
      var text = p.getAttribute("data-prompt") || p.textContent || "";
      location.href = "assistant.html?q=" + encodeURIComponent(text);
    });
    // textarea Enter 发送
    if (ta) ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        var text = ta.value.trim();
        if (!text) return;
        location.href = "assistant.html?q=" + encodeURIComponent(text);
      }
    });
    // ESC / 点外部关闭
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    document.addEventListener("click", function (e) {
      if (!btn.classList.contains("open")) return;
      if (btn.contains(e.target)) return;
      close();
    });
  }

  function buildSidebar() {
    var aside = document.querySelector(".sidebar");
    if (!aside) return;
    // 暴露给 modal 保存成功后触发侧栏刷新
    if (window.Edu) Edu.renderSidebar = buildSidebar;
    var groups = isStudent ? STUDENT_GROUPS : GROUPS;
    var hash = (location.hash || "#home").slice(1);
    var nav = "";
    groups.forEach(function (g) {
      nav += '<div class="nav-label">' + g.label + "</div>";
      g.items.forEach(function (it) {
        if (!isStudent && it.page === "courses") {
          nav += '<div class="nav-sec" id="navProjects">' +
              '<button class="nav-sec-h' + (page === "courses" ? " active" : "") + '" type="button" data-proj-toggle data-nav-courses aria-expanded="false">' +
                ic(it.icon) + '<span class="lbl">' + it.text + '</span>' +
                '<span class="cnt" data-proj-count hidden></span><span class="caret">▾</span>' +
              '</button>' +
              '<div class="nav-sec-b"><div class="nav-sec-empty">展开后加载项目…</div></div>' +
            '</div>';
          return;
        }
        var on = it.page === page;
        if (isStudent && page === "student" && it.href.indexOf("#") > -1) {
          on = it.href.split("#")[1] === hash;
        }
        nav += '<a href="' + it.href + '" class="' + (on ? "active" : "") + '">' + ic(it.icon) + "<span>" + it.text + "</span></a>";
      });
    });
    var u = (isStudent ? window.EDU.student : window.EDU.teacher) || {};
    var au = (window.EduAuth && window.EduAuth.user) || null;
    if (au) {
      var label = au.display_name || au.username || "";
      u = {
        initials: (label || (isStudent ? "生" : "师")).slice(-2),
        name: label || (isStudent ? "学生" : "教师"),
        class: isStudent
          ? [au.college, au.major, au.class_name].filter(Boolean).join(" · ") || "未绑定学籍"
          : "教师账号"
      };
    }
    var newBtn = isStudent
      ? '<button type="button" data-go="student.html#tasks">' + ic("plus", 14) + " 我的学习任务</button>"
      : '<button type="button" data-new-task>' + ic("plus", 14) + " 新建教学任务</button>";
    var homeHref = isStudent ? "student.html" : "index.html";
    var homeBtnText = ic("home", 14) + " 首页";
    var homeBtn = isStudent
      ? '<button type="button" data-go="' + homeHref + '">' + homeBtnText + '</button>'
      : '<button type="button" data-go="' + homeHref + '">' + homeBtnText + '</button>';
    aside.innerHTML =
      '<a class="brand" href="' + homeHref + '">' +
        '<div class="mark"><img src="assets/img/logo-z.png?v=1795865037" alt="致壹" width="28" height="28"></div>' +
        '<div><div class="name">' + window.EDU.brand.name + '</div><div class="sub">' + window.EDU.brand.sub + "</div></div>" +
      "</a>" +
      '<div class="side-new">' + homeBtn + newBtn + "</div>" +
      '<nav class="nav">' + nav + "</nav>" +
      '<button class="side-foot" type="button" title="个人资料与设置">' +
        '<div class="avatar">' + ((au && au.avatar) ? '<img src="' + au.avatar + '" alt="">' : escHtml(u.initials || "")) + "</div>" +
        '<div class="sf-meta"><b>' + escHtml(u.name || (isStudent ? "学生" : "教师")) + "</b><span>" + escHtml(isStudent ? (u.class || "") : "教师 · 单租户") + "</span></div>" +
        '<span class="sf-hint">' + ic("user", 14) + "</span>" +
      "</button>";

    var projSec = aside.querySelector("#navProjects");
    if (projSec) initSideProjects(projSec);

    // 「新建教学任务」按钮（侧栏 / 页内 data-open-new-course）→ 任意页面都弹新建课程项目弹窗
    document.addEventListener("click", function (e) {
      if (!e.target.closest("[data-new-task], [data-open-new-course]")) return;
      e.preventDefault();
      var mask = document.getElementById("modalNewCourse");
      if (!mask) { initModal(); mask = document.getElementById("modalNewCourse"); }
      if (mask) mask.classList.add("on");
    });
    // 侧栏底部头像卡 → 弹出菜单（上方弹，不是 modal 遮罩）
    var foot = aside.querySelector(".side-foot");
    if (foot) {
      foot.style.cursor = "pointer";
      foot.addEventListener("click", function (e) {
        e.stopPropagation();
        toggleSidePopover(foot, u, isStudent);
      });
    }
    // 侧栏"个人资料"菜单项点击后的弹 modal：走侧栏头像卡事件委托统一处理
    document.addEventListener("click", function (e) {
      var item = e.target.closest("[data-side-item]");
      if (!item) return;
      var act = item.getAttribute("data-side-item");
      closeSidePopover();
      if (act === "profile") { openProfileModal(); }
      else if (act === "settings") {
        if (isStudent) location.href = "student.html#settings";
        else location.href = "settings.html";
      }
    });
    // 点侧栏头像卡之外、popover 之外 → 关掉 popover
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".side-foot") && !e.target.closest(".side-popover")) {
        closeSidePopover();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSidePopover();
    });
  }

  /* ---------- 侧栏头像卡弹出菜单 ---------- */
  var _sidePopoverEl = null;
  function toggleSidePopover(trigger, u, isStudent) {
    if (_sidePopoverEl && _sidePopoverEl.classList.contains("on")) { closeSidePopover(); return; }
    closeSidePopover();
    // 从 auth.user 取完整学院/专业/班级（buildSidebar 传给的 u 是简化对象）
    var fullUser = (window.EduAuth && window.EduAuth.user) || {};
    var classLine = isStudent
      ? ([fullUser.college, fullUser.major, fullUser.class_name].filter(Boolean).join(" · ") || "未绑定学籍")
      : "教师 · 单租户";
    var pop = document.createElement("div");
    pop.className = "side-popover";
    var items;
    if (isStudent) {
      items =
        '<button class="sp-item" type="button" data-side-item="profile"><span class="sp-ic">👤</span><span>个人资料<span class="sp-sub">修改姓名 / 学院 / 专业 / 班级</span></span></button>' +
        '<button class="sp-item" type="button" data-side-item="settings"><span class="sp-ic">⚙</span><span>设置<span class="sp-sub">外观 / 密码 / 账号状态</span></span></button>';
    } else {
      items =
        '<button class="sp-item" type="button" data-side-item="profile"><span class="sp-ic">👤</span><span>教师<span class="sp-sub">修改名字 / 头像</span></span></button>' +
        '<button class="sp-item" type="button" data-side-item="settings"><span class="sp-ic">⚙</span><span>设置<span class="sp-sub">外观 / 密码 / 账号状态</span></span></button>';
    }
    pop.innerHTML =
      '<div class="sp-h"><b>' + (fullUser.display_name || fullUser.username || u.name || "本地用户") + '</b><span>' + classLine + '</span></div>' + items;
    document.body.appendChild(pop);
    _sidePopoverEl = pop;
    // 定位：紧贴头像卡上方，用 fixed 定位
    requestAnimationFrame(function () {
      var r = trigger.getBoundingClientRect();
      var ph = pop.offsetHeight;
      var pw = pop.offsetWidth;
      var top = r.top - ph - 8;
      var left = Math.min(r.left + r.width - pw, r.right - pw);
      if (top < 8) top = r.bottom + 8; // 极端窄屏下方空间不足 → 反向
      pop.style.top = top + "px";
      pop.style.left = left + "px";
      pop.classList.add("on");
    });
  }
  function closeSidePopover() {
    if (!_sidePopoverEl) return;
    _sidePopoverEl.classList.remove("on");
    var el = _sidePopoverEl;
    _sidePopoverEl = null;
    setTimeout(function () { try { el.remove(); } catch (e) {} }, 160);
  }

  /* ---------- 顶栏 ---------- */
  function renderTopCourseSummary() {
    var summary = document.querySelector(".course-summary");
    if (!summary) return;
    var sel = getSelectedCourse();
    var draft = Edu.state.draftCourse;
    var label, detail;
    if (sel) {
      var cs = courseSummary(sel);
      label = cs.courseName;
      detail = cs.totalHours + " · " + cs.progress;
      summary.classList.remove("empty", "draft");
      summary.classList.add("filled");
    } else if (draft && draft.name && draft.name.trim()) {
      label = "新课程草稿：" + draft.name.trim();
      detail = (draft.totalHours ? draft.totalHours + " 课时" : "课时待填")
        + " · " + (draft.class || "班级待填");
      summary.classList.remove("filled", "empty");
      summary.classList.add("draft");
    } else {
      label = "请选择或创建课程";
      detail = "";
      summary.classList.remove("filled", "draft");
      summary.classList.add("empty");
    }
    summary.innerHTML =
      '<div class="cs-label">' + label + '</div>' +
      (detail ? '<div class="cs-detail">' + detail + '</div>' : '');
  }

  function accountLabel() {
    var u = (window.EduAuth && window.EduAuth.user) || null;
    if (!u) return "未登录";
    var name = u.display_name || u.username || "";
    return name + (u.role === "student" ? " · 学生" : " · 教师");
  }

  function buildTopbar() {
    var top = document.querySelector(".topbar");
    if (!top) return;
    var options = currentCourses().map(function (c) {
      return '<option value="' + c.id + '">' + c.name + " · " + (c.class || "") + "</option>";
    }).join("") || '<option value="">（暂无课程）</option>';
    var mobile = '<select class="nav-mobile" aria-label="页面导航">' +
      Object.keys(TITLES).map(function (k) {
        return '<option value="' + k + '.html"' + (k === page ? " selected" : "") + ">" + TITLES[k] + "</option>";
      }).join("") + "</select>";

    top.innerHTML =
      mobile +
      '<div class="crumb"><span>致壹</span><span>/</span><b>' + (TITLES[page] || "首页") + "</b></div>" +
      '<div class="top-right">' +
        '<button class="btn sm ghost theme-toggle" type="button" id="themeToggle" title="切换亮色/暗色" aria-label="切换亮色/暗色">☾</button>' +
        '<label class="course-pick"><span>课程</span><select id="coursePick">' + options + '</select></label>' +
        (isStudent ? "" : '<a class="btn sm" href="courses.html#newCourse">＋ 创建课程</a>') +
        '<span class="mini" id="accountTag" style="white-space:nowrap">' + escHtml(accountLabel()) + "</span>" +
        '<button class="btn sm ghost" type="button" data-acct="password">修改密码</button>' +
        '<button class="btn sm ghost" type="button" data-acct="logout">退出登录</button>' +
      "</div>";

    top.addEventListener("change", function (e) {
      if (e.target.id === "coursePick") {
        selectCourse(e.target.value || null);
        var name = e.target.options[e.target.selectedIndex] ? e.target.options[e.target.selectedIndex].text.split(" · ")[0] : "";
        if (name) toast("已切换到「" + name + "」");
        renderTopCourseSummary();
      }
      if (e.target.classList.contains("nav-mobile")) location.href = e.target.value;
    });
    top.addEventListener("click", function (e) {
      var b = e.target.closest("[data-go]");
      if (b) location.href = b.getAttribute("data-go");
      var acct = e.target.closest("[data-acct]");
      if (acct && window.EduAuth) {
        var act = acct.getAttribute("data-acct");
        if (act === "logout") { EduAuth.logout(); return; }
        if (act === "password") { EduAuth.openPassword(); return; }
      }
      // 点击课程摘要 → 展开下拉
      var cs = e.target.closest(".course-summary");
      if (cs) {
        var pick = document.querySelector("#coursePick");
        if (pick) pick.focus();
      }
      // 顶栏明暗主题一键切换：立即生效并写入 edu.prefs（同时镜像到设置页用的 edu.look）
      if (e.target.closest("#themeToggle")) { toggleTheme(); }
    });

    syncThemeToggle();

    var pick = top.querySelector("#coursePick");
    try {
      var saved = localStorage.getItem("edu.course");
      var cur = currentCourses();
      if (saved && cur.some(function (c) { return String(c.id) === String(saved); })) {
        pick.value = saved; Edu.state.selectedCourseId = saved;
      } else if (cur.length) {
        Edu.state.selectedCourseId = cur[0].id;
        pick.value = cur[0].id;
      }
    } catch (err) {}
    renderTopCourseSummary();
  }

  /* ---------- 标签页 ---------- */
  function initTabs() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".tabs button");
      if (!btn) return;
      var box = btn.closest(".tabs");
      var scope = box.parentElement;
      box.querySelectorAll("button").forEach(function (b) { b.classList.remove("on"); });
      btn.classList.add("on");
      var name = btn.getAttribute("data-tab");
      scope.querySelectorAll(":scope > .tabpane").forEach(function (p) {
        p.classList.toggle("on", p.getAttribute("data-pane") === name);
      });
      if (box.hasAttribute("data-hash") && location.hash !== "#" + name) location.hash = name;
    });
  }

  /* ---------- Toast ---------- */
  var toastTimer;
  function toast(msg) {
    var el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    requestAnimationFrame(function () { el.classList.add("on"); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("on"); }, 2400);
  }
  window.toast = toast;
  Edu.toast = toast;

  /* ---------- data-go 全局跳转 ---------- */
  function initGo() {
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-go]");
      if (b) {
        e.preventDefault();
        location.href = b.getAttribute("data-go");
      }
    });
  }

  /* ---------- 弹窗 ---------- */
  function initModal() {
    /* 弹窗 1：新建课程项目（任意页面可弹） */
    var mc = document.querySelector("#modalNewCourse");
    if (!mc) {
      mc = document.createElement("div");
      mc.className = "modal-mask";
      mc.id = "modalNewCourse";
      mc.innerHTML =
        '<div class="modal" style="max-width:760px">' +
        '<div class="modal-h"><b>新建课程项目</b><button class="x" type="button" data-close-modal>×</button></div>' +
        '<div class="modal-b">' +
        '<form id="newCourseForm" novalidate method="post" data-sim="#courseCreated">' +
        '<h3>课程基本信息</h3>' +
        '<div class="grid g3">' +
        '<div class="field"><label>课程名称 *</label><input type="text" id="nf_name" name="courseName" required placeholder="例如：消费者行为分析"></div>' +
        '<div class="field"><label>授课班级或对象 *</label><input type="text" id="nf_class" name="className" required placeholder="例如：市场营销 24-1"></div>' +
        '<div class="field unit-field"><label>课时 *</label><input type="number" id="nf_hours" name="totalHours" min="1" required placeholder="请输入数字"><span class="unit-suffix">课时</span></div>' +
        '</div>' +
        '<div class="grid g3">' +
        '<div class="field unit-field"><label>班级人数</label><input type="number" id="nf_size" name="classSize" min="1" placeholder=""><span class="unit-suffix">人</span></div>' +
        '<div class="field"><label>教材 / 课程标准版本</label><input type="text" id="nf_textbook" name="textbook" placeholder="例如：第 5 版"></div>' +
        '<div class="field unit-field"><label>课程总课次</label><input type="number" id="nf_totalSessions" name="totalSessions" min="1" placeholder=""><span class="unit-suffix">次课</span></div>' +
        '</div>' +
        '<div class="grid g2">' +
        '<div class="field"><label>课程描述 / 备注（可选）</label><input type="text" id="nf_desc" name="desc" placeholder="一句话说明课程定位或授课时间、场地"></div>' +
        '</div>' +
        '<h3 style="margin-top:6px">教学目标</h3>' +
        '<div class="field"><label>课程学习目标 *</label><textarea id="nf_objectives" name="objectives" required placeholder="知识目标、能力目标、素养目标，可分行填写"></textarea></div>' +
        '<div class="grid g2">' +
        '<div class="field"><label>重点</label><input type="text" id="nf_key" name="key" placeholder="例如：消费者决策模型"></div>' +
        '<div class="field"><label>难点</label><input type="text" id="nf_diff" name="diff" placeholder="例如：情境因素对决策的干扰"></div>' +
        '</div>' +
        '<div class="form-actions">' +
        '<button class="btn primary" type="submit">创建课程项目</button>' +
        '<button class="btn" type="reset" id="nfReset">取消</button>' +
        '<span class="mini">创建后会自动成为当前课程。</span>' +
        '</div>' +
        '</form>' +
        '<div id="courseCreated" class="rule" hidden style="margin-top:12px"></div>' +
        '</div>' +
        '</div>';
      document.body.appendChild(mc);
    }

    /* 弹窗 2：新建教学任务入口选择器（备课/实训/答疑/评审） */
    var mask2 = document.querySelector("#modalNewTask");
    if (!mask2) {
      mask2 = document.createElement("div");
      mask2.className = "modal-mask";
      mask2.id = "modalNewTask";
      mask2.innerHTML =
        '<div class="modal">' +
        '<div class="modal-h"><b>新建教学任务</b><button class="x" type="button" data-close-modal>×</button></div>' +
        '<div class="modal-b">' +
        '<p class="sub" style="margin-bottom:12px">选择要开始的教学环节，内容会自动关联到当前课程。</p>' +
        '<div class="quick">' +
        '<a href="lesson.html"><span class="qi">✦</span><span><b>一键备课</b><span>生成教案、课件与练习</span></span></a>' +
        '<a href="training.html"><span class="qi">◈</span><span><b>创建实训</b><span>生成真实工作场景任务包</span></span></a>' +
        '<a href="tutor.html"><span class="qi">◌</span><span><b>学生答疑</b><span>记录或回答学生问题</span></span></a>' +
        '<a href="review.html"><span class="qi">✓</span><span><b>作业评审</b><span>上传提交并开始评审</span></span></a>' +
        '</div></div>' +
        '<div class="modal-f"><button class="btn" type="button" data-close-modal>关闭</button></div>' +
        '</div>';
      document.body.appendChild(mask2);
    }

    /* 统一关闭逻辑（新建课程 / 新建任务 / 个人资料） */
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-close-modal]")) {
        e.target.closest(".modal-mask").classList.remove("on");
      }
    });
    document.querySelectorAll(".modal-mask").forEach(function (m) {
      m.addEventListener("click", function (e) { if (e.target === m) m.classList.remove("on"); });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-mask.on").forEach(function (m) { m.classList.remove("on"); });
      }
    });

    /* 关闭 modal（新建课程 / 新建任务）；个人资料 modal 由 openProfileModal 动态创建 */
  }

  /* ---------- 卡片弹窗化：.card[data-panel] → 独立按钮 + 独立弹窗 ----------
     约定：给卡片加 data-panel="标题" 即可把它挪进自己的弹窗，并在页面上留一个按钮。
     可选：data-panel-width="860px"、data-panel-ic="▤"、data-panel-auto（卡片由隐藏变可见时自动弹出） */
  function initPanels() {
    var cards = [].slice.call(document.querySelectorAll(".content .card[data-panel]"));
    if (!cards.length) return;
    var byCardId = {};
    var owners = [];
    var seq = 0;

    function toolbarFor(owner, inPane) {
      for (var i = 0; i < owners.length; i++) {
        if (owners[i].owner === owner) return owners[i].el;
      }
      var tb = document.createElement("div");
      tb.className = "panel-tools";
      if (inPane) {
        owner.insertBefore(tb, owner.firstChild);
      } else {
        var head = owner.querySelector(":scope > .page-head") || owner.querySelector(":scope > .hero");
        if (head) {
          if (head.nextSibling) owner.insertBefore(tb, head.nextSibling);
          else owner.appendChild(tb);
        } else {
          owner.insertBefore(tb, owner.firstChild);
        }
      }
      owners.push({ owner: owner, el: tb });
      return tb;
    }

    cards.forEach(function (card) {
      seq++;
      var title = (card.getAttribute("data-panel") || "").trim() ||
        ((card.querySelector(".card-h h2, .card-h h3") || {}).textContent || "").trim() || "详情";
      var width = card.getAttribute("data-panel-width") || "760px";
      var icon = card.getAttribute("data-panel-ic") || "▤";
      var pane = card.closest(".tabpane");
      var owner = pane || card.closest(".content") || document.body;

      /* 每张卡片一个独立弹窗：标题、内容、尺寸各自独立 */
      var mask = document.createElement("div");
      mask.className = "modal-mask panel-modal";
      mask.id = "panelModal" + seq;
      mask.innerHTML =
        '<div class="modal" style="max-width:' + width + '">' +
          '<div class="modal-h"><b>' + escHtml(title) + '</b>' +
            '<button class="x" type="button" data-close-modal aria-label="关闭">×</button></div>' +
          '<div class="modal-b panel-body"></div>' +
          '<div class="modal-f"><button class="btn" type="button" data-close-modal>关闭</button></div>' +
        '</div>';
      if (pane) document.body.appendChild(mask);
      else card.parentNode.insertBefore(mask, card);
      mask.addEventListener("click", function (e) { if (e.target === mask) mask.classList.remove("on"); });

      card.classList.remove("fold", "open");
      card.style.margin = "0";
      card.style.marginTop = "0";
      mask.querySelector(".panel-body").appendChild(card);
      if (card.id) byCardId[card.id] = mask;

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn sm panel-btn";
      btn.setAttribute("data-open-panel", mask.id);
      btn.innerHTML = '<span class="pi">' + escHtml(icon) + '</span>' + escHtml(title);
      toolbarFor(owner, !!pane).appendChild(btn);

      /* 生成结果类卡片：由隐藏变可见时自动打开弹窗 */
      if (card.hasAttribute("data-panel-auto") && window.MutationObserver) {
        new MutationObserver(function () {
          if (!card.hidden) mask.classList.add("on");
        }).observe(card, { attributes: true, attributeFilter: ["hidden"] });
      }
    });

    /* 多列容器里只剩一张卡时，让它占满整行，避免右侧大片空白 */
    document.querySelectorAll(".content .split, .content .tutor-layout").forEach(function (box) {
      var left = [].filter.call(box.children, function (c) {
        return c.tagName !== "SCRIPT" && c.tagName !== "TEMPLATE" && !c.classList.contains("modal-mask");
      });
      if (left.length === 1) box.classList.add("single-col");
    });

    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-open-panel]");
      if (b) {
        var m2 = document.getElementById(b.getAttribute("data-open-panel"));
        if (m2) m2.classList.add("on");
        return;
      }
      /* 页面里原有用 href="#id" 的入口继续可用：指向已弹窗化的卡片时改为打开弹窗 */
      var a = e.target.closest('a[href^="#"]');
      if (!a) return;
      var id = a.getAttribute("href").slice(1);
      if (byCardId[id]) { e.preventDefault(); byCardId[id].classList.add("on"); }
    });

    if (location.hash && byCardId[location.hash.slice(1)]) {
      byCardId[location.hash.slice(1)].classList.add("on");
    }
  }

  /* ---------- 页内模块导航：一屏放不下时，点击切换内容模块 ----------
     约定：
       <div class="pnav" data-pnav>
         <button data-pnav-tab="a" class="on">A</button>
         <button data-pnav-tab="b">B</button>
       </div>
       <div class="pnav-pane on" data-pnav-pane="a">…</div>
       <div class="pnav-pane" data-pnav-pane="b">…</div>
     模块与导航需在同一个父亲容器内（默认取导航的 parentNode）。 */
  function initPageNav() {
    var navs = [].slice.call(document.querySelectorAll("[data-pnav]"));
    if (!navs.length) return;
    navs.forEach(function (nav) {
      var scope = nav.parentNode;
      var tabs = [].slice.call(nav.querySelectorAll("[data-pnav-tab]"));
      var panes = [].slice.call(scope.querySelectorAll("[data-pnav-pane]"));
      if (!tabs.length || !panes.length) return;
      function show(name) {
        tabs.forEach(function (t) {
          t.classList.toggle("on", t.getAttribute("data-pnav-tab") === name);
        });
        panes.forEach(function (p) {
          p.classList.toggle("on", p.getAttribute("data-pnav-pane") === name);
        });
      }
      nav.addEventListener("click", function (e) {
        var b = e.target.closest("[data-pnav-tab]");
        if (!b || !nav.contains(b)) return;
        show(b.getAttribute("data-pnav-tab"));
      });
      var active = nav.querySelector("[data-pnav-tab].on") || tabs[0];
      show(active.getAttribute("data-pnav-tab"));
    });
  }

  /* ---------- 个人资料弹窗（单卡：修改公开资料） ---------- */
  function openProfileModal() {
    if (typeof window.EduAuth === "undefined" || !window.EduAuth.user) {
      location.href = "login.html";
      return;
    }
    var u = window.EduAuth.user;
    var mask = document.getElementById("modalProfile");
    if (!mask) {
      mask = document.createElement("div");
      mask.className = "modal-mask";
      mask.id = "modalProfile";
      document.body.appendChild(mask);
    }
    mask.innerHTML =
      '<div class="modal" style="max-width:520px">' +
      '<div class="modal-h"><b>个人资料</b><button class="x" type="button" data-close-modal>×</button></div>' +
      '<div class="modal-b">' +
      '<div class="pf-top"><button class="pf-avatar" type="button" id="mpPick" title="点击更换头像">' +
        (u.avatar ? '<img src="' + u.avatar + '" alt="">' : "<span>" + escHtml((u.display_name || u.username || "师").slice(-2)) + "</span>") +
        "<i>更换头像</i></button>" +
        '<input type="file" id="mpFile" accept="image/*" hidden>' +
      "</div>" +
      '<div class="field compact"><label>姓名</label><input id="mpName" value="' + (u.display_name || "") + '"></div>' +
      '<div class="field compact"><label>学号（只读）</label><input value="' + (u.username || "") + '" readonly></div>' +
      '<div class="grid g2" style="gap:8px">' +
      '<div class="field compact"><label>学院</label><input id="mpCollege" value="' + (u.college || "") + '"></div>' +
      '<div class="field compact"><label>专业</label><input id="mpMajor" value="' + (u.major || "") + '"></div>' +
      '</div>' +
      '<div class="field compact"><label>班级</label><input id="mpClass" value="' + (u.class_name || "") + '"></div>' +
      '<div class="form-actions" style="margin-top:10px">' +
      '<button class="btn primary sm" type="button" id="mpSave">保存资料</button>' +
      '<button class="btn sm ghost" type="button" data-close-modal>取消</button>' +
      '<span class="mini" id="mpSaveMsg" style="margin-left:auto"></span>' +
      '</div>' +
      '</div>' +
      '<div class="modal-f"><button class="btn ghost" type="button" data-close-modal>关闭</button></div>' +
      '</div>';

    var saveBtn = mask.querySelector("#mpSave");
    var nameBox = mask.querySelector("#mpName");
    if (nameBox) setTimeout(function () { nameBox.focus(); }, 40);
    // 头像：选择图片 → 居中裁剪为 256x256 → 转 dataURL
    var pendingAvatar = "";
    var pfFile = mask.querySelector("#mpFile");
    var pfPick = mask.querySelector("#mpPick");
    if (pfPick && pfFile) {
      pfPick.addEventListener("click", function () { pfFile.click(); });
      pfFile.addEventListener("change", function () {
        var f = pfFile.files && pfFile.files[0];
        if (!f) return;
        if (!/^image\//.test(f.type)) { toast("请选择图片文件"); return; }
        var fr = new FileReader();
        fr.onload = function () {
          var img = new Image();
          img.onload = function () {
            var size = 256, cv = document.createElement("canvas");
            cv.width = size; cv.height = size;
            var g = cv.getContext("2d");
            var s = Math.min(img.width, img.height);
            g.drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
            pendingAvatar = cv.toDataURL("image/jpeg", 0.86);
            pfPick.innerHTML = '<img src="' + pendingAvatar + '" alt=""><i>更换头像</i>';
          };
          img.src = fr.result;
        };
        fr.readAsDataURL(f);
      });
    }
    if (saveBtn) saveBtn.addEventListener("click", function () {
      var body = {},
        dn = (mask.querySelector("#mpName").value || "").trim(),
        col = (mask.querySelector("#mpCollege").value || "").trim(),
        maj = (mask.querySelector("#mpMajor").value || "").trim(),
        cls = (mask.querySelector("#mpClass").value || "").trim();
      if (dn) body.display_name = dn;
      if (col) body.college = col;
      if (maj) body.major = maj;
      if (cls) body.class_name = cls;
      if (pendingAvatar) body.avatar = pendingAvatar;
      if (!Object.keys(body).length) { toast("没有需要保存的内容"); return; }
      saveBtn.disabled = true; saveBtn.innerHTML = '<span class="spin"></span> 保存中…';
      var msg = mask.querySelector("#mpSaveMsg");
      var useAPI = (typeof window.EduAPI !== "undefined" && EduAPI.auth);
      var p = useAPI ? EduAPI.auth.updateMe(body) : apiFetch("/api/auth/me", "PATCH", body);
      p.then(function (nu) {
        saveBtn.disabled = false; saveBtn.textContent = "保存资料";
        toast("资料已保存");
        if (msg) msg.textContent = "✓ 已保存";
        if (window.EduAuth && window.EduAuth.user) {
          Object.assign(window.EduAuth.user, (nu && nu.id) ? nu : body);
          try { localStorage.setItem("edu.user", JSON.stringify(window.EduAuth.user)); } catch (e) {}
        }
        try { if (typeof Edu.renderSidebar === "function") Edu.renderSidebar(); } catch (e) {}
        setTimeout(function () { mask.classList.remove("on"); }, 450);
      }).catch(function (err) {
        saveBtn.disabled = false; saveBtn.textContent = "保存资料";
        var detail = err && (err.detail || err.message || err.error) || err;
        toast("保存失败：" + String(detail).slice(0, 40));
        if (msg) msg.textContent = "保存失败";
      });
    });

    mask.classList.add("on");
  }

  /* site.js 内置的 fetch 封装（兜底用，优先走 EduAPI） */
  function apiFetch(path, method, body) {
    var h = { "Content-Type": "application/json" };
    try {
      var tk = localStorage.getItem("edu.token");
      if (tk) h["Authorization"] = "Bearer " + tk;
    } catch (e) {}
    var url = path;
    if (path.charAt(0) === "/") {
      var apiBase = (typeof EduAPI !== "undefined" && EduAPI.base) || "http://127.0.0.1:8700/api";
      url = apiBase + path;
    }
    var opts = { method: method || "GET", headers: h, credentials: "same-origin" };
    if (body) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (d) {
        throw new Error((d && d.detail) || r.statusText || r.status);
      });
      return r.json();
    });
  }

  /* ---------- 表单模拟 ---------- */
  function initSim() {
    // 二次确认：发布、保存等不可逆操作，先确认再执行（捕获阶段，避免被 live 逻辑绕过）
    document.addEventListener("click", function (e) {
      var c = e.target.closest("[data-confirm]");
      if (!c) return;
      if (!window.confirm(c.getAttribute("data-confirm"))) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }, true);

    document.addEventListener("submit", function (e) {
      var form = e.target.closest("form[data-sim]");
      if (!form) return;
      if (Edu.isLive()) return; // live 模式由 live.js 接管，走真实接口
      e.preventDefault();
      var btn = form.querySelector('[type="submit"]');
      var target = document.querySelector(form.getAttribute("data-sim"));
      if (btn && !btn.dataset.label) btn.dataset.label = btn.innerHTML;

      function fail() {
        if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.label; }
        var box = form.querySelector(".form-error");
        if (!box) {
          box = document.createElement("div");
          box.className = "state is-denied form-error";
          box.innerHTML = '<div class="state-ic">!</div><div><b>生成失败</b><span>目标结果不存在或服务暂时不可用。</span></div>' +
            '<div class="state-actions"><button class="btn sm" type="button">重试</button></div>';
          form.appendChild(box);
          box.querySelector("button").addEventListener("click", function () {
            box.parentNode.removeChild(box);
            form.requestSubmit();
          });
        }
      }
      if (!target) return fail();

      // AI 生成中的进度状态（演示模式）
      var gen = /生成|评审|分析/.test(btn ? btn.textContent : "");
      var steps = gen ? [18, 52, 86, 100] : [0, 100];
      var i = 0;
      if (btn) btn.disabled = true;
      function tick() {
        if (btn) btn.innerHTML = '<span class="spin"></span> ' + (gen ? "生成中 " : "处理中 ") + steps[i] + "%";
        i++;
        if (i < steps.length) { setTimeout(tick, 420); return; }
        setTimeout(function () {
          if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.label; }
          target.hidden = false;
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          toast(form.getAttribute("data-msg") || "已完成");
        }, 320);
      }
      tick();
    });

    // 演示按钮：loading → 保存成功 toast
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-demo]");
      if (!b) return;
      if (Edu.isLive()) return; // live 模式由 live.js 接管真实导出/保存
      var label = b.innerHTML;
      b.disabled = true;
      b.innerHTML = '<span class="spin"></span> 处理中…';
      setTimeout(function () {
        b.disabled = false;
        b.innerHTML = label;
        toast(b.getAttribute("data-demo"));
      }, 520);
    });
  }

  /* ---------- 表格行键盘操作 ---------- */
  function initKeyboard() {
    function mark() {
      document.querySelectorAll("tbody tr").forEach(function (tr) {
        if (tr.querySelector("button, a.btn")) tr.tabIndex = 0;
      });
    }
    mark();
    document.addEventListener("click", function () { setTimeout(mark, 0); });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var tr = e.target.closest ? e.target.closest("tbody tr") : null;
      if (!tr) return;
      var tag = (e.target.tagName || "").toLowerCase();
      if (tag === "button" || tag === "a" || tag === "input" || tag === "select" || tag === "textarea") return;
      var btn = tr.querySelector("button, a.btn");
      if (btn) { e.preventDefault(); btn.click(); }
    });
  }

  /* ---------- 条形动画 ---------- */
  function initBars() {
    var bars = document.querySelectorAll(".bar > i[data-w]");
    if (!bars.length) return;
    requestAnimationFrame(function () {
      bars.forEach(function (b) { b.style.width = b.getAttribute("data-w") + "%"; });
    });
  }

  /* ---------- 勾选高亮 ---------- */
  function initChecks() {
    document.addEventListener("change", function (e) {
      var c = e.target.closest(".chk input");
      if (c) c.closest(".chk").classList.toggle("on", c.checked);
    });
  }

  /* ---------- 学生页哈希 ---------- */
  function initHashTabs() {
    if (page !== "student") return;
    function apply() {
      var key = (location.hash || "#home").slice(1);
      document.querySelectorAll('.tabs[data-hash] button').forEach(function (b) {
        if (b.getAttribute("data-tab") === key) b.click();
      });
      document.querySelectorAll(".nav a").forEach(function (a) {
        var h = a.getAttribute("href") || "";
        if (h.indexOf("#") < 0) return;
        a.classList.toggle("active", h.split("#")[1] === key);
      });
    }
    window.addEventListener("hashchange", apply);
    apply();
  }

  /* ---------- 在线检测与课程刷新 ---------- */
  function initLive() {
    if (!window.EduAPI) { return; }
    EduAPI.health().then(function () {
      Edu.state.live = true;
      return EduAPI.courses.list().then(function (list) {
        Edu.state.courses = list || [];
        var pick = document.querySelector("#coursePick");
        if (pick) {
          var saved = null; try { saved = localStorage.getItem("edu.course"); } catch (e) {}
          // 用合并后的列表重建下拉框，避免覆盖掉演示模式持久化的自定义课程
          var visible = currentCourses();
          var target = (saved && visible.some(function (c) { return String(c.id) === String(saved); })) ? saved
            : (visible[0] ? visible[0].id : "");
          Edu.state.selectedCourseId = target || null;
          pick.innerHTML = visible.length ? visible.map(function (c) {
            return '<option value="' + c.id + '">' + c.name + " · " + (c.class_name || c.class || "") + "</option>";
          }).join("") : '<option value="">（暂无课程）</option>';
          pick.value = target;
        }
        emitCourseChange();
        renderTopCourseSummary();
      });
    }).catch(function () {
      Edu.state.courses = [];
      // 优先恢复上次选中的课程（含本地保存的自定义课程），避免刷新后串课
      var saved = null; try { saved = localStorage.getItem("edu.course"); } catch (e) {}
      var visible = currentCourses();
      Edu.state.selectedCourseId = (saved && visible.some(function (c) { return String(c.id) === String(saved); }))
        ? saved
        : (visible[0] ? visible[0].id : null);
      var pick = document.querySelector("#coursePick");
      if (pick && Edu.state.selectedCourseId) pick.value = String(Edu.state.selectedCourseId);
      toast("无法连接后端服务，请确认 api_server.py 已启动");
      emitCourseChange();
      renderTopCourseSummary();
    });
  }

  /* 首页 hero 文案：有课程时说明关联关系，无课程时给出明确引导 */
  function renderHeroCourseLine() {
    var el = document.getElementById("heroCourseLine");
    if (!el) return;
    var c = getSelectedCourse();
    var name = c && (c.name || "").trim();
    el.textContent = name
      ? "所有内容都会关联到当前课程「" + name + "」。"
      : "尚未选择课程，请先在顶部选择或新建课程。";
  }

  function fillCourseFields() {
    var c = getSelectedCourse();
    renderHeroCourseLine();
    document.querySelectorAll("[data-fill]").forEach(function (el) {
      var v = el.getAttribute("data-fill");
      if (v.indexOf("course.") !== 0) return;
      var key = v.slice(7);
      var val, html = false;
      if (c) {
        switch (key) {
          case "name": val = c.name || "—"; break;
          case "class": val = c.class || "待完善"; break;
          case "className": val = c.class || "待完善"; break;
          case "classSize": val = c.classSize ? c.classSize + " 人" : ""; break;
          case "classWithSize": val = c.class ? (c.class + (c.classSize ? "（" + c.classSize + " 人）" : "")) : "待完善"; break;
          case "totalHours": val = c.totalHours ? c.totalHours + " 课时" : "未填写课时"; break;
          case "hours": val = c.totalHours ? c.totalHours + " 课时" : "待完善"; break;
          case "textbook": val = c.textbook || "待完善"; break;
          case "progress":
            if (c.currentSession && c.totalSessions) val = "第 " + c.currentSession + " 次课 / 共 " + c.totalSessions + " 次";
            else val = "进度待完善"; break;
          case "resourceCount": val = (c.resourceCount || 0) + " 份"; break;
          case "note": val = c.note || "待完善"; break;
          case "objectives": val = (c.objectives || "待完善").replace(/\n/g, "<br>"); html = true; break;
          case "key": val = c.key || "待完善"; break;
          case "diff": val = c.diff || "待完善"; break;
          case "desc": val = c.desc || "待完善"; break;
          default: val = c[key] || "待完善"; break;
        }
      } else {
        val = "—";
      }
      if (html) el.innerHTML = val;
      else if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") el.value = val;
      else if (el.tagName === "SELECT") {
        // select 里找匹配的 option，找不到就用 first option
        var found = null;
        Array.prototype.forEach.call(el.options, function (o) {
          if (o.textContent === val || o.value === val) found = o.value;
        });
        if (found) el.value = found;
        else if (el.options.length) el.options[0].textContent = val;
      }
      else el.textContent = val;
    });

    // 页面副标题动态化：所有 [data-page-sub] 元素里的课程引用统一替换
    document.querySelectorAll("[data-page-sub]").forEach(function (sub) {
      if (!c) return;
      var name = c.name || "";
      var text = sub.textContent;
      // 1) 替换「xxx」包裹的课程名
      text = text.replace(/「[^」]*」/g, "「" + name + "」");
      // 2) 替换（当前：xxx）格式的课程引用
      text = text.replace(/（当前：[^）]*）/g, "（当前：" + name + "）");
      sub.textContent = text;
    });
  }

  /* 版本历史：查看 / 比较差异 / 恢复旧版本 */
  function initVersions() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-versions]"), function (root) {
      var now = root.querySelector(".ver-now");
      if (typeof Edu.isLive === "function" && Edu.isLive()) {
        var right = root.querySelector(".card-h .right");
        if (right && !right.querySelector(".live-demo-tag")) {
          var tag = document.createElement("span");
          tag.className = "tag live-demo-tag";
          tag.textContent = "演示";
          tag.title = "版本历史为本地演示，恢复不会持久化到后端";
          right.insertBefore(tag, right.firstChild);
        }
      }
      root.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-vact]");
        if (!btn) return;
        var row = btn.closest(".ver-row");
        if (!row) return;
        var act = btn.getAttribute("data-vact");

        if (act === "restore") {
          if (!window.confirm("恢复到 " + row.getAttribute("data-ver") + " 后，当前内容将被替换。确定继续？")) return;
          Array.prototype.forEach.call(root.querySelectorAll(".ver-row"), function (r) {
            var isCur = r === row;
            r.classList.toggle("current", isCur);
            var old = r.querySelector('[data-vact="restore"]');
            if (isCur) {
              if (old) old.remove();
            } else if (!old) {
              var b = document.createElement("button");
              b.type = "button";
              b.className = "btn sm";
              b.setAttribute("data-vact", "restore");
              b.textContent = "恢复";
              var ops = r.querySelector(".ver-ops");
              if (ops) ops.appendChild(b);
            }
            var tag = r.querySelector(".ver-tag");
            if (tag) {
              tag.textContent = isCur ? "当前" : r.getAttribute("data-kind");
              tag.classList.toggle("on", isCur);
            }
          });
          if (now) {
            var saved = now.getAttribute("data-tpl") || "当前 {ver}";
            now.textContent = saved.replace("{ver}", row.getAttribute("data-ver"));
          }
          toast("已恢复到 " + row.getAttribute("data-ver") + (typeof Edu.isLive === "function" && Edu.isLive() ? "（演示：未持久化）" : ""));
          return;
        }

        var panel = row.querySelector(".ver-panel");
        if (!panel) return;
        var snap = panel.querySelector(".ver-snap");
        var diff = panel.querySelector(".ver-diff");
        var mode = act === "diff" ? "diff" : "view";
        if (panel.getAttribute("data-mode") === mode && !panel.hidden) {
          panel.hidden = true;
          return;
        }
        panel.setAttribute("data-mode", mode);
        panel.hidden = false;
        if (snap) snap.hidden = mode === "diff";
        if (diff) diff.hidden = mode !== "diff";
      });
    });
  }

  /* 可折叠卡片：点标题栏展开/收起，支持 #hash 定位自动展开 */
  function initFolds() {
    function setOpen(card, open) {
      card.classList.toggle("open", open);
      var head = card.querySelector("[data-fold-head]");
      if (head) head.setAttribute("aria-expanded", open ? "true" : "false");
    }
    document.addEventListener("click", function (e) {
      var head = e.target.closest("[data-fold-head]");
      if (!head) return;
      var card = head.closest(".card");
      if (!card) return;
      setOpen(card, !card.classList.contains("open"));
    });
    function openByHash() {
      var id = (location.hash || "").slice(1);
      if (!id) return;
      var el = document.getElementById(id);
      if (!el) return;
      var card = el.closest(".card");
      if (!card || !card.querySelector("[data-fold-head]")) return;
      setOpen(card, true);
    }
    window.addEventListener("hashchange", openByHash);
    openByHash();
  }

  document.addEventListener("DOMContentLoaded", function () {
    // 立即应用用户偏好（主题/字号），防止后续脚本覆盖
    applyPrefs();
    // 事件循环末尾再调一次，确保万无一失
    setTimeout(applyPrefs, 0);
    if (!window.EDU) return;
    buildSidebar();
    buildTopbar();
    initTabs();
    initGo();
    initModal();
    initSim();
    initKeyboard();
    initBars();
    initChecks();
    initHashTabs();
    initFolds();
    initPanels();
    initPageNav();
    fillCourseFields();
    Edu.onCourseChange(function () { fillCourseFields(); renderTopCourseSummary(); });
    initLive();
    initVersions();
    initAssistantFab();
  });
})();

/* ===== 目录锚点：点击平滑滚动（约 600ms，预留 64px 吸顶偏移）+ 滚动自动高亮 ===== */
(function () {
  "use strict";

  var DURATION = 600;
  var navs = [].slice.call(document.querySelectorAll("[data-toc], .toc"));
  if (!navs.length) return;

  function offsetTop() {
    var v = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--anchor-offset"), 10);
    return isNaN(v) ? 64 : v;
  }

  // 找到元素最近的纵向滚动容器；没有则返回 null（用 window 滚动）
  function scrollParent(el) {
    var p = el.parentNode;
    while (p && p !== document.body && p !== document.documentElement) {
      var s = getComputedStyle(p);
      if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 1) return p;
      p = p.parentNode;
    }
    return null;
  }

  function readScroll(box) { return box ? box.scrollTop : (window.pageYOffset || document.documentElement.scrollTop); }
  function writeScroll(box, v) { if (box) box.scrollTop = v; else window.scrollTo(0, v); }

  function smoothTo(box, to, dur) {
    var from = readScroll(box);
    var delta = to - from;
    if (Math.abs(delta) < 1) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      writeScroll(box, to);
      return;
    }
    var t0 = 0;
    function step(now) {
      if (!t0) t0 = now;
      var t = Math.min(1, (now - t0) / dur);
      var e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;   // easeInOutCubic
      writeScroll(box, from + delta * e);
      if (t < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  }

  function targetOf(link) {
    var href = link.getAttribute("href") || "";
    if (href.charAt(0) !== "#" || href.length < 2) return null;
    var id = decodeURIComponent(href.slice(1));
    return document.getElementById(id);
  }

  navs.forEach(function (nav) {
    var links = [].slice.call(nav.querySelectorAll('a[href^="#"]'));
    if (!links.length) return;

    var items = links.map(function (a) {
      var sec = targetOf(a);
      return sec ? { a: a, sec: sec } : null;
    }).filter(Boolean);
    if (!items.length) return;

    var box = scrollParent(items[0].sec);
    var current = -1;
    var ticking = false;

    function setActive(i) {
      if (i === current) return;
      current = i;
      items.forEach(function (it, k) {
        it.a.classList.toggle("is-current", k === i);
        if (k === i) it.a.setAttribute("aria-current", "true");
        else it.a.removeAttribute("aria-current");
      });
    }

    function spy() {
      ticking = false;
      var base = box ? box.getBoundingClientRect().top : 0;
      var line = offsetTop() + 8;
      var idx = 0;
      for (var i = 0; i < items.length; i++) {
        if (items[i].sec.getBoundingClientRect().top - base <= line) idx = i;
      }
      // 触底时高亮最后一项
      var maxScroll = box ? box.scrollHeight - box.clientHeight : document.documentElement.scrollHeight - window.innerHeight;
      if (readScroll(box) >= maxScroll - 2) idx = items.length - 1;
      setActive(idx);
    }

    function requestSpy() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(spy);
    }

    links.forEach(function (a) {
      a.addEventListener("click", function (e) {
        var sec = targetOf(a);
        if (!sec) return;
        e.preventDefault();
        var container = scrollParent(sec);
        var base = container ? container.getBoundingClientRect().top : 0;
        var to = sec.getBoundingClientRect().top - base + readScroll(container) - offsetTop();
        smoothTo(container, Math.max(0, to), DURATION);
        if (history.replaceState) history.replaceState(null, "", "#" + sec.id);
        else location.hash = sec.id;
        var idx = -1;
        items.forEach(function (it, k) { if (it.a === a) idx = k; });
        setActive(idx);
      });
    });

    (box || window).addEventListener("scroll", requestSpy, { passive: true });
    window.addEventListener("resize", requestSpy);
    requestSpy();
  });
})();
