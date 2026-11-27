/* ===== 致壹 静态站 · 真实接口接入（live.js）=====
   仅在 Edu.isLive()===true（本地 api_server.py 可达）时接管页面：
   - 拉取真实数据渲染 KPI / 表格 / 列表
   - 拦截 form[data-sim] 走真实 API
   - 把 data-demo 导出按钮改为真实下载
   - 非 live 时不介入，由 site.js 的演示逻辑兜底
   依赖：site.js（window.Edu）、api.js（window.EduAPI）*/
(function () {
  "use strict";
  var API = window.EduAPI, Edu = window.Edu;
  if (!API || !Edu) return;
  var page = (document.body && document.body.getAttribute("data-page")) || "index";

  /* 真实模型名：Live 启动时拉取一次，替换页面里写死的"智谱 GLM-4" */
  var REAL_MODEL = null;
  function applyRealModel() {
    if (!REAL_MODEL) return;
    window.__eduModel = REAL_MODEL;
    var m = REAL_MODEL;
    // 1) 替换正文文本节点里写死的模型名（跳过 script/style）
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        if (!p) return NodeFilter.FILTER_REJECT;
        var tag = p.tagName;
        if (tag === "SCRIPT" || tag === "STYLE") return NodeFilter.FILTER_REJECT;
        return /智谱\s*GLM-4|GLM-4-Air/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var nodes = [], nd;
    while ((nd = walker.nextNode())) nodes.push(nd);
    nodes.forEach(function (x) {
      x.nodeValue = x.nodeValue.replace(/智谱\s*GLM-4-Air/g, m).replace(/智谱\s*GLM-4/g, m)
        .replace(/GLM-4-Air/g, m).replace(/GLM-4/g, m);
    });
    // 2) 模型下拉：用真实模型名替换去重，并选中
    $all("select[data-model-select]").forEach(function (sel) {
      var seen = {};
      for (var i = sel.options.length - 1; i >= 0; i--) {
        var o = sel.options[i];
        var t = String(o.textContent).replace(/智谱\s*GLM-4(-Air)?/g, m).replace(/GLM-4(-Air)?/g, m);
        if (seen[t]) { o.remove(); continue; }
        seen[t] = 1; o.textContent = t; o.value = t;
      }
      sel.value = m;
    });
  }

  /* ---------------- 通用工具 ---------------- */
  function $(s, c) { return (c || document).querySelector(s); }
  function $all(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function h(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"]/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
    });
  }
  function fmtTime(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    if (isNaN(d.getTime())) return "";
    var p = function (n) { return n < 10 ? "0" + n : "" + n; };
    return p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }
  function fmtSize(b) {
    b = Number(b) || 0;
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
    if (b < 1024 * 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + " MB";
    return (b / 1024 / 1024 / 1024).toFixed(2) + " GB";
  }
  function notify(msg) {
    var el = document.querySelector(".toast");
    if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
    el.textContent = msg;
    requestAnimationFrame(function () { el.classList.add("on"); });
    clearTimeout(notify._t);
    notify._t = setTimeout(function () { el.classList.remove("on"); }, 2400);
  }
  function pid() { return Edu.state.selectedCourseId || (Edu.getSelectedCourse() && Edu.getSelectedCourse().id) || null; }
  function onLive(fn) {
    Edu.onCourseChange(function () {
      if (!Edu.isLive()) return;
      try { fn(); } catch (e) { console.error("[live]", e); }
    });
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) { btn._lab = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spin"></span> ' + (label || "处理中…"); }
    else { btn.disabled = false; btn.innerHTML = btn._lab || btn.innerHTML; }
  }
  function courseName(id) {
    var c = (Edu.state.courses || []).filter(function (x) { return String(x.id) === String(id); })[0];
    return c ? c.name : "";
  }
  function selectCourse(id) {
    if (typeof Edu.selectCourse === "function") { Edu.selectCourse(id); return; }
    var pick = document.querySelector("#coursePick");
    if (pick) { pick.value = id; pick.dispatchEvent(new Event("change")); }
    else { Edu.state.selectedCourseId = id; try { localStorage.setItem("edu.course", id); } catch (e) {} Edu.onCourseChange && id && location.reload(); }
  }
  function barAnim(scope) {
    requestAnimationFrame(function () {
      $all(".bar > i[data-w]", scope || document).forEach(function (i) {
        i.style.width = (i.getAttribute("data-w") || 0) + "%";
      });
    });
  }
  function renderBars(scope, rows) {
    if (!scope) return;
    if (!rows || !rows.length) { scope.innerHTML = '<div class="mini" style="padding:10px 0">暂无数据</div>'; return; }
    var max = 0;
    rows.forEach(function (r) { if (Number(r.value) > max) max = Number(r.value); });
    scope.innerHTML = rows.map(function (r) {
      var w = max ? Math.round(Number(r.value) / max * 100) : 0;
      return '<div class="bar-row"><div class="t"><b>' + h(r.label) + '</b><span>' + h(r.suffix || r.value) + '</span></div>' +
        '<div class="bar"><i data-w="' + w + '" style="width:0"></i></div></div>';
    }).join("");
    barAnim(scope);
  }
  function setKpis(scope, vals) {
    var cards = $all(".kpi", scope);
    vals.forEach(function (v, i) {
      var k = cards[i]; if (!k) return;
      var val = k.querySelector(".value"), foot = k.querySelector(".foot");
      if (val && v.value !== undefined) val.textContent = v.value;
      if (foot && v.foot !== undefined) foot.textContent = v.foot;
    });
  }
  var KIND = { lesson: "备课", training: "实训", qa: "答疑", review: "评审", nextlesson: "下一课", agent: "助手", load: "加载" };
  var KIND_IC = { lesson: "✦", training: "◈", qa: "◌", review: "✓", nextlesson: "◔", agent: "✧", load: "▤" };
  function kindLabel(k) { return KIND[k] || k || "任务"; }
  function bindBtn(scope, text, fn) {
    $all("button, a", scope).forEach(function (b) {
      if ((b.textContent || "").indexOf(text) > -1 && !b.getAttribute("data-live-bound")) {
        b.setAttribute("data-live-bound", "1");
        b.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); fn(e, b); });
      }
    });
  }

  /* ---------------- index ---------------- */
  function initIndex() {
    onLive(function () {
      var p = pid(); if (!p) return;
      API.lesson.history(p).then(function (rows) {
        var box = document.querySelector(".card .card-b.tight");
        if (!box) return;
        rows = (rows || []).slice(0, 2);
        if (!rows.length) {
          box.innerHTML = '<div class="list-item"><div class="li-ic">✦</div><div style="flex:1"><div class="li-t">暂无备课包</div><div class="li-s">去「一键备课」生成第一个</div></div><a class="btn sm ghost" href="lesson.html">去生成</a></div>';
          return;
        }
        box.innerHTML = rows.map(function (r) {
          var ck = (r.checks && r.checks.consistency) ? " · 一致性检查完成" : "";
          return '<div class="list-item"><div class="li-ic">✦</div><div style="flex:1"><div class="li-t">' + h(r.topic) +
            '</div><div class="li-s">' + fmtTime(r.ts) + ck + '</div></div><a class="btn sm ghost" href="lesson.html">查看</a></div>';
        }).join("");
      }).catch(function () {});
      // 第二卡：最近实训任务
      API.training.history(p).then(function (rows) {
        var cards = document.querySelectorAll(".recent-grid .card-b.tight");
        var box = cards[1];
        if (!box) return;
        rows = (rows || []).slice(0, 2);
        if (!rows.length) { box.innerHTML = '<div class="list-item"><div class="li-ic">◈</div><div style="flex:1"><div class="li-t">暂无实训任务</div><div class="li-s">去「创建实训」生成第一个</div></div><a class="btn sm ghost" href="training.html">去生成</a></div>'; return; }
        box.innerHTML = rows.map(function (r) {
          return '<a class="list-item" href="training.html"><div class="li-ic">◈</div><div style="flex:1"><div class="li-t">' + h(r.scenario || "(无标题)") + '</div><div class="li-s">' + fmtTime(r.ts) + '</div></div><span class="tag warn">草稿</span></a>';
        }).join("");
      }).catch(function () {});
      // 第三卡：待评审作业
      API.review.history(p).then(function (rows) {
        var cards = document.querySelectorAll(".recent-grid .card-b.tight");
        var box = cards[2];
        if (!box) return;
        rows = rows || [];
        var pending = rows.filter(function (r) { return r.status !== "published"; }).length;
        if (!rows.length) { box.innerHTML = '<div class="list-item"><div class="li-ic">✓</div><div style="flex:1"><div class="li-t">暂无待评审作业</div><div class="li-s">上传学生提交后开始评审</div></div><a class="btn sm ghost" href="review.html">去评审</a></div>'; return; }
        box.innerHTML = '<a class="list-item" href="review.html"><div class="li-ic">✓</div><div style="flex:1"><div class="li-t">' + pending + ' 份待教师复核</div><div class="li-s">共 ' + rows.length + ' 份评审记录</div></div><span class="tag warn">待处理</span></a>';
      }).catch(function () {});
      API.tasks.list(p).then(function (rows) {
        var stack = document.querySelectorAll(".card .stack .rule");
        if (!stack.length) return;
        var pending = (rows || []).filter(function (t) { return t.status !== "ok"; }).slice(0, 3);
        var host = stack[0].parentNode;
        if (!pending.length) { host.innerHTML = '<div class="rule">暂无待处理事项。</div>'; return; }
        host.innerHTML = pending.map(function (t) {
          return '<div class="rule">' + h(kindLabel(t.kind)) + "：" + h(t.prompt || "(无标题)") + "（" + fmtTime(t.created_at) + "）</div>";
        }).join("");
      }).catch(function () {});
    });
  }

  /* ---------------- courses ---------------- */
  function initCourses() {
    var form = $('form[data-sim="#courseCreated"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var btn = form.querySelector('[type="submit"]');
      var vals = {};
      $all("input, textarea, select", form).forEach(function (el) {
        var lab = (el.previousElementSibling && el.previousElementSibling.textContent) || el.name || "";
        if (!el.value) return;
        if (lab.indexOf("课程名称") > -1) vals.name = el.value;
        else if (lab.indexOf("班级") > -1 || lab.indexOf("对象") > -1) vals.audience = el.value;
        else if (lab.indexOf("课时") > -1) vals.hours = el.value;
        else if (lab.indexOf("教材") > -1 || lab.indexOf("标准版本") > -1) vals.textbook_version = el.value;
        else if (lab.indexOf("描述") > -1) vals.description = el.value;
        else if (lab.indexOf("学习目标") > -1) vals.objectives = el.value;
        else if (lab.indexOf("重点") > -1) vals.key_points = el.value;
        else if (lab.indexOf("难点") > -1) vals.difficulties = el.value;
        else if (lab.indexOf("进度") > -1) vals.progress = el.value;
        else if (lab.indexOf("备注") > -1) vals.description = el.value;
      });
      if (!vals.name) { notify("课程名称必填"); return; }
      busy(btn, true, "创建中…");
      API.courses.create(vals).then(function (c) {
        busy(btn, false);
        notify("课程已创建：" + c.name);
        return API.courses.list().then(function (list) { Edu.state.courses = list || []; });
      }).then(function () {
        selectCourse(vals._id || (Edu.state.courses[0] && Edu.state.courses[0].id));
        var created = $("#courseCreated");
        if (created) { created.hidden = false; created.textContent = "已创建课程「" + vals.name + "」并设为当前课程。"; }
        form.reset();
        loadCourses();
      }).catch(function (err) { busy(btn, false); notify("创建失败：" + (err.message || err)); });
    });

    function loadCourses() {
      var p = pid();
      API.courses.list().then(function (list) {
        Edu.state.courses = list || [];
        var tb = document.querySelectorAll("table tbody");
        // 全部课程表：第一个 table
        var allTbody = tb[0];
        if (allTbody && list.length) {
          allTbody.innerHTML = list.map(function (c) {
            return '<tr><td><b>' + h(c.name) + '</b></td><td>' + h(c.class_name || c.audience || "") + '</td>' +
              '<td>' + h(c.hours || "") + '</td><td>' + h(c.progress || "") + '</td>' +
              '<td>' + (c.file_count != null ? c.file_count + " 份" : "—") + '</td>' +
              '<td><button class="btn sm" type="button" data-switch-course="' + c.id + '">切换</button></td></tr>';
          }).join("");
        }
        if (p) loadOverview(p);
      }).catch(function () {});
    }
    function loadOverview(p) {
      API.courses.overview(p).then(function (o) {
        setKpis(document, [
          { value: o.files_total, foot: "教材 / 标准 / 案例 / 课件" },
          { value: o.last_lesson_title || "—", foot: o.lesson_count ? "共 " + o.lesson_count + " 个备课包" : "暂无" },
          { value: o.training_count, foot: "实训任务" },
          { value: o.pending_review, foot: "AI 已生成评分证据" },
          { value: o.qa_count ? ("答疑 " + o.qa_count + " 条") : "—", foot: "近 30 天" },
          { value: o.review_count ? ("评审 " + o.review_count + " 份") : "—", foot: "累计记录" }
        ]);
        var ctx = document.querySelectorAll(".ctx b");
        var cur = (Edu.state.courses || []).filter(function (c) { return String(c.id) === String(p); })[0] || {};
        if (ctx[0]) ctx[0].textContent = cur.name || "—";
        if (ctx[1]) ctx[1].textContent = cur.class_name || cur.audience || "—";
        if (ctx[2]) ctx[2].textContent = cur.hours || "—";
        if (ctx[3]) ctx[3].textContent = cur.progress || "—";
        if (ctx[4]) ctx[4].textContent = o.files_total + " 份";
      }).catch(function () {});
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-switch-course]");
      if (b) { e.preventDefault(); selectCourse(b.getAttribute("data-switch-course")); }
    });
    onLive(loadCourses);
  }

  /* ---------------- lesson ---------------- */
  function renderLesson(pkg, taskId) {
    var out = $("#lessonOut"); if (!out) return;
    var lp = pkg.lesson_plan || {}, ppt = pkg.ppt || {}, q = pkg.questions || {}, rub = pkg.rubric || [];
    var checks = pkg.checks || {};
    var pct = checks.consistency_pct;
    var headTags = (typeof pct === "number") ? '<span class="tag ok">一致性 ' + pct + '%</span>' :
      (checks.ok ? '<span class="tag ok">校验通过</span>' : '<span class="tag warn">校验未通过</span>');
    out.querySelector(".card-h h2").textContent = pkg.topic || "备课包";
    var right = out.querySelector(".card-h .right");
    if (right) right.innerHTML = '<button class="btn sm ghost" type="button" id="lessonCite">引用依据</button>' + headTags + '<span class="tag">待教师审核</span>';
    var citeBtn = out.querySelector("#lessonCite");
    if (citeBtn) citeBtn.addEventListener("click", function () {
      var box = out.querySelector("#lessonCiteBox");
      if (box) box.hidden = !box.hidden;
    });

    function list(arr) { return (arr || []).map(function (x) { return "<li>" + h(x) + "</li>"; }).join(""); }
    var steps = (lp.steps || []).map(function (s, i) {
      return '<div class="list-item"><div class="li-ic">' + (i + 1) + '</div><div><div class="li-t">' + h(s.phase || "") +
        '（' + h(s.minutes || "") + ' 分钟）</div><div class="li-s">教师：' + h(s.teacher || "") + '｜学生：' + h(s.student || "") +
        (s.design_intent ? '｜意图：' + h(s.design_intent) : "") + '</div></div></div>';
    }).join("");
    var planHtml = '<h3>教学目标</h3><ul class="mini" style="margin:0 0 10px;padding-left:18px">' + list(lp.objectives) + "</ul>" +
      '<div class="grid g3" style="margin-bottom:10px"><div><span class="k mini">重点</span><div class="mini">' + h((lp.key_points || []).join("；")) + '</div></div>' +
      '<div><span class="k mini">难点</span><div class="mini">' + h((lp.difficulties || []).join("；")) + '</div></div>' +
      '<div><span class="k mini">准备</span><div class="mini">' + h((lp.preparation || []).join("；")) + '</div></div></div>' +
      '<h3>教学流程</h3><div class="stack" style="gap:8px">' + (steps || '<div class="mini">暂无流程</div>') + '</div>' +
      (lp.homework ? '<h3 style="margin-top:10px">作业</h3><div class="mini">' + h(lp.homework) + '</div>' : "");

    var KIND_LABEL = {
      cover: "封面", objectives: "学习目标", agenda: "课堂流程", concept: "概念讲解",
      example: "案例分析", activity: "课堂活动", quiz: "课堂练习",
      homework: "分层作业", summary: "课堂小结", board: "板书设计"
    };
    function arr(v) {
      if (!v) return [];
      if (typeof v === "string") return v.split(/[\n；;]+/).map(function (x) { return x.replace(/^[•·\-\s]+/, "").trim(); }).filter(Boolean);
      return Array.isArray(v) ? v : [v];
    }
    var slides = (ppt.slides || []).map(function (s, i) {
      var kind = s.kind || "concept";
      var bullets = arr(s.bullets);
      var tblObj = s.table && typeof s.table === "object" ? s.table : {};
      var rows = arr(tblObj.rows).map(function (r) { return arr(r); });
      var head = '<div class="mini" style="margin-bottom:2px">P' + (i + 1) + " · " +
        h(KIND_LABEL[kind] || "内容") + (s.duration_min ? " · " + h(s.duration_min) + " 分钟" : "") +
        "</div><b>" + h(s.title || "") + "</b>";
      var body = bullets.length
        ? '<div class="mini" style="margin-top:4px">' + bullets.map(function (b) {
            return "• " + h(b);
          }).join("<br>") + "</div>"
        : "";
      var tbl = rows.length
        ? '<div class="table-wrap" style="margin-top:6px"><table><thead><tr>' +
          arr(tblObj.headers).map(function (x) { return "<th>" + h(x) + "</th>"; }).join("") +
          "</tr></thead><tbody>" + rows.map(function (r) {
            return "<tr>" + r.map(function (c) { return '<td class="mini">' + h(c) + "</td>"; }).join("") + "</tr>";
          }).join("") + "</tbody></table></div>"
        : "";
      var vis = (s.visual && typeof s.visual === "object" && s.visual.prompt && s.visual.type !== "none")
        ? '<div class="mini" style="margin-top:4px">图示：' + h(s.visual.prompt) + "</div>" : "";
      var acts = (s.teacher_action || s.student_action)
        ? '<div class="mini" style="margin-top:4px">教师：' + h(s.teacher_action || "—") +
          "｜学生：" + h(s.student_action || "—") + "</div>" : "";
      var take = s.key_takeaway ? '<div class="mini" style="margin-top:4px">结论：' + h(s.key_takeaway) + "</div>" : "";
      var notes = s.notes ? '<div class="mini" style="margin-top:4px">讲稿：' + h(s.notes) + "</div>" : "";
      return '<div class="rule">' + head + body + tbl + vis + acts + take + notes + "</div>";
    }).join("");
    var pptHtml = '<div class="grid g2">' + (slides || '<div class="mini">暂无课件</div>') + '</div>';

    function qlist(arr) {
      return (arr || []).map(function (x, i) {
        return '<div class="rule"><b>' + (i + 1) + '. </b>' + h(x.q || "") +
          (x.hint1 ? '<div class="mini">提示：' + h(x.hint1) + '</div>' : "") + '</div>';
      }).join("");
    }
    var drillHtml = '<h3>基础</h3><div class="stack" style="gap:8px">' + qlist(q.basic) + '</div>' +
      '<h3 style="margin-top:10px">应用</h3><div class="stack" style="gap:8px">' + qlist(q.applied) + '</div>' +
      '<h3 style="margin-top:10px">拓展</h3><div class="stack" style="gap:8px">' + qlist(q.extension) + '</div>';
    var keyHtml = (q.basic || []).concat(q.applied || []).concat(q.extension || []).map(function (x, i) {
      return '<div class="rule"><b>' + (i + 1) + '. 参考答案</b><br>' + h(x.answer || "") +
        (x.hint2 ? '<div class="mini">关键步骤：' + h(x.hint2) + '</div>' : "") + '</div>';
    }).join("");
    var rubHtml = rub.length ?
      '<div class="table-wrap"><table><thead><tr><th>维度</th><th>分值</th><th>优秀</th><th>良好</th><th>合格</th><th>待改进</th></tr></thead><tbody>' +
      rub.map(function (r) {
        return '<tr><td>' + h(r.dimension) + '</td><td>' + h(r.weight) + '</td><td class="mini">' + h(r.excellent) + '</td><td class="mini">' + h(r.good) + '</td><td class="mini">' + h(r.pass) + '</td><td class="mini">' + h(r.fail) + '</td></tr>';
      }).join("") + '</tbody></table></div>' : '<div class="mini">暂无评分量规</div>';

    var panes = out.querySelectorAll(".tabpane");
    var map = { plan: planHtml, ppt: pptHtml, drill: drillHtml, key: keyHtml, rubric: rubHtml };
    panes.forEach(function (p) { var k = p.getAttribute("data-pane"); if (map[k] !== undefined) p.innerHTML = map[k]; });

    out.hidden = false;
    out.scrollIntoView({ behavior: "smooth", block: "start" });
    // 导出按钮
    bindBtn(out, "导出 Word", function () { window.open(API.lesson.exportUrl(taskId, "docx")); });
    bindBtn(out, "导出 PPT", function () { window.open(API.lesson.exportUrl(taskId, "pptx")); });
    bindBtn(out, "导出 Excel", function () { window.open(API.lesson.exportUrl(taskId, "xlsx")); });
    bindBtn(out, "通过审核并保存", function (e, b) {
      if (!taskId) { notify("请先生成备课包"); return; }
      busy(b, true, "保存中…");
      API.lesson.approve(taskId).then(function (r) {
        busy(b, false);
        var names = (r.files || []).map(function (f) { return f.name; }).join("、");
        notify("已通过审核，已存入课程资料：" + names);
      }).catch(function (err) { busy(b, false); notify("保存失败：" + (err.message || err)); });
    });
    bindBtn(out, "换一版", function (e, b) {
      if (!taskId) { notify("请先生成备课包"); return; }
      busy(b, true, "重新生成中…");
      API.lesson.regenerateAll(taskId).then(function (r) {
        busy(b, false);
        renderLesson(r.pkg, r.task_id);
        notify("已按原参数生成新版备课包");
      }).catch(function (err) { busy(b, false); notify("重生成失败：" + (err.message || err)); });
    });
  }

  function initLesson() {
    var form = $('form[data-sim="#lessonOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid(); if (!p) { notify("请先选择课程"); return; }
      var btn = form.querySelector('[type="submit"]');
      var inputs = $all("input, textarea, select", form);
      var topic = "", style = "", extra = "", student_level = "", hours = "", lesson_type = "";
      var outputs = [];
      inputs.forEach(function (el) {
        var lab = (el.previousElementSibling && el.previousElementSibling.textContent) || el.name || el.placeholder || "";
        if (el.type === "checkbox" && el.checked && !el.closest("#docChecks") && el.parentElement.textContent.indexOf("双模型") < 0 && el.parentElement.textContent.indexOf("本次使用") < 0) {
          var t = (el.parentElement.textContent || "").replace(/\s/g, "");
          if (t) outputs.push(t);
        }
        if (!el.value) return;
        if (lab.indexOf("课题") > -1) topic = el.value;
        else if (lab.indexOf("课型") > -1) lesson_type = el.value;
        else if (lab.indexOf("课时") > -1) hours = el.value;
        else if (lab.indexOf("基础") > -1 || lab.indexOf("水平") > -1) student_level = el.value;
        else if (lab.indexOf("风格") > -1 || lab.indexOf("活动要求") > -1) style = el.value;
        else if (lab.indexOf("补充") > -1) extra = el.value;
      });
      if (!topic) { notify("请填写本次课题"); return; }
      var dualBox = $all('.checks label.chk', form).filter(function (lab) { return /双模型/.test(lab.textContent); })[0];
      var dual = dualBox ? !!dualBox.querySelector('input:checked') : false;
      var docIds = $all("#docChecks input:checked").map(function (i) {
        return Number(i.getAttribute("data-fid"));
      }).filter(function (n) { return n; });
      busy(btn, true, "生成中…");
      API.lesson.generate({ project_id: Number(p), topic: topic, lesson_type: lesson_type, hours: hours,
        student_level: student_level, style: style, extra: extra, outputs: outputs.length ? outputs : undefined,
        file_ids: docIds.length ? docIds : undefined,
        dual_check: dual })
        .then(function (res) { busy(btn, false); renderLesson(res.pkg, res.task_id); notify("备课包已生成"); })
        .catch(function (err) { busy(btn, false); var o = $("#lessonOut"); if (o) { o.hidden = false; o.querySelector(".card-b").innerHTML = '<div class="rule" style="color:var(--warn)">生成失败：' + h(err.message || err) + '</div>'; } notify("生成失败"); });
    });

    function loadDocs() {
      var p = pid(); if (!p) return;
      var box = document.getElementById("docChecks");
      var hint = document.getElementById("docHint");
      if (!box) return;
      API.files.list(p).then(function (files) {
        files = files || [];
        if (!files.length) {
          box.innerHTML = '<span class="mini">当前课程暂无资料，将使用课程信息生成。</span>';
          if (hint) hint.textContent = "未找到课程资料，可先到「课程资源」上传。";
          return;
        }
        box.innerHTML = files.map(function (f) {
          return '<label class="chk on"><input type="checkbox" data-fid="' + f.id + '" checked>' + h(f.name) + '</label>';
        }).join("");
        if (hint) hint.textContent = "已选 " + files.length + " / " + files.length + " 份资料，生成时仅引用所选资料。";
      }).catch(function () {
        if (box) box.innerHTML = '<span class="mini">资料加载失败，将使用课程信息生成。</span>';
      });
    }
    document.addEventListener("change", function (e) {
      if (!e.target || !e.target.closest || !e.target.closest("#docChecks")) return;
      var all = $all("#docChecks input");
      var checked = all.filter(function (i) { return i.checked; }).length;
      var hint = document.getElementById("docHint");
      if (hint) hint.textContent = "已选 " + checked + " / " + all.length + " 份资料" +
        (checked ? "，生成时仅引用所选资料。" : "，未选将使用全部课程信息。");
    });

    function loadHistory() {
      var p = pid(); if (!p) return;
      API.lesson.history(p).then(function (rows) {
        rows = rows || [];
        var tb = document.querySelectorAll("#packs table tbody")[0];
        var pc = document.getElementById("packCount");
        if (pc) pc.textContent = rows.length + " 条";
        if (!tb) return;
        if (!rows.length) { tb.innerHTML = '<tr><td colspan="6" class="mini">暂无备课包</td></tr>'; return; }
        var cells = rows.map(function (r) {
          var pct = (r.checks && r.checks.consistency_pct);
          return '<tr><td>' + h(r.topic) + '</td><td>' + fmtTime(r.ts) + '</td><td>' + h(r.model || "") + '</td>' +
            '<td>' + (typeof pct === "number" ? pct + "%" : "—") + '</td><td><span class="tag">待审核</span></td>' +
            '<td><button class="btn sm" type="button" data-open-lesson="' + r.task_id + '">打开</button></td></tr>';
        });
        var shown = 3;
        function paint() {
          var more = cells.length > 3
            ? '<tr><td colspan="6"><button class="btn sm ghost" type="button" data-pack-more="1">' +
              (shown >= cells.length ? "收起" : "展开全部（" + cells.length + " 条）") + '</button></td></tr>'
            : "";
          tb.innerHTML = cells.slice(0, shown).join("") + more;
        }
        tb.onclick = function (e) {
          if (!e.target.closest("[data-pack-more]")) return;
          shown = shown >= cells.length ? 3 : cells.length;
          paint();
        };
        paint();
      }).catch(function () {});
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-open-lesson]");
      if (b) { e.preventDefault(); var id = b.getAttribute("data-open-lesson"); API.lesson.get(id).then(function (pkg) { renderLesson(pkg, id); }).catch(function (err) { notify("打开失败：" + (err.message || err)); }); }
    });
    onLive(loadDocs);
    onLive(loadHistory);
    // 从学情分析跳转过来时（lesson.html?task=123）直接打开对应备课包
    var qt = new URLSearchParams(location.search).get("task");
    if (qt) API.lesson.get(qt).then(function (pkg) { renderLesson(pkg, qt); })
      .catch(function () { notify("未找到指定备课包"); });
  }
  function renderTraining(pkg, taskId) {
    var out = $("#trainOut"); if (!out) return;
    out.querySelector(".card-h h2").textContent = "任务包：" + (pkg.title || "");
    var g = out.querySelector(".grid.g2");
    if (g) {
      var cols = g.children;
      if (cols[0]) {
        cols[0].innerHTML = '<h3>项目背景</h3><p class="mini" style="margin:0 0 12px">' + h(pkg.background || "") + '</p>' +
          '<h3>学生角色</h3><p class="mini" style="margin:0 0 12px">' + h(pkg.student_role || "") + '</p>' +
          '<h3>任务目标</h3><div class="stack" style="gap:6px">' + ((pkg.data_tasks || []).map(function (d) {
            return '<div class="rule">② ' + h(d.task || "") + (d.points ? "（" + d.points + " 分）" : "") + '</div>';
          }).join("") || '<div class="mini">暂无</div>') + '</div>';
      }
      if (cols[1]) {
        var items = [{ t: "Excel", a: (pkg.excel_requirements || []).join("<br>") },
          { t: "Word", a: (pkg.word_requirements || []).join("<br>") },
          { t: "PPT", a: (pkg.ppt_requirements || []).join("<br>") }];
        cols[1].innerHTML = '<h3>交付物要求</h3><div class="stack" style="gap:8px">' +
          items.map(function (it) { return '<div class="rule"><b>' + it.t + '</b><br>' + it.a + '</div>'; }).join("") + '</div>';
      }
    }
    out.hidden = false;
    out.scrollIntoView({ behavior: "smooth", block: "start" });
    bindBtn(out, "导出任务说明", function () { window.open(API.training.exportUrl(taskId, "docx")); });
    bindBtn(out, "发布任务", function (e, b) {
      if (!taskId) { notify("请先生成实训任务包"); return; }
      busy(b, true, "发布中…");
      API.training.status(taskId, "published")
        .then(function () { busy(b, false); notify("已发布到学生空间"); document.dispatchEvent(new CustomEvent("edu:training-changed")); })
        .catch(function (err) { busy(b, false); notify("发布失败：" + (err.message || err)); });
    });
    bindBtn(out, "保存草稿", function (e, b) {
      if (!taskId) { notify("请先生成实训任务包"); return; }
      busy(b, true, "保存中…");
      API.training.status(taskId, "draft")
        .then(function () { busy(b, false); notify("已保存为草稿"); document.dispatchEvent(new CustomEvent("edu:training-changed")); })
        .catch(function (err) { busy(b, false); notify("保存失败：" + (err.message || err)); });
    });
  }
  function initTraining() {
    var form = $('form[data-sim="#trainOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid(); if (!p) { notify("请先选择课程"); return; }
      var tas = $all("textarea", form);
      var scenario = tas[0] ? tas[0].value : "", extra = tas[1] ? tas[1].value : "";
      if (!scenario.trim()) { notify("请填写场景描述"); return; }
      var btn = form.querySelector('[type="submit"]');
      busy(btn, true, "生成中…");
      API.training.generate({ project_id: Number(p), scenario: scenario, extra: extra })
        .then(function (res) { busy(btn, false); renderTraining(res.pkg, res.task_id); notify("实训任务包已生成"); })
        .catch(function (err) { busy(btn, false); notify("生成失败：" + (err.message || err)); });
    });
    function loadHistory() {
      var p = pid(); if (!p) return;
      API.training.history(p).then(function (rows) {
        rows = rows || [];
        var tb = document.querySelectorAll("#taskList table tbody")[0];
        var tc = document.getElementById("taskCount");
        if (tc) tc.textContent = rows.length + " 个";
        if (!tb) return;
        if (!rows.length) { tb.innerHTML = '<tr><td colspan="6" class="mini">暂无实训任务</td></tr>'; return; }
        tb.innerHTML = rows.map(function (r) {
          var tag = r.status === "published" ? '<span class="tag ok">已发布</span>' : '<span class="tag">草稿</span>';
          return '<tr><td><b>' + h(r.scenario) + '</b></td><td>' + tag + '</td><td>100</td><td>—</td><td>' + fmtTime(r.ts) + '</td>' +
            '<td><button class="btn sm" type="button" data-open-train="' + r.task_id + '">查看</button></td></tr>';
        }).join("");
      }).catch(function () {});
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-open-train]");
      if (b) { var id = b.getAttribute("data-open-train"); API.training.get(id).then(function (pkg) { renderTraining(pkg, id); }).catch(function (err) { notify("打开失败：" + (err.message || err)); }); }
    });
    function loadTemplates() {
      var bar = document.getElementById("tplBar");
      if (!bar) return;
      API.training.templates().then(function (rows) {
        rows = rows || [];
        if (!rows.length) { bar.innerHTML = '<span class="mini">暂无模板，可直接填写场景。</span>'; return; }
        bar.innerHTML = rows.map(function (t) {
          return '<button class="chk" type="button" data-tpl="' + h(t.key) + '">' + h(t.name) + '</button>';
        }).join("");
        bar.onclick = function (e) {
          var b = e.target.closest("[data-tpl]");
          if (!b) return;
          var key = b.getAttribute("data-tpl");
          var tpl = rows.filter(function (x) { return String(x.key) === key; })[0];
          if (!tpl) return;
          var sc = document.getElementById("trainScenario");
          var ex = document.getElementById("trainExtra");
          if (sc) { sc.value = tpl.scenario || ""; sc.dispatchEvent(new Event("input")); }
          if (ex && tpl.extra) { ex.value = tpl.extra; ex.dispatchEvent(new Event("input")); }
          notify("已套用模板：" + (tpl.name || ""));
        };
      }).catch(function () {});
    }
    onLive(loadTemplates);
    onLive(loadHistory);
    document.addEventListener("edu:training-changed", loadHistory);
  }

  /* ---------------- tutor ---------------- */
  function initTutor() {
    var form = $('form[data-sim="#askOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid();
      var q = ($all("textarea", form)[0] || {}).value;
      if (!q || !q.trim()) { notify("请填写学生问题"); return; }
      var btn = form.querySelector('[type="submit"]');
      busy(btn, true, "生成中…");
      API.tutor.reply({ project_id: p ? Number(p) : null, question: q })
        .then(function (res) {
          busy(btn, false);
          var detail = document.querySelectorAll(".card .card-b")[1]; // 问题详情卡
          var r = res.reply || {};
          var me = document.querySelector(".card .msg.me .bubble");
          if (me) me.textContent = q;
          var panes = document.querySelectorAll(".card .tabpane");
          if (panes[0]) panes[0].innerHTML = '<div class="rule">' + h(r.feedback || "") + (r.question_to_student ? '<div class="mini" style="margin-top:6px">下一步问题：' + h(r.question_to_student) + '</div>' : "") + '</div>';
          if (panes[1]) panes[1].innerHTML = '<div class="rule">知识点：' + h(r.knowledge_point || "") + '<br>错因：' + h(r.error_type || "") + (r.need_teacher ? '<br><span style="color:var(--warn)">建议教师接管</span>' : "") + '</div>';
          if (panes[2]) panes[2].innerHTML = '<div class="mini" style="margin:0 0 8px">点击「查看完整解析」由 AI 给出完整答案（学生完成尝试后可见）。</div>' +
            '<button class="btn" type="button" id="fullAnsBtn">查看完整解析</button>';
          var fb = document.getElementById("fullAnsBtn");
          if (fb) fb.addEventListener("click", function () {
            busy(fb, true, "生成中…");
            API.tutor.full({ project_id: p ? Number(p) : null, question: q, thread_id: res.thread_id })
              .then(function (f) { busy(fb, false); var d = f.reply || {}; panes[2].innerHTML = '<div class="rule"><b>完整解析</b><br>' + h(d.solution || "") + (d.answer ? '<br><b>答案：</b>' + h(d.answer) : "") + '</div>'; })
              .catch(function (err) { busy(fb, false); notify("失败：" + (err.message || err)); });
          });
          var out = $("#askOut"); if (out) { out.hidden = false; out.textContent = "答疑已创建，已写入本地记录。"; }
          notify("答疑已创建");
          loadTutor();
        })
        .catch(function (err) { busy(btn, false); notify("失败：" + (err.message || err)); });
    });
    var TUTOR_LABEL = { ai: "AI 引导中", teacher: "教师接管", solved: "已解决" };
    var currentTid = null;
    function setTutorStatus(status) {
      if (!currentTid) { notify("请先在左侧选择一条答疑记录"); return; }
      API.tutor.status(currentTid, status).then(function () {
        notify("状态已更新为：" + TUTOR_LABEL[status]);
        loadTutor();
      }).catch(function (err) { notify("更新失败：" + (err.message || err)); });
    }
    function syncTutorDetail(item) {
      var title = document.getElementById("tutorDetailTitle");
      var status = document.getElementById("tutorDetailStatus");
      var bubble = document.getElementById("tutorBubble");
      if (title) title.textContent = (item.getAttribute("data-name") || "学生") + " 的提问";
      var st = item.getAttribute("data-status") || "AI 引导中";
      if (status) { status.textContent = st; status.className = "tag " + (st === "已解决" ? "ok" : (st === "等待学生尝试" ? "warn" : "acc")); }
      if (bubble) bubble.textContent = item.getAttribute("data-q") || "";
    }
    function loadTutor() {
      var p = pid();
      Promise.all([API.tutor.history(p), API.tasks.list(p, "qa")]).then(function (res) {
        var threads = res[0] || [], qas = res[1] || [];
        setKpis(document, [
          { value: qas.length, foot: "近 30 天" },
          { value: qas.filter(function (t) { return t.status === "ok"; }).length, foot: "解决率 " + (qas.length ? Math.round(qas.filter(function (t) { return t.status === "ok"; }).length / qas.length * 100) : 0) + "%" },
          { value: qas.filter(function (t) { return t.status !== "ok"; }).length, foot: "未解决" },
          { value: (function () { var m = {}; qas.forEach(function (t) { var k = ((t.meta || {}).knowledge_point || ""); if (k) m[k] = (m[k] || 0) + 1; }); var top = Object.keys(m).sort(function (a, b) { return m[b] - m[a]; })[0]; return top || "—"; })(), foot: "高频知识点" }
        ]);
        var list = document.querySelector(".tutor-list .card-b");
        if (!list) return;
        var cnt = document.getElementById("tutorCount");
        if (cnt) cnt.textContent = threads.length + " 条";
        var rows = qas.length ? qas.slice(0, 8).map(function (t) {
          return { tid: t.id, question: t.prompt || (t.meta || {}).question || "(无问题)",
                   ts: t.created_at, status: (t.meta || {}).status || "ai" };
        }) : threads.slice(0, 8).map(function (r) {
          return { tid: null, question: r.question, ts: r.ts, status: "ai" };
        });
        if (!rows.length) {
          list.innerHTML = '<div class="mini" style="padding:14px 0">暂无答疑记录。学生提问后会出现在这里。</div>';
          var t = document.getElementById("tutorDetailTitle"), s = document.getElementById("tutorDetailStatus"), b = document.getElementById("tutorBubble");
          if (t) t.textContent = "暂无提问";
          if (s) { s.textContent = "—"; s.className = "tag"; }
          if (b) b.textContent = "暂无答疑内容。";
          currentTid = null;
          return;
        }
        list.innerHTML = rows.map(function (r, i) {
          var q = r.question || "(无问题)";
          var label = TUTOR_LABEL[r.status] || TUTOR_LABEL.ai;
          var cls = r.status === "solved" ? "ok" : (r.status === "teacher" ? "warn" : "acc");
          return '<div class="tq' + (i === 0 ? " on" : "") + '" data-tid="' + (r.tid || "") + '" data-name="学生" data-status="' + label + '" data-q="' + h(q) + '">' +
            '<div class="q">' + h(q) + '</div>' +
            '<div class="meta"><span>学生</span><span>·</span><span>' + fmtTime(r.ts) + '</span><span class="tag ' + cls + '">' + label + '</span></div></div>';
        }).join("");
        var first = list.querySelector(".tq");
        if (first) { first.classList.add("on"); currentTid = first.getAttribute("data-tid"); syncTutorDetail(first); }
      }).catch(function () {});
    }
    // 列表点击切换详情（事件委托，兼容 live 动态渲染与静态演示项）
    var listHost = document.querySelector(".tutor-list");
    if (listHost) listHost.addEventListener("click", function (e) {
      var item = e.target.closest(".tq");
      if (!item) return;
      $all(".tq", listHost).forEach(function (o) { o.classList.remove("on"); });
      item.classList.add("on");
      currentTid = item.getAttribute("data-tid") || null;
      syncTutorDetail(item);
    });
    bindBtn(document, "标记已解决", function () { setTutorStatus("solved"); });
    bindBtn(document, "转教师接管", function () { setTutorStatus("teacher"); });
    onLive(loadTutor);
  }

  /* ---------------- review ---------------- */
  function initReview() {
    var form = $('form[data-sim="#reviewOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid();
      var fileInput = form.querySelector('input[type="file"]');
      var student = ($all("input", form).filter(function (i) { return i.type === "text" && i.previousElementSibling && /学生/.test(i.previousElementSibling.textContent); })[0] || {}).value || "";
      var file = fileInput && fileInput.files && fileInput.files[0];
      var btn = form.querySelector('[type="submit"]');
      function doEval(text, name) {
        var sel = document.getElementById("rubricPick");
        var tpl = sel && rubricMap[sel.value];
        busy(btn, true, "评审中…");
        API.review.evaluate({ project_id: p ? Number(p) : null, submission_text: text, file_name: name || "学生提交", student: student,
          rubric: tpl ? tpl.rows : undefined })
          .then(function (res) { busy(btn, false); renderReview(res.review, res.task_id, student, name); notify("评审完成"); })
          .catch(function (err) { busy(btn, false); notify("评审失败：" + (err.message || err)); });
      }
      if (file) {
        var name = file.name;
        if (/\.(txt|md|csv|json)$/i.test(name)) {
          var fr = new FileReader();
          fr.onload = function () { doEval(String(fr.result || ""), name); };
          fr.onerror = function () { notify("读取文件失败"); busy(btn, false); };
          fr.readAsText(file);
        } else {
          notify("暂仅支持直接粘贴正文或 txt/md/csv 文件（docx/pdf 需先提取正文）");
          // 降级：用文件名占位，提醒粘贴正文
          var out = $("#reviewOut"); if (out) { out.hidden = false; out.textContent = "请把提交正文粘贴到上传处，或改用 txt/md/csv 文件。"; }
        }
      } else {
        notify("请选择学生提交文件或粘贴正文");
      }
    });
    var currentReviewId = null;
    var currentDims = [];
    var finalForm = $('form[data-sim="#finalOut"]');
    if (finalForm) finalForm.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!currentReviewId) { notify("请先生成一条评审记录"); return; }
      var btn = finalForm.querySelector('[type="submit"]');
      var scores = {};
      $all('input[type="number"]', finalForm).forEach(function (el, i) {
        var d = currentDims[i];
        var v = parseFloat(el.value);
        if (d && !isNaN(v)) scores[d.name || d.dimension || ("维度" + (i + 1))] = v;
      });
      var ta = $all("textarea", finalForm)[0];
      busy(btn, true, "保存中…");
      API.review.patch(currentReviewId, {
        scores: Object.keys(scores).length ? scores : null,
        comment: ta ? ta.value : "", status: "published"
      }).then(function (r) {
        busy(btn, false);
        var out = $("#finalOut");
        if (out) {
          out.hidden = false;
          out.textContent = "教师终评已保存并发布" +
            (r && r.final_total != null ? "，总分 " + r.final_total : "") + "。";
        }
        notify("终评已保存");
        loadHistory();
      }).catch(function (err) { busy(btn, false); notify("保存失败：" + (err.message || err)); });
    });

    var rubricMap = {};
    function applyRubric(key) {
      var tpl = rubricMap[key];
      var inputs = finalForm ? $all('input[type="number"]', finalForm) : [];
      inputs.forEach(function (el, i) {
        var row = tpl && tpl.rows && tpl.rows[i];
        var lab = el.closest(".field") ? el.closest(".field").querySelector("label") : null;
        if (row) {
          if (lab) lab.textContent = row.dimension || ("维度" + (i + 1));
          if (row.weight) el.max = row.weight;
        }
      });
    }
    function loadRubrics() {
      var sel = document.getElementById("rubricPick");
      if (!sel) return;
      API.review.rubrics().then(function (rows) {
        (rows || []).forEach(function (r) { rubricMap[r.key] = r; });
        sel.innerHTML = '<option value="">默认量规（内容 / 数据 / 表达 / 可行性）</option>' +
          (rows || []).map(function (r) {
            return '<option value="' + h(r.key) + '">' + h(r.name) + '</option>';
          }).join("");
      }).catch(function () {});
    }
    var rubricSel = document.getElementById("rubricPick");
    if (rubricSel) rubricSel.addEventListener("change", function () { applyRubric(rubricSel.value); });
    onLive(loadRubrics);

    function reviewAction(status) {
      if (!currentReviewId) { notify("请先在列表中选择一条评审记录"); return; }
      var ff = $('form[data-sim="#finalOut"]');
      var ta = ff ? $all("textarea", ff)[0] : null;
      API.review.patch(currentReviewId, {
        status: status, reason: ta ? ta.value : ""
      }).then(function () {
        notify(status === "returned" ? "已退回学生修改" : "已标记为需人工检查");
        loadHistory();
      }).catch(function (err) { notify("操作失败：" + (err.message || err)); });
    }
    bindBtn(document, "退回修改", function () { reviewAction("returned"); });
    bindBtn(document, "需要人工检查", function () { reviewAction("manual"); });

    function renderReview(review, taskId, student, name) {
      var dims = review.dimensions || [];
      currentReviewId = taskId || currentReviewId;
      currentDims = dims;
      var tb = document.querySelectorAll("table tbody")[1]; // 分维度评分证据表
      if (tb) {
        tb.innerHTML = dims.map(function (d) {
          return '<tr><td>' + h(d.name || d.dimension || "") + '</td><td><b>' + h(d.score) + '</b>/' + h(d.max) + '</td>' +
            '<td class="wrap">' + h(d.evidence || "") + (d.suggestion ? '<div class="mini">建议：' + h(d.suggestion) + '</div>' : "") + '</td>' +
            '<td>' + h(d.location || "") + '</td><td><input type="checkbox" checked></td></tr>';
        }).join("") || '<tr><td colspan="5" class="mini">暂无维度数据</td></tr>';
      }
      var acc = document.querySelector(".card .card-h .tag.acc");
      if (acc) acc.textContent = "AI 初评 " + (review.total != null ? review.total : "");
      var subTb = document.querySelectorAll("table tbody")[0];
      if (subTb) {
        var row = '<tr><td><b>' + h(student || "学生") + '</b><div class="mini">—</div></td><td>' + h(name || "学生提交") + '</td><td>' + h(review.total) + '</td><td><span class="tag warn">待复核</span></td></tr>';
        subTb.insertAdjacentHTML("afterbegin", row);
      }
      // 终评表单预填
      var inputs = $all('input[type="number"]', finalForm);
      dims.forEach(function (d, i) { if (inputs[i]) inputs[i].value = d.score; });
      var total = document.querySelector(".form-actions b");
      if (total) total.textContent = review.total;
      bindBtn(document, "导出", function () { if (taskId) window.open(API.review.exportUrl(taskId)); });
    }
    function resetReviewEvidence() {
      var ev = document.getElementById("reviewEvidenceTb");
      if (ev) ev.innerHTML = '<tr><td colspan="5" class="mini">暂无评分证据，选择左侧一条评审记录后展示。</td></tr>';
      var ai = document.getElementById("reviewAiScore");
      if (ai) ai.textContent = "AI 初评 —";
      var total = document.getElementById("reviewFinalTotal");
      if (total) total.textContent = "—";
      var ff = $('form[data-sim="#finalOut"]');
      if (ff) $all('input[type="number"]', ff).forEach(function (i) { i.value = ""; });
    }
    function loadHistory() {
      var p = pid();
      API.review.history(p).then(function (rows) {
        rows = rows || [];
        var tb = document.querySelectorAll("table tbody")[0];
        if (tb) {
          if (!rows.length) {
            tb.innerHTML = '<tr><td colspan="4" class="mini">暂无评审记录，上传学生提交后开始 AI 评审。</td></tr>';
          } else {
            tb.innerHTML = rows.map(function (r) {
              var st = r.status === "published" ? '<span class="tag ok">已发布</span>' :
                       (r.status === "returned" ? '<span class="tag warn">待修改</span>' :
                       (r.status === "manual" ? '<span class="tag warn">需人工检查</span>' :
                       '<span class="tag warn">待复核</span>'));
              return '<tr><td><b>' + h(r.student || "学生") + '</b></td><td>' + h(r.file_name || "") + '</td><td>' + (r.total != null ? h(r.total) : "—") + '</td><td>' + st + '</td></tr>';
            }).join("");
          }
        }
        // 同步页头徽章 / 学生提交计数 / 正在查看
        var ht = document.getElementById("reviewHeadTags");
        if (ht) {
          var pending = rows.filter(function (r) { return r.status !== "published"; }).length;
          ht.innerHTML = '<span class="tag warn">' + pending + ' 份待复核</span><span class="tag ok">' + (rows.length - pending) + ' 份已发布</span>';
        }
        var sc = document.getElementById("reviewSubmitCount");
        if (sc) sc.textContent = rows.length + " 份";
        var vw = document.getElementById("reviewViewing");
        if (vw) vw.textContent = rows[0] ? ((rows[0].student || "学生") + " · " + (rows[0].file_name || "")) : "暂无";
        if (!currentReviewId && rows[0]) currentReviewId = rows[0].task_id;
        // 无选中记录时清掉写死的假证据与终评预填
        resetReviewEvidence();
      }).catch(function () {});
    }
    onLive(loadHistory);
  }

  /* ---------------- analytics ---------------- */
  function initAnalytics() {
    var applyBtn = $all('button[data-demo]').filter(function (b) { return b.textContent.indexOf("应用筛选") > -1; })[0];
    if (applyBtn) {
      applyBtn.setAttribute("data-live-bound", "1");
      applyBtn.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); loadAggregate(); });
    }
    var nextBtn = $all('a.btn[href="lesson.html"]').filter(function (a) { return a.textContent.indexOf("备课") > -1; })[0];
    bindBtn(document, "导出报告", function () { var p = pid(); if (p) window.open(API.analytics.exportUrl(p)); });

    var lastAgg = null;
    var lastPayload = null;
    function filterPayload() {
      var daysEl = document.getElementById("anaDays");
      var kpEl = document.getElementById("anaKp");
      var src = $all("#anaSrc input:checked").map(function (i) { return i.value; });
      var days = daysEl && daysEl.value ? Number(daysEl.value) : null;
      return {
        project_id: Number(pid()),
        days: days || undefined,
        knowledge_point: kpEl ? kpEl.value.trim() : "",
        sources: src.length ? src : ["答疑", "评审", "实训"]
      };
    }
    function genReviewLesson(withPpt) {
      var p = pid();
      if (!p) { notify("请先选择课程"); return; }
      var weak = (lastAgg && lastAgg.top_knowledge || []).slice(0, 2).map(function (x) { return x[0]; });
      var topic = "讲评课：" + (weak.length ? weak.join("、") : "阶段学情讲评");
      notify("正在生成讲评课…");
      API.lesson.generate({ project_id: Number(p), topic: topic, lesson_type: "讲评课", hours: "1 课时" })
        .then(function (res) {
          notify("讲评课已生成");
          if (withPpt) window.open(API.lesson.exportUrl(res.task_id, "pptx"));
          else location.href = "lesson.html?task=" + res.task_id;
        })
        .catch(function (err) { notify("生成失败：" + (err.message || err)); });
    }
    bindBtn(document, "重新分析", function () { loadAggregate(); });
    $all('button[data-demo]').forEach(function (b) {
      if (b.textContent.indexOf("重新加载") > -1 && !b.getAttribute("data-live-bound")) {
        b.setAttribute("data-live-bound", "1");
        b.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); loadAggregate(); });
      }
    });
    if (nextBtn) nextBtn.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); loadNext(lastAgg); });
    bindBtn(document, "生成讲评课 PPT", function () { genReviewLesson(true); });
    bindBtn(document, "生成讲评课", function () { genReviewLesson(false); });

    function clearAnalyticsDemo() {
      // 以下块没有对应后端接口，Live 下统一清成诚实空状态，避免展示写死的演示数据
      var stale = document.getElementById("staleNote");
      if (stale) stale.hidden = true;
      ["pointsConclusion", "dimsConclusion"].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = "none";
      });
      var mc = document.getElementById("masteryCard");
      if (mc) {
        var tb = mc.querySelector("tbody");
        if (tb) tb.innerHTML = '<tr><td colspan="5" class="mini">暂无掌握率数据（接口暂未接入）。</td></tr>';
        var mini = mc.querySelector(".card-h .mini");
        if (mini) mini.textContent = "数据待接入";
      }
      function ph(msg) { return '<div class="mini" style="padding:4px 0">' + msg + "</div>"; }
      var map = {
        weakStack: "正在生成下一课方案…",
        remedialStack: "暂无补偿练习建议。",
        questionStack: "暂无课堂追问建议。"
      };
      Object.keys(map).forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = ph(map[id]);
      });
      var rt = document.getElementById("reviewTime");
      if (rt) rt.style.display = "none";
      var at = document.getElementById("actionLessonTag");
      if (at) at.textContent = "待生成";
    }
    function loadAggregate() {
      var p = pid(); if (!p) return;
      lastPayload = filterPayload();
      busy(applyBtn, true, "分析中…");
      API.analytics.aggregate(lastPayload).then(function (a) {
        busy(applyBtn, false);
        lastAgg = a;
        setKpis(document, [
          { value: a.qa_count, foot: "覆盖 " + (a.student_answered || 0) + " 名学生" },
          { value: a.review_count, foot: "已评审" },
          { value: (a.need_remedial || []).length, foot: "均分 < 60" },
          { value: (a.can_extend || []).length, foot: "均分 ≥ 85" }
        ]);
        renderBars($('[data-pane="points"] .bars'), (a.top_knowledge || []).map(function (x) { return { label: x[0], value: x[1], suffix: x[1] + " 次" }; }));
        renderBars($('[data-pane="dims"] .bars'), (a.dimension_rows || []).map(function (r) { return { label: r.name, value: r.avg, suffix: r.avg + " 分" }; }));
        var errTb = $('[data-pane="errors"] table tbody');
        if (errTb) {
          errTb.innerHTML = (a.error_rows || []).map(function (r) {
            return '<tr><td>' + h(r.error) + '</td><td>' + h(r.percent) + '%</td><td class="mini">—</td><td class="mini">—</td></tr>';
          }).join("") || '<tr><td colspan="4" class="mini">暂无错误类型数据</td></tr>';
        }
        var sup = $('[data-pane="supports"] .stack');
        if (sup) {
          sup.innerHTML = '<div class="list-item"><span class="tag warn">重点支持</span><div style="flex:1"><div class="li-t">' + (a.need_remedial || []).length + ' 名学生均分低于 60</div></div></div>' +
            '<div class="list-item"><span class="tag ok">拓展</span><div style="flex:1"><div class="li-t">' + (a.can_extend || []).length + ' 名学生均分高于 85</div></div></div>' +
            (a.sample_warning ? '<div class="list-item"><span class="tag">提示</span><div style="flex:1"><div class="li-t">样本量较少，结论仅供参考</div></div></div>' : "");
        }
        // 数据来源
        var sc = a.source_counts || {};
        renderBars(document.querySelectorAll(".card .bars")[2] || $all(".bars")[2], [
          { label: "学生答疑", value: sc["答疑"] || 0, suffix: (sc["答疑"] || 0) + " 条" },
          { label: "作业评审", value: sc["评审"] || 0, suffix: (sc["评审"] || 0) + " 份" },
          { label: "实训提交", value: sc["实训"] || 0, suffix: (sc["实训"] || 0) + " 个" }
        ]);
        clearAnalyticsDemo();
        loadNext(a);
      }).catch(function (err) { busy(applyBtn, false); notify("分析失败：" + (err.message || err)); });
    }
    function loadNext(a) {
      var p = pid(); if (!p) return;
      var host = document.querySelectorAll(".split .card .card-b .stack")[0]; // 下一课方案
      if (!host) return;
      host.innerHTML = '<div class="mini">正在生成下一课方案…</div>';
      API.analytics.next(lastPayload || { project_id: Number(p) }).then(function (res) {
        var plan = res.plan || {};
        var rl = plan.review_lesson || {};
        var html = '<p class="sub" style="margin-bottom:10px">' + h(plan.prefill && plan.prefill.topic || (rl.title || "下一课方案")) + '</p>';
        html += '<div class="stack" style="gap:8px">';
        (rl.outline || []).forEach(function (o) {
          html += '<div class="list-item"><div class="li-ic">' + (o.minutes || "") + "'</div><div><div class=\"li-t\">" + h(o.content || "") + "</div><div class=\"li-s\">" + h(o.method || "") + "</div></div></div>";
        });
        if (plan.sequence_adjustment && plan.sequence_adjustment.length) {
          html += '<div class="rule"><b>顺序调整：</b>' + h(plan.sequence_adjustment.join("；")) + '</div>';
        }
        if (plan.remedial_exercises && plan.remedial_exercises.length) {
          html += '<div class="rule"><b>补偿练习：</b>' + plan.remedial_exercises.map(function (x) { return h(x.q); }).join("；") + '</div>';
        }
        html += '</div>';
        host.innerHTML = html;
      }).catch(function () { host.innerHTML = '<div class="mini">下一课方案生成失败（可能缺少 LLM 配置）。</div>'; });
    }
    onLive(loadAggregate);
  }

  /* ---------------- assistant ---------------- */
  function initAssistant() {
    var chat = $("#chat"), form = $("#composer");
    onLive(function () {
      // 清空内置演示对话，只保留欢迎语（第一条 .msg.ai），并隐藏演示提示
      if (chat) {
        var welcome = chat.querySelector(".msg.ai");
        chat.innerHTML = "";
        if (welcome) chat.appendChild(welcome);
      }
      var demoNote = document.getElementById("assistantDemoNote");
      if (demoNote) demoNote.style.display = "none";
    });
    function appendMsg(role, html) {
      if (!chat) return;
      var d = document.createElement("div"); d.className = "msg " + (role === "me" ? "me" : "ai");
      d.innerHTML = '<div class="who">' + (role === "me" ? "李" : "AI") + '</div><div class="bubble">' + html + '</div>';
      chat.appendChild(d); d.scrollIntoView({ behavior: "smooth", block: "end" }); return d;
    }
    function addActs(msg) {
      if (!msg || msg.querySelector(".msg-acts")) return;
      var acts = document.createElement("div");
      acts.className = "msg-acts";
      acts.setAttribute("style", "display:flex;gap:8px;margin-top:8px");
      acts.innerHTML = '<button class="btn sm ghost" type="button" data-act="copy">复制</button>' +
        '<button class="btn sm ghost" type="button" data-act="save">保存到课程资料</button>';
      msg.appendChild(acts);
    }
    function realSend(text) {
      text = (text || "").trim(); if (!text) return;
      appendMsg("me", h(text));
      var thinking = appendMsg("ai", '<span class="spin"></span> 正在结合课程资料整理…');
      if (!Edu.isLive()) {
        setTimeout(function () { thinking.querySelector(".bubble").innerHTML = '<b>示例回复</b><br>静态演示：未连接本地接口，启动 api_server.py 后返回真实结果。'; }, 700);
        return;
      }
      var p = pid();
      API.assistant.chat({ prompt: text, project_id: p ? Number(p) : null }).then(function (res) {
        var out = (res && res.output) || "(无输出)";
        thinking.querySelector(".bubble").innerHTML = h(out).replace(/\n/g, "<br>");
        addActs(thinking);
        thinking.scrollIntoView({ behavior: "smooth", block: "end" });
      }).catch(function (err) { thinking.querySelector(".bubble").innerHTML = '<span style="color:var(--warn)">生成失败：' + h(err.message || err) + "</span>"; });
    }
    if (chat) chat.addEventListener("click", function (e) {
      var b = e.target.closest("[data-act]");
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      var msg = b.closest(".msg");
      var bubble = msg ? msg.querySelector(".bubble") : null;
      if (!bubble) return;
      var text = bubble.innerText || bubble.textContent || "";
      if (b.getAttribute("data-act") === "copy") {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { notify("已复制"); })
            .catch(function () { notify("复制失败"); });
        } else { notify("当前浏览器不支持复制"); }
        return;
      }
      if (!Edu.isLive()) { notify("未连接本地接口，无法保存"); return; }
      var p = pid();
      if (!p) { notify("请先选择课程"); return; }
      var firstLine = (text.split("\n").filter(function (s) { return s && s.trim(); })[0] || "")
        .replace(/^[#>*\-\s]+/, "").replace(/\*+/g, "").trim();
      var head = firstLine.split(/[：:]/)[0].trim();
      var title = (head.length >= 2 ? head : firstLine).slice(0, 24) || "AI 助手回答";
      busy(b, true, "保存中…");
      API.assistant.save({ project_id: Number(p), title: title, content: text })
        .then(function (r) { busy(b, false); notify("已保存为课程资料：" + (r.name || "")); })
        .catch(function (err) { busy(b, false); notify("保存失败：" + (err.message || err)); });
    });
    window.__eduSendAssistant = realSend;
    if (form) {
      form.addEventListener("submit", function (e) { e.preventDefault(); e.stopImmediatePropagation(); realSend(form.querySelector("textarea").value); form.querySelector("textarea").value = ""; });
      var ta = form.querySelector("textarea");
      if (ta) ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.dispatchEvent(new Event("submit")); } });
    }
    $all("[data-prompt]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); e.stopImmediatePropagation(); realSend(b.getAttribute("data-prompt")); });
    });
    // ?q= 自动发送（inline 脚本已被守卫跳过，这里统一处理）
    var q = new URLSearchParams(location.search).get("q");
    if (q) { if (Edu.isLive()) realSend(q); else setTimeout(function () { realSend(q); }, 0); }
  }

  /* ---------------- files ---------------- */
  function initFiles() {
    var form = $('form[data-sim="#fileOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid(); if (!p) { notify("请先选择课程"); return; }
      var fi = form.querySelector('input[type="file"]');
      var files = fi && fi.files ? Array.prototype.slice.call(fi.files) : [];
      if (!files.length) { notify("请选择文件"); return; }
      var sel = $all("select", form);
      var category = sel[0] ? sel[0].value : "资料";
      var visRaw = sel[1] ? sel[1].value : "师生可见";
      var visibility = visRaw.indexOf("教师") > -1 ? "teacher" : (visRaw.indexOf("学生") > -1 ? "student" : "both");
      var btn = form.querySelector('[type="submit"]');
      busy(btn, true, "上传解析中…");
      var chain = Promise.resolve();
      files.forEach(function (f) { chain = chain.then(function () { return API.files.upload({ projectId: Number(p), category: category, visibility: visibility, file: f }); }); });
      chain.then(function () { busy(btn, false); notify("已加入 " + files.length + " 个文件"); form.reset(); loadFiles(); })
        .catch(function (err) { busy(btn, false); notify("上传失败：" + (err.message || err)); });
    });
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-del-file]");
      if (b) { e.preventDefault(); if (!confirm("删除该资料？")) return; API.files.remove(b.getAttribute("data-del-file")).then(function () { notify("已删除"); loadFiles(); }).catch(function (err) { notify("删除失败：" + (err.message || err)); }); }
    });
    function parseInfo(f) {
      if (f.rows) return f.rows + " 行 × " + (f.cols || 0) + " 列";
      if (f.chars) return Number(f.chars).toLocaleString() + " 字";
      return "—";
    }
    function loadFiles() {
      var p = pid(); if (!p) return;
      API.files.list(p).then(function (files) {
        files = files || [];
        var tb = document.querySelectorAll("table tbody")[0];
        if (tb) {
          if (!files.length) { tb.innerHTML = '<tr><td colspan="7" class="mini">暂无资料，上传第一个文件。</td></tr>'; }
          else {
            tb.innerHTML = files.map(function (f) {
              var vis = f.visibility === "both" ? '<span class="tag acc">师生可见</span>' : (f.visibility === "student" ? '<span class="tag acc">学生可见</span>' : '<span class="tag warn">教师可见</span>');
              return '<tr><td>' + h(f.name) + '</td><td>' + h(f.category || f.ext || "") + '</td><td>' + fmtSize(f.size) + '</td><td>' + parseInfo(f) + '</td><td>' + vis + '</td><td>' + fmtTime(f.created_at) + '</td>' +
                '<td><button class="btn sm ghost" type="button" data-demo>预览</button> <button class="btn sm ghost" type="button" data-del-file="' + f.id + '">删除</button></td></tr>';
            }).join("");
          }
        }
        var totalChars = files.reduce(function (s, f) { return s + (Number(f.chars) || 0); }, 0);
        var totalSize = files.reduce(function (s, f) { return s + (Number(f.size) || 0); }, 0);
        setKpis(document, [
          { value: files.length, foot: "当前课程" },
          { value: totalChars.toLocaleString() + " 字", foot: "可用于备课检索" },
          { value: fmtSize(totalSize), foot: "仅保存在本机" }
        ]);
      }).catch(function () {});
    }
    onLive(loadFiles);
    // 页头「上传资料」按钮：直接选文件上传（默认师生可见、分类「资料」）
    var topUp = $all("button").filter(function (b) { return b.textContent.indexOf("上传资料") > -1 && !b.closest("form"); })[0];
    if (topUp) topUp.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid(); if (!p) { notify("请先选择课程"); return; }
      var input = document.createElement("input");
      input.type = "file"; input.multiple = true;
      input.accept = ".pdf,.docx,.doc,.pptx,.ppt,.md,.txt,.csv,.xlsx,.xls,.png,.jpg,.jpeg";
      input.onchange = function () {
        var files = Array.prototype.slice.call(input.files || []);
        if (!files.length) return;
        notify("上传解析中…");
        var chain = Promise.resolve();
        files.forEach(function (f) { chain = chain.then(function () { return API.files.upload({ projectId: Number(p), category: "资料", visibility: "both", file: f }); }); });
        chain.then(function () { notify("已加入 " + files.length + " 个文件"); loadFiles(); })
          .catch(function (err) { notify("上传失败：" + (err.message || err)); });
      };
      input.click();
    });
  }

  /* ---------------- tasks ---------------- */
  function initTasks() {
    function loadTasks() {
      var p = pid();
      API.tasks.list(p).then(function (rows) {
        rows = rows || [];
        setKpis(document, [
          { value: rows.filter(function (t) { return t.status === "doing"; }).length, foot: "进行中" },
          { value: rows.filter(function (t) { return t.status !== "ok" && t.status !== "doing"; }).length, foot: "待处理" },
          { value: rows.filter(function (t) { return t.status === "ok"; }).length, foot: "已完成" },
          { value: rows.length, foot: "累计任务" }
        ]);
        var tb = document.querySelectorAll("table tbody")[0];
        if (tb) {
          if (!rows.length) { tb.innerHTML = '<tr><td colspan="7" class="mini">暂无任务</td></tr>'; }
          else {
            tb.innerHTML = rows.slice(0, 50).map(function (t) {
              var st = t.status === "ok" ? '<span class="tag ok">已完成</span>' : (t.status === "doing" ? '<span class="tag ok">进行中</span>' : '<span class="tag warn">待处理</span>');
              var href = ({ lesson: "lesson.html", training: "training.html", review: "review.html", qa: "tutor.html" })[t.kind] || "tasks.html";
              return '<tr><td><b>' + h(t.prompt || "(无标题)") + '</b></td><td>' + kindLabel(t.kind) + '</td><td>' + h(courseName(t.project_id) || "—") + '</td><td>' + st + '</td>' +
                '<td style="min-width:150px"><div class="progress"><i style="width:' + (t.status === "ok" ? 100 : 60) + '%"></i></div></td><td>' + fmtTime(t.created_at) + '</td>' +
                '<td><a class="btn sm ghost" href="' + href + '">查看</a></td></tr>';
            }).join("");
          }
        }
        // 最近活动
        var acts = $("#recentActs");
        if (acts) {
          acts.innerHTML = rows.length ? rows.slice(0, 4).map(function (t) {
            return '<div class="list-item"><div class="li-ic">' + (KIND_IC[t.kind] || "•") + '</div><div style="flex:1"><div class="li-t">' + h(t.prompt || "") + '</div><div class="li-s">' + fmtTime(t.created_at) + ' · ' + kindLabel(t.kind) + '</div></div></div>';
          }).join("") : '<div class="mini" style="padding:6px 0">暂无数据</div>';
        }
        // 本周待办
        var todos = $("#weekTodos");
        if (todos) {
          var pending = rows.filter(function (t) { return t.status !== "ok"; }).slice(0, 5);
          todos.innerHTML = pending.length ? pending.map(function (t) { return '<div class="rule">' + h(kindLabel(t.kind) + "：" + (t.prompt || "")) + '</div>'; }).join("") : '<div class="rule">暂无待办，全部完成 🎉</div>';
        }
      }).catch(function () {});
    }
    onLive(loadTasks);
  }

  /* ---------------- settings ---------------- */
  function initSettings() {
    onLive(function () {
      API.settings.get().then(function (s) {
        var modelPane = $('[data-pane="model"]');
        if (!modelPane) return;
        var inputs = $all("input, select", modelPane);
        inputs.forEach(function (el) {
          var lab = (el.previousElementSibling && el.previousElementSibling.textContent) || "";
          if (lab.indexOf("Base URL") > -1 && s.llm_base_url) el.value = s.llm_base_url;
          else if (lab.indexOf("默认模型") > -1 && s.llm_model) { var o = document.createElement("option"); o.value = s.llm_model; o.textContent = s.llm_model; el.insertBefore(o, el.firstChild); el.value = s.llm_model; }
          else if (lab.indexOf("审核模型") > -1 && s.zhipu_model) { el.value = s.zhipu_model; }
          else if (lab.indexOf("API Key") > -1 && s.llm_api_key) { el.placeholder = "已设置（" + s.llm_api_key + "），留空不修改"; }
        });
      }).catch(function () {});
    });
    // 测试连接（保留按钮）；模型配置即时自动保存
    document.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      var b = e.target.closest("button"); if (!b) return;
      var txt = b.textContent || "";
      if (txt.indexOf("测试连接") > -1) {
        e.preventDefault(); e.stopImmediatePropagation(); busy(b, true, "连接中…");
        API.health().then(function (h) { busy(b, false); notify("连接成功：" + (h.model || "默认模型") + (h.llm_configured ? "" : "（未配置密钥）")); }).catch(function (err) { busy(b, false); notify("连接失败：" + (err.message || err)); });
      }
    });
    // 模型配置即时保存：select 立即、input 防抖 350ms
    var cfgTimer = null;
    var cfgSavedHint = null;
    function saveModelSettingsImmediate() {
      var pane = $('[data-pane="model"]'); if (!pane) return;
      var body = {};
      $all("input, select", pane).forEach(function (el) {
        var lab = (el.previousElementSibling && el.previousElementSibling.textContent) || "";
        if (!el.value) return;
        if (lab.indexOf("Base URL") > -1) body.llm_base_url = el.value;
        else if (lab.indexOf("默认模型") > -1) body.llm_model = el.value;
        else if (lab.indexOf("审核模型") > -1) body.zhipu_model = el.value;
        else if (lab.indexOf("API Key") > -1) body.llm_api_key = el.value;
        else if (lab.indexOf("温度") > -1) body.temperature = el.value;
        else if (lab.indexOf("核采样") > -1) body.top_p = el.value;
        else if (lab.indexOf("最大输出") > -1) body.max_tokens = el.value;
        else if (lab.indexOf("深度思考") > -1) body.thinking = el.value;
        else if (lab.indexOf("推理强度") > -1) body.reasoning_effort = el.value;
      });
      cfgSavedHint = cfgSavedHint || document.getElementById("cfgSaved");
      if (cfgSavedHint) cfgSavedHint.textContent = "保存中…";
      API.settings.save(body).then(function (r) {
        if (cfgSavedHint) { cfgSavedHint.textContent = "已保存 · " + new Date().toLocaleTimeString(); setTimeout(function () { if (cfgSavedHint) cfgSavedHint.textContent = ""; }, 1800); }
      }).catch(function () { if (cfgSavedHint) cfgSavedHint.textContent = ""; });
    }
    function bindModelAutoSave() {
      var pane = $('[data-pane="model"]'); if (!pane) return;
      $all("select", pane).forEach(function (el) {
        el.addEventListener("change", function () { if (Edu.isLive()) saveModelSettingsImmediate(); });
      });
      $all("input", pane).forEach(function (el) {
        el.addEventListener("input", function () {
          if (!Edu.isLive()) return;
          clearTimeout(cfgTimer);
          cfgTimer = setTimeout(saveModelSettingsImmediate, 350);
        });
        el.addEventListener("change", function () {
          if (!Edu.isLive()) return;
          clearTimeout(cfgTimer);
          saveModelSettingsImmediate();
        });
      });
    }
    bindModelAutoSave();

    // ---------------- 外观（本机持久化，即时生效） ----------------
    function prefs() { try { return JSON.parse(localStorage.getItem("edu.prefs") || "{}"); } catch (e) { return {}; } }
    function savePrefs(p) { try { localStorage.setItem("edu.prefs", JSON.stringify(p)); } catch (e) {} }
    function applyLook() {
      var dark = document.getElementById("lookDark");
      var font = document.getElementById("lookFont");
      var sidebar = document.getElementById("lookSidebar");
      var p = prefs();
      p.theme = dark && dark.checked ? "dark" : "light";
      p.fontSize = font && font.value.indexOf("紧凑") > -1 ? 12.5 : (font && font.value.indexOf("宽松") > -1 ? 14.5 : 13.5);
      p.sidebar = sidebar ? sidebar.value : "展开";
      savePrefs(p);
      if (window.Edu && Edu.applyPrefs) Edu.applyPrefs();
    }
    ["lookLight","lookDark","lookFont","lookSidebar"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("change", function () { if (Edu.isLive()) { applyLook(); notify("外观已更新"); } });
    });
    onLive(function () {
      var p = prefs();
      var ld = document.getElementById("lookDark"), ll = document.getElementById("lookLight");
      if (p.theme === "dark" && ld) { ld.checked = true; if (ll) ll.checked = false; }
      var lf = document.getElementById("lookFont");
      if (lf && p.fontSize) lf.value = p.fontSize === 12.5 ? "紧凑（12.5px）" : (p.fontSize === 14.5 ? "宽松（14.5px）" : "标准（13.5px）");
    });
    var ll2 = document.getElementById("lookLight"), ld2 = document.getElementById("lookDark");
    if (ll2 && ld2) {
      ll2.addEventListener("change", function () { if (ll2.checked) ld2.checked = false; });
      ld2.addEventListener("change", function () { if (ld2.checked) ll2.checked = false; });
    }

    // ---------------- 数据与隐私 ----------------
    var backupBtn = document.getElementById("backupBtn");
    if (backupBtn) backupBtn.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      window.open(API.maintenance.backupUrl());
      notify("正在打包下载备份");
    });
    var cleanBtn = document.getElementById("cleanBtn");
    if (cleanBtn) cleanBtn.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      busy(cleanBtn, true, "清理中…");
      API.maintenance.cleanup().then(function (r) {
        busy(cleanBtn, false);
        notify("已清理 " + r.removed + " 个临时文件，释放 " + fmtSize(r.freed));
      }).catch(function (err) { busy(cleanBtn, false); notify("清理失败：" + (err.message || err)); });
    });
    var resetBtn = document.getElementById("resetBtn");
    if (resetBtn) resetBtn.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!confirm("将删除全部课程、资料、任务与导出文件，且无法恢复。确定继续？")) return;
      busy(resetBtn, true, "删除中…");
      API.maintenance.reset().then(function () {
        busy(resetBtn, false);
        notify("已清空全部数据");
        setTimeout(function () { location.reload(); }, 800);
      }).catch(function (err) { busy(resetBtn, false); notify("删除失败：" + (err.message || err)); });
    });

    // ---------------- 高级设置（仅本机保存，即时） ----------------
    function saveAdvanced() {
      var p = prefs();
      p.advanced = {
        concurrency: (document.getElementById("advConcurrency") || {}).value,
        maxMB: (document.getElementById("advMaxMB") || {}).value,
        log: (document.getElementById("advLog") || {}).value,
        dual: !!(document.getElementById("advDual") || {}).checked,
        format: (document.getElementById("advFormat") || {}).value
      };
      savePrefs(p);
    }
    ["advConcurrency","advMaxMB","advLog","advDual","advFormat"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("change", function () { if (Edu.isLive()) { saveAdvanced(); notify("高级设置已更新"); } });
    });
  }

  /* ---------------- student ---------------- */
  function initStudent() {
    var form = $('form[data-sim="#stuAskOut"]');
    if (form) form.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var p = pid();
      var q = ($all("textarea", form)[0] || {}).value;
      if (!q || !q.trim()) { notify("请填写问题"); return; }
      var btn = form.querySelector('[type="submit"]');
      busy(btn, true, "生成中…");
      API.tutor.reply({ project_id: p ? Number(p) : null, question: q }).then(function (res) {
        busy(btn, false);
        var out = $("#stuAskOut"); if (out) { out.hidden = false; out.innerHTML = "<b>AI 提示：</b><br>" + h((res.reply || {}).feedback || ""); }
        notify("问题已提交");
      }).catch(function (err) { busy(btn, false); notify("失败：" + (err.message || err)); });
    });
    function renderStudent(d, wrong) {
      d = d || {};
      wrong = wrong || { items: [], total: 0, corrected: 0 };
      var myQa = d.my_qa || [], myRev = d.my_reviews || [],
          trains = d.trainings || [], lessons = d.lessons || [];
      setKpis(document, [
        { value: trains.length, foot: "实训任务" },
        { value: myRev.filter(function (r) { return r.status !== "published"; }).length, foot: "待阅读反馈" },
        { value: myRev.length ? Math.round(myRev.reduce(function (s, r) { return s + Number((r.meta || {}).final_total || 0); }, 0) / myRev.length) : 0, foot: "作业平均分" },
        { value: wrong.total || 0, foot: "已讲解 " + (wrong.corrected || 0) + " 题" }
      ]);
      // 顶部副文案：用真实计数替换写死的"2 个任务 / 1 条反馈"
      var heroP = document.querySelector("#studentHero p");
      if (heroP) {
        var c = (typeof Edu.getSelectedCourse === "function") ? Edu.getSelectedCourse() : null;
        var pendingCount = trains.concat(lessons).filter(function (t) { return t.status !== "ok"; }).length;
        heroP.textContent = (c && c.name ? c.name : "课程") + "。本周有 " + pendingCount + " 个任务待完成，" + myRev.length + " 条教师反馈。";
      }
      // 今日安排
      var homeStack = document.querySelector('[data-pane="home"] .stack');
      if (homeStack) {
        var todos = trains.concat(lessons).filter(function (t) { return t.status !== "ok"; }).slice(0, 3);
        if (!todos.length) homeStack.innerHTML = '<div class="list-item"><div class="li-ic">✓</div><div><div class="li-t">今日暂无待办</div><div class="li-s">所有任务已完成</div></div></div>';
        else homeStack.innerHTML = todos.map(function (t, i) {
          var meta = t.meta || {}; var title = (meta.pkg && meta.pkg.title) || t.prompt || "任务";
          return '<div class="list-item"><div class="li-ic">' + (i + 1) + '</div><div><div class="li-t">' + h(title) + '</div><div class="li-s">' + (t.kind === "training" ? "实训" : "备课") + " · " + (fmtTime(t.created_at) || "未排期") + '</div></div></div>';
        }).join("");
      }
      // 学习进度
      var homeBars = document.querySelector('[data-pane="home"] .bars');
      if (homeBars) {
        var all = trains.concat(lessons), done = all.filter(function (t) { return t.status === "ok"; }).length;
        renderBars(homeBars, [{ label: "任务完成", value: done, suffix: done + " / " + all.length + " 个" }]);
      }
      // 我的任务
      var taskTb = document.querySelector('[data-pane="tasks"] tbody');
      if (taskTb) {
        var taskRows = trains.concat(lessons).slice(0, 20);
        if (!taskRows.length) taskTb.innerHTML = '<tr><td colspan="5" class="mini">暂无任务</td></tr>';
        else taskTb.innerHTML = taskRows.map(function (t) {
          var isTrain = t.kind === "training";
          var meta = t.meta || {};
          var title = isTrain ? ((meta.pkg && meta.pkg.title) || t.prompt || "实训任务") : (t.prompt || "备课任务");
          var st = t.status === "ok" ? '<span class="tag ok">已完成</span>' : '<span class="tag warn">进行中</span>';
          return '<tr><td><b>' + h(title) + '</b></td><td>' + (isTrain ? "实训" : "备课") + '</td><td>' + (fmtTime(t.created_at) || "—") + '</td><td>' + st + '</td><td><button class="btn sm" type="button" data-demo="已打开任务">查看</button></td></tr>';
        }).join("");
      }
      // 我的提问
      var qaStack = document.querySelector('[data-pane="qa"] .stack');
      if (qaStack) {
        var items = [];
        myQa.forEach(function (t) { items.push({ q: t.prompt, ts: t.created_at, st: t.status === "ok" ? "已解决" : "进行中" }); });
        (d.tutor_threads || []).forEach(function (th) { items.push({ q: th.question, ts: th.ts, st: "AI 引导中" }); });
        if (!items.length) qaStack.innerHTML = '<div class="rule">暂无提问记录。</div>';
        else qaStack.innerHTML = items.slice(0, 10).map(function (it) {
          return '<div class="rule"><b>' + h(it.q || "(无问题)") + '</b><br><span class="mini">' + (fmtTime(it.ts) || "") + " · " + h(it.st) + '</span></div>';
        }).join("");
      }
      // 教师反馈
      var fbList = document.getElementById("fbList");
      if (fbList) {
        if (!myRev.length) fbList.innerHTML = '<div class="rule">暂无教师反馈。</div>';
        else fbList.innerHTML = myRev.map(function (r, i) {
          var meta = r.meta || {};
          var total = meta.final_total != null ? meta.final_total : ((meta.ai || {}).total);
          var unread = i === 0 ? "0" : "1";
          var comment = ((meta.ai || {}).comment) || ((meta.ai || {}).summary) || "见评分详情。";
          return '<div class="rule fb" tabindex="0" role="button" data-read="' + unread + '"><div class="fb-h"><b>' +
            h(r.prompt || "作业反馈") + (total != null ? " · " + total + " 分" : "") + '</b>' +
            (unread === "0" ? '<span class="tag acc fb-unread">未读</span>' : '<span class="tag fb-unread" hidden>未读</span>') +
            '</div><p class="mini" style="margin:6px 0 0">' + h(comment) + '</p></div>';
        }).join("");
        var fbCount = document.getElementById("fbCount");
        if (fbCount) fbCount.textContent = "共 " + myRev.length + " 条";
      }
      // 错题本：由真实评审低分维度与答疑错因派生
      var rvTb = document.getElementById("rvTbody");
      if (rvTb) {
        rvTb.innerHTML = (wrong.items || []).map(function (it) {
          var st = it.status === "已讲解" ? '<span class="tag ok">已讲解</span>' : '<span class="tag warn">待订正</span>';
          return '<tr><td>' + h(it.topic || "—") + '</td><td>' + h(it.knowledge_point || "—") + '</td><td>' + h(it.mastery || "—") + '</td>' +
            '<td class="wrap">' + h(it.last_error || "—") + '</td><td>' + st + '</td><td class="mini">—</td></tr>';
        }).join("") || '<tr><td colspan="6" class="mini">暂无错题记录。</td></tr>';
      }
      var rvCount = document.getElementById("rvCount");
      if (rvCount) rvCount.textContent = (wrong.total || 0) + " 题";
      var rvProgText = document.getElementById("rvProgText");
      if (rvProgText) rvProgText.textContent = (wrong.corrected || 0) + " / " + (wrong.total || 0) + " 题已订正";
      var rvProgBar = document.getElementById("rvProgBar");
      if (rvProgBar) rvProgBar.style.width = (wrong.total ? Math.round((wrong.corrected || 0) / wrong.total * 100) : 0) + "%";
    }
    onLive(function () {
      var p = pid();
      var stu = (window.EDU && window.EDU.student && window.EDU.student.name) || "";
      Promise.all([
        API.student.dashboard(p, stu),
        API.student.wrong(p, stu).catch(function () { return { items: [], total: 0, corrected: 0 }; })
      ]).then(function (res) { renderStudent(res[0], res[1]); }).catch(function () {});
    });
  }

  /* ---------------- tools ---------------- */
  function initTools() {
    bindBtn(document, "查看学情分析", function () { location.href = "analytics.html"; });
    bindBtn(document, "导出模板", function () { window.open(API.tools.rubricUrl("insight")); });
    bindBtn(document, "导出 Excel", function () {
      var p = pid();
      var c = (typeof Edu.getSelectedCourse === "function") ? Edu.getSelectedCourse() : null;
      window.open(API.tools.gradesUrl(p, c && (c.class_name || "")));
    });
    bindBtn(document, "分组", function (e, b) {
      var c = (typeof Edu.getSelectedCourse === "function") ? Edu.getSelectedCourse() : null;
      var n = Number((c && (c.class_size || c.classSize)) || 30);
      n = Math.max(2, Math.min(80, n));
      var size = 5, groups = Math.ceil(n / size), parts = [];
      for (var i = 0; i < groups; i++) {
        var a = i * size + 1, z = Math.min((i + 1) * size, n);
        parts.push("第" + (i + 1) + "组 " + a + (z > a ? "-" + z : "") + " 号");
      }
      var rule = b.closest(".rule");
      var res = rule && rule.querySelector(".groupRes");
      if (rule && !res) {
        res = document.createElement("div");
        res.className = "mini groupRes";
        res.style.marginTop = "6px";
        rule.appendChild(res);
      }
      if (res) res.textContent = "共 " + n + " 人，分 " + groups + " 组（每组约 " + size + " 人）：" + parts.join("；");
      notify("已按班级人数 " + n + " 分组");
    });
    // 其余按钮在 live 模式下仍无对应后端端点，保留轻提示
    document.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      var b = e.target.closest("[data-demo]"); if (!b) return;
      notify("该功能暂未接入后端");
    });
  }

  /* ---------------- 分发 ---------------- */
  var inits = {
    index: initIndex, courses: initCourses, lesson: initLesson, training: initTraining,
    tutor: initTutor, review: initReview, analytics: initAnalytics, assistant: initAssistant,
    files: initFiles, tasks: initTasks, settings: initSettings, student: initStudent, tools: initTools
  };
  try { (inits[page] || function () {})(); } catch (e) { console.error("[live init]", e); }

  /* Live 下：等 isLive 就绪（课程变更事件）后拉取真实模型名，替换全站写死的"智谱 GLM-4" */
  onLive(function () {
    API.health().then(function (h) { REAL_MODEL = (h && h.model) || null; applyRealModel(); }).catch(function () {});
  });
})();
