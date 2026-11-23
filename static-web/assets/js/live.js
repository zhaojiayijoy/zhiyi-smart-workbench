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
      API.files.list(p).then(function (files) {
        var tb = document.querySelectorAll("table tbody");
        var fileTbody = tb[1]; // 课程资料表
        if (!fileTbody) return;
        var rows = (files || []).slice(0, 6);
        if (!rows.length) { fileTbody.innerHTML = '<tr><td colspan="4" class="mini">暂无资料，去「课程资源」上传。</td></tr>'; return; }
        fileTbody.innerHTML = rows.map(function (f) {
          var vis = f.visibility === "both" || f.visibility === "student" ? '<span class="tag acc">师生</span>' : '<span class="tag warn">教师</span>';
          return '<tr><td>' + h(f.name) + '</td><td>' + h(f.category || f.ext || "") + '</td><td>' + vis + '</td><td>' + fmtTime(f.created_at) + '</td></tr>';
        }).join("");
      }).catch(function () {});
      API.tasks.list(p).then(function (tasks) {
        var host = document.querySelectorAll(".card-b.tight")[1]; // 关联记录容器
        if (!host) return;
        var rows = (tasks || []).slice(0, 4);
        if (!rows.length) { host.innerHTML = '<div class="mini">暂无关联记录。</div>'; return; }
        host.innerHTML = rows.map(function (t) {
          var href = ({ lesson: "lesson.html", training: "training.html", review: "review.html", qa: "tutor.html", nextlesson: "analytics.html" })[t.kind] || "tasks.html";
          return '<div class="list-item"><div class="li-ic">' + (KIND_IC[t.kind] || "•") + '</div><div style="flex:1"><div class="li-t">' +
            h(kindLabel(t.kind) + "：" + (t.prompt || "")) + '</div><div class="li-s">' + fmtTime(t.created_at) + '</div></div>' +
            '<a class="btn sm ghost" href="' + href + '">查看</a></div>';
        }).join("");
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

    var slides = (ppt.slides || []).map(function (s, i) {
      return '<div class="rule"><b>P' + (i + 1) + " " + h(s.title || "") + '</b><br>' +
        h((s.bullets || []).join("；")) + (s.notes ? '<div class="mini">讲稿：' + h(s.notes) + '</div>' : "") + '</div>';
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
    bindBtn(out, "通过审核并保存", function () { notify("已保存（后端暂无发布端点，本地记录保留）"); });
    bindBtn(out, "换一版", function () { notify("请修改上方参数后再次生成"); });
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
        if (el.type === "checkbox" && el.checked && el.parentElement.textContent.indexOf("双模型") < 0 && el.parentElement.textContent.indexOf("本次使用") < 0) {
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
      busy(btn, true, "生成中…");
      API.lesson.generate({ project_id: Number(p), topic: topic, lesson_type: lesson_type, hours: hours,
        student_level: student_level, style: style, extra: extra, outputs: outputs.length ? outputs : undefined,
        dual_check: dual })
        .then(function (res) { busy(btn, false); renderLesson(res.pkg, res.task_id); notify("备课包已生成"); })
        .catch(function (err) { busy(btn, false); var o = $("#lessonOut"); if (o) { o.hidden = false; o.querySelector(".card-b").innerHTML = '<div class="rule" style="color:var(--warn)">生成失败：' + h(err.message || err) + '</div>'; } notify("生成失败"); });
    });

    function loadHistory() {
      var p = pid(); if (!p) return;
      API.lesson.history(p).then(function (rows) {
        var tb = document.querySelectorAll("#packs table tbody")[0];
        if (!tb) return;
        if (!rows || !rows.length) { tb.innerHTML = '<tr><td colspan="6" class="mini">暂无备课包</td></tr>'; return; }
        tb.innerHTML = rows.map(function (r) {
          var pct = (r.checks && r.checks.consistency_pct);
          return '<tr><td>' + h(r.topic) + '</td><td>' + fmtTime(r.ts) + '</td><td>' + h(r.model || "") + '</td>' +
            '<td>' + (typeof pct === "number" ? pct + "%" : "—") + '</td><td><span class="tag">待审核</span></td>' +
            '<td><button class="btn sm" type="button" data-open-lesson="' + r.task_id + '">打开</button></td></tr>';
        }).join("");
      }).catch(function () {});
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-open-lesson]");
      if (b) { e.preventDefault(); var id = b.getAttribute("data-open-lesson"); API.lesson.get(id).then(function (pkg) { renderLesson(pkg, id); }).catch(function (err) { notify("打开失败：" + (err.message || err)); }); }
    });
    onLive(loadHistory);
  }

  /* ---------------- training ---------------- */
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
    bindBtn(out, "发布任务", function () { notify("已发布到学生空间（后端暂无发布端点）"); });
    bindBtn(out, "保存草稿", function () { notify("已保存为草稿"); });
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
        var tb = document.querySelectorAll("#taskList table tbody")[0];
        if (!tb) return;
        if (!rows || !rows.length) { tb.innerHTML = '<tr><td colspan="6" class="mini">暂无实训任务</td></tr>'; return; }
        tb.innerHTML = rows.map(function (r) {
          return '<tr><td><b>' + h(r.scenario) + '</b></td><td><span class="tag">草稿</span></td><td>100</td><td>—</td><td>' + fmtTime(r.ts) + '</td>' +
            '<td><button class="btn sm" type="button" data-open-train="' + r.task_id + '">查看</button></td></tr>';
        }).join("");
      }).catch(function () {});
    }
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-open-train]");
      if (b) { var id = b.getAttribute("data-open-train"); API.training.get(id).then(function (pkg) { renderTraining(pkg, id); }).catch(function (err) { notify("打开失败：" + (err.message || err)); }); }
    });
    onLive(loadHistory);
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
        var tb = document.querySelectorAll("table tbody")[0];
        if (!tb) return;
        var rows = threads.slice(0, 8);
        if (!rows.length) { tb.innerHTML = '<tr><td colspan="7" class="mini">暂无答疑记录</td></tr>'; return; }
        tb.innerHTML = rows.map(function (r) {
          return '<tr><td>' + h(r.question) + '</td><td>—</td><td>—</td><td><span class="tag acc">AI 引导中</span></td><td><span class="tag acc">师生可见</span></td><td>' + fmtTime(r.ts) + '</td><td><button class="btn sm" type="button" data-demo>打开</button></td></tr>';
        }).join("");
      }).catch(function () {});
    }
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
        busy(btn, true, "评审中…");
        API.review.evaluate({ project_id: p ? Number(p) : null, submission_text: text, file_name: name || "学生提交", student: student })
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
    var finalForm = $('form[data-sim="#finalOut"]');
    if (finalForm) finalForm.addEventListener("submit", function (e) {
      if (!Edu.isLive()) return;
      e.preventDefault(); e.stopImmediatePropagation();
      var out = $("#finalOut"); if (out) { out.hidden = false; out.textContent = "教师终评已记录（后端暂无终评发布端点，结果保留在当前会话）。"; }
      notify("终评已保存");
    });

    function renderReview(review, taskId, student, name) {
      var dims = review.dimensions || [];
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
    function loadHistory() {
      var p = pid();
      API.review.history(p).then(function (rows) {
        var tb = document.querySelectorAll("table tbody")[0];
        if (!tb || !rows || !rows.length) return;
        tb.innerHTML = rows.map(function (r) {
          return '<tr><td><b>' + h(r.student || "学生") + '</b></td><td>' + h(r.file_name || "") + '</td><td>' + h(r.total) + '</td><td><span class="tag warn">待复核</span></td></tr>';
        }).join("");
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

    function loadAggregate() {
      var p = pid(); if (!p) return;
      busy(applyBtn, true, "分析中…");
      API.analytics.aggregate({ project_id: Number(p) }).then(function (a) {
        busy(applyBtn, false);
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
        loadNext(a);
      }).catch(function (err) { busy(applyBtn, false); notify("分析失败：" + (err.message || err)); });
    }
    function loadNext(a) {
      var p = pid(); if (!p) return;
      var host = document.querySelectorAll(".split .card .card-b .stack")[0]; // 下一课方案
      if (!host) return;
      host.innerHTML = '<div class="mini">正在生成下一课方案…</div>';
      API.analytics.next({ project_id: Number(p) }).then(function (res) {
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
    function appendMsg(role, html) {
      if (!chat) return;
      var d = document.createElement("div"); d.className = "msg " + (role === "me" ? "me" : "ai");
      d.innerHTML = '<div class="who">' + (role === "me" ? "李" : "AI") + '</div><div class="bubble">' + html + '</div>';
      chat.appendChild(d); d.scrollIntoView({ behavior: "smooth", block: "end" }); return d;
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
        thinking.scrollIntoView({ behavior: "smooth", block: "end" });
      }).catch(function (err) { thinking.querySelector(".bubble").innerHTML = '<span style="color:var(--warn)">生成失败：' + h(err.message || err) + "</span>"; });
    }
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
        var acts = document.querySelectorAll(".card-b.tight .list-item");
        if (acts.length && acts[0].parentNode) {
          acts[0].parentNode.innerHTML = rows.slice(0, 4).map(function (t) {
            return '<div class="list-item"><div class="li-ic">' + (KIND_IC[t.kind] || "•") + '</div><div style="flex:1"><div class="li-t">' + h(t.prompt || "") + '</div><div class="li-s">' + fmtTime(t.created_at) + ' · ' + kindLabel(t.kind) + '</div></div></div>';
          }).join("");
        }
        // 本周待办
        var todos = document.querySelectorAll(".card .stack .rule");
        if (todos.length && todos[0].parentNode) {
          var pending = rows.filter(function (t) { return t.status !== "ok"; }).slice(0, 5);
          todos[0].parentNode.innerHTML = pending.length ? pending.map(function (t) { return '<div class="rule">' + h(kindLabel(t.kind) + "：" + (t.prompt || "")) + '</div>'; }).join("") : '<div class="rule">暂无待办，全部完成 🎉</div>';
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
    // 保存 / 测试连接（data-demo，live 模式 site.js 已跳过 toast）
    document.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      var b = e.target.closest("button"); if (!b) return;
      var txt = b.textContent || "";
      if (txt.indexOf("测试连接") > -1) {
        e.preventDefault(); e.stopImmediatePropagation(); busy(b, true, "连接中…");
        API.health().then(function (h) { busy(b, false); notify("连接成功：" + (h.model || "默认模型") + (h.llm_configured ? "" : "（未配置密钥）")); }).catch(function (err) { busy(b, false); notify("连接失败：" + (err.message || err)); });
      } else if (txt.indexOf("保存") > -1 && txt.indexOf("模型") > -1) {
        e.preventDefault(); e.stopImmediatePropagation(); saveModelSettings(b);
      }
    });
    function saveModelSettings(btn) {
      var pane = $('[data-pane="model"]'); if (!pane) return;
      var body = {};
      $all("input, select", pane).forEach(function (el) {
        var lab = (el.previousElementSibling && el.previousElementSibling.textContent) || "";
        if (!el.value) return;
        if (lab.indexOf("Base URL") > -1) body.llm_base_url = el.value;
        else if (lab.indexOf("默认模型") > -1) body.llm_model = el.value;
        else if (lab.indexOf("审核模型") > -1) body.zhipu_model = el.value;
        else if (lab.indexOf("API Key") > -1) body.llm_api_key = el.value;
      });
      busy(btn, true, "保存中…");
      API.settings.save(body).then(function (r) { busy(btn, false); notify("已保存并热生效：" + (r.updated || []).join("、")); }).catch(function (err) { busy(btn, false); notify("保存失败：" + (err.message || err)); });
    }
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
    onLive(function () {
      var p = pid();
      var stu = (window.EDU && window.EDU.student && window.EDU.student.name) || "陈思远";
      API.student.dashboard(p, stu).then(function (d) {
        var myQa = d.my_qa || [], myRev = d.my_reviews || [], trains = d.trainings || [];
        setKpis(document, [
          { value: trains.length, foot: "实训任务" },
          { value: myRev.filter(function (r) { return r.status !== "published"; }).length, foot: "待阅读反馈" },
          { value: myRev.length ? Math.round(myRev.reduce(function (s, r) { return s + Number((r.meta || {}).final_total || 0); }, 0) / myRev.length) : 0, foot: "作业平均分" },
          { value: myQa.length, foot: "答疑记录" }
        ]);
      }).catch(function () {});
    });
  }

  /* ---------------- tools ---------------- */
  function initTools() {
    bindBtn(document, "查看学情分析", function () { location.href = "analytics.html"; });
    // 其余导出按钮在 live 模式下无对应后端端点，保留演示提示（site.js 已在非 live 弹 toast；live 下静默，补一个轻提示）
    document.addEventListener("click", function (e) {
      if (!Edu.isLive()) return;
      var b = e.target.closest("[data-demo]"); if (!b) return;
      notify("演示功能：后端暂未提供该批量导出端点");
    });
  }

  /* ---------------- 分发 ---------------- */
  var inits = {
    index: initIndex, courses: initCourses, lesson: initLesson, training: initTraining,
    tutor: initTutor, review: initReview, analytics: initAnalytics, assistant: initAssistant,
    files: initFiles, tasks: initTasks, settings: initSettings, student: initStudent, tools: initTools
  };
  try { (inits[page] || function () {})(); } catch (e) { console.error("[live init]", e); }
})();
