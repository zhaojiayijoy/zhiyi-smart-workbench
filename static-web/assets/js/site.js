/* ===== 致壹 智能教育工作台 · 静态站公共脚本 ===== */
(function () {
  "use strict";

  var ICONS = {
    home: '<path d="M2.5 7.5 8 2.5l5.5 5V14h-4v-4h-3v4h-4z"/>',
    book: '<path d="M4 2.5h5.5a2 2 0 0 1 2 2V14H6a2 2 0 0 1-2-2z"/><path d="M4 2.5V14"/>',
    spark: '<path d="M8 2.5 9.2 6l3.5 1.2L9.2 8.4 8 12 6.8 8.4 3.3 7.2 6.8 6z"/>',
    tool: '<path d="M10.5 2.5 13.5 5.5 11.6 7.4 8.6 4.4z"/><path d="M8.6 6.2 3 11.8V13h1.2l5.6-5.6"/>',
    chat: '<path d="M2.8 3h10.4v7.2H7L3.4 13V3z"/>',
    check: '<path d="M3 8.4 6.2 11.6 13 4.8"/>',
    chart: '<path d="M3 13V8.2M6.7 13V4.5M10.4 13V9.4M13.5 13V6.6"/><path d="M2 13.6h12"/>',
    grid: '<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/>',
    file: '<path d="M4 2.5h5.5L12.5 5.5V13.5H4z"/><path d="M9.3 2.6v3h3"/>',
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
      label: "教学流程",
      items: [
        { href: "courses.html", icon: "book", text: "课程项目", page: "courses" },
        { href: "lesson.html", icon: "spark", text: "一键备课", page: "lesson" },
        { href: "training.html", icon: "tool", text: "创建实训", page: "training" },
        { href: "tutor.html", icon: "chat", text: "学生答疑", page: "tutor" },
        { href: "review.html", icon: "check", text: "作业评审", page: "review" },
        { href: "analytics.html", icon: "chart", text: "学情分析", page: "analytics" }
      ]
    },
    {
      label: "工具",
      items: [
        { href: "assistant.html", icon: "spark", text: "AI 助手", page: "assistant" },
        { href: "tools.html", icon: "tool", text: "教学工具", page: "tools" }
      ]
    },
    {
      label: "系统",
      items: [{ href: "settings.html", icon: "gear", text: "设置", page: "settings" }]
    }
  ];

  var STUDENT_GROUPS = [
    {
      label: "我的学习",
      items: [
        { href: "student.html#home", icon: "home", text: "学生首页", page: "student" },
        { href: "student.html#tasks", icon: "clock", text: "我的任务", page: "student" },
        { href: "student.html#qa", icon: "chat", text: "我的答疑", page: "student" },
        { href: "student.html#feedback", icon: "check", text: "教师反馈", page: "student" },
        { href: "student.html#review", icon: "book", text: "错题回顾", page: "student" }
      ]
    }
  ];

  var TITLES = {
    index: "工作台首页", courses: "课程项目", lesson: "一键备课", training: "创建实训",
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
    if (p.theme === "dark") root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");
    root.style.setProperty("--edu-font", (p.fontSize || 13.5) + "px");
  }
  applyPrefs();

  window.Edu = window.Edu || {};
  window.Edu.applyPrefs = applyPrefs;
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
    var base = (Edu.state.courses && Edu.state.courses.length) ? Edu.state.courses : (window.EDU.courses || []);
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
  function buildSidebar() {
    var aside = document.querySelector(".sidebar");
    if (!aside) return;
    var groups = isStudent ? STUDENT_GROUPS : GROUPS;
    var hash = (location.hash || "#home").slice(1);
    var nav = "";
    groups.forEach(function (g) {
      nav += '<div class="nav-label">' + g.label + "</div>";
      g.items.forEach(function (it) {
        var on = it.page === page;
        if (isStudent && page === "student" && it.href.indexOf("#") > -1) {
          on = it.href.split("#")[1] === hash;
        }
        nav += '<a href="' + it.href + '" class="' + (on ? "active" : "") + '">' + ic(it.icon) + "<span>" + it.text + "</span></a>";
      });
    });
    var u = isStudent ? window.EDU.student : window.EDU.teacher;
    aside.innerHTML =
      '<a class="brand" href="' + (isStudent ? "student.html" : "index.html") + '">' +
        '<div class="mark">致</div>' +
        '<div><div class="name">' + window.EDU.brand.name + '</div><div class="sub">' + window.EDU.brand.sub + "</div></div>" +
      "</a>" +
      '<div class="side-new"><button type="button" data-go="' + (isStudent ? "student.html#tasks" : "index.html") + '">' +
        ic("plus", 14) + (isStudent ? " 我的学习任务" : " 新建教学任务") + "</button></div>" +
      '<nav class="nav">' + nav + "</nav>" +
      '<div class="side-foot"><div class="avatar">' + u.initials + "</div>" +
        "<div><b>" + (isStudent ? u.name : "本地用户") + "</b><span>" + (isStudent ? u.class : "教师 · 单租户") + "</span></div></div>";
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
        '<label class="course-pick"><span>课程</span><select id="coursePick">' + options + '</select></label>' +
        (isStudent ? "" : '<a class="btn sm" href="courses.html#newCourse">＋ 创建课程</a>') +
        '<div class="mode-switch">' +
          '<button type="button" class="' + (isStudent ? "" : "on") + '" data-go="index.html">教师工作台</button>' +
          '<button type="button" class="' + (isStudent ? "on" : "") + '" data-go="student.html">学生空间</button>' +
        "</div>" +
        '<span class="mini" style="white-space:nowrap">' + (isStudent ? "学生 · 本地账号" : "教师 · 本地账号") + "</span>" +
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
      // 点击课程摘要 → 展开下拉
      var cs = e.target.closest(".course-summary");
      if (cs) {
        var pick = document.querySelector("#coursePick");
        if (pick) pick.focus();
      }
    });

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
    var mask = document.querySelector("#modalNewTask");
    if (!mask) {
      mask = document.createElement("div");
      mask.className = "modal-mask";
      mask.id = "modalNewTask";
      mask.innerHTML =
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
      document.body.appendChild(mask);
    }
    document.addEventListener("click", function (e) {
      if (e.target.closest('[data-open-modal="new-task"]')) {
        // 动态显示当前课程名
        var sub = mask.querySelector(".modal-b [data-page-sub], .modal-b .sub");
        if (sub) {
          var cur = getSelectedCourse();
          var name = cur ? (cur.name || "（未选课程）") : "（未选课程）";
          // 如果已有 data-page-sub，则 fillCourseFields 已处理过；否则手动更新
          if (sub.hasAttribute && sub.hasAttribute("data-page-sub")) {
            // fillCourseFields 已自动更新，什么都不做
          } else {
            sub.textContent = '选择要开始的教学环节。所有内容都会关联到当前课程「' + name + '」。';
          }
        }
        mask.classList.add("on");
        return;
      }
      if (e.target.closest("[data-close-modal]")) { mask.classList.remove("on"); }
    });
    mask.addEventListener("click", function (e) { if (e.target === mask) mask.classList.remove("on"); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") mask.classList.remove("on");
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
  function liveBadge(on) {
    var el = document.getElementById("liveBadge");
    if (!el) { el = document.createElement("div"); el.id = "liveBadge"; document.body.appendChild(el); }
    el.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:60;font-size:11px;padding:5px 10px;" +
      "border-radius:20px;line-height:1;box-shadow:0 2px 8px rgba(37,50,45,.12);" +
      (on ? "background:#DCE8E1;color:#294D40;border:1px solid #365B4C;"
          : "background:#EEE8DB;color:#66736C;border:1px solid #CDBFA7;");
    el.textContent = on ? "● 已连接真实接口" : "○ 演示模式";
    el.title = on ? "本地接口 8700 已连接，数据为真实数据" :
      "未连接本地接口，当前为内置演示数据；启动 api_server.py 后刷新即接入真实数据";
  }

  function initLive() {
    if (!window.EduAPI) { liveBadge(false); return; }
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
        liveBadge(true);
        emitCourseChange();
        renderTopCourseSummary();
      });
    }).catch(function () {
      liveBadge(false);
      Edu.state.courses = window.EDU.courses || [];
      // 优先恢复上次选中的课程（含演示模式持久化的自定义课程），避免刷新后串课
      var saved = null; try { saved = localStorage.getItem("edu.course"); } catch (e) {}
      var visible = currentCourses();
      Edu.state.selectedCourseId = (saved && visible.some(function (c) { return String(c.id) === String(saved); }))
        ? saved
        : (visible[0] ? visible[0].id : null);
      var pick = document.querySelector("#coursePick");
      if (pick && Edu.state.selectedCourseId) pick.value = String(Edu.state.selectedCourseId);
      toast("演示模式：启动 api_server.py 后刷新可接入真实数据");
      emitCourseChange();
      renderTopCourseSummary();
    });
  }

  function fillCourseFields() {
    var c = getSelectedCourse();
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
      // 3) 兜底：如果还有写死的三个 demo 课程名，也替换掉
      ["消费者行为分析", "市场营销基础", "数字营销实训"].forEach(function (demo) {
        if (name && demo !== name) text = text.split(demo).join(name);
      });
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

  document.addEventListener("DOMContentLoaded", function () {
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
    fillCourseFields();
    Edu.onCourseChange(function () { fillCourseFields(); renderTopCourseSummary(); });
    initLive();
    initVersions();
  });
})();
