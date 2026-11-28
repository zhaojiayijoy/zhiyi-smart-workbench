/* ============= AI 课堂预演 前端逻辑 ============= */
(function(){
  "use strict";
  const API = window.EduAPI;
  function h(value){
    return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  }

  const PERSONAS = [
    { id: "novice",     name: "基础薄弱型", avatar: "基", color: "#7A9C88", desc: "跟不上讲解、混淆前置概念、练习中误用概念" },
    { id: "challenger", name: "深度追问型", avatar: "深", color: "#B9885C", desc: "追问概念边界、提出延伸问题、挑战案例成立性" },
    { id: "operator",   name: "操作不熟练型", avatar: "操", color: "#798CA0", desc: "Excel慢、不清楚Word/PPT交付要求、实训漏字段格式" },
  ];

  function $(sel){ return document.querySelector(sel); }
  function $all(sel){ return Array.from(document.querySelectorAll(sel)); }
  function notify(msg){ if (window.EduAPI && EduAPI.notify) EduAPI.notify(msg); else toast(msg); }
  function toast(msg){
    const t = document.querySelector(".toast"); if (!t) return;
    t.textContent = msg; t.classList.add("on");
    clearTimeout(toast._tm); toast._tm = setTimeout(()=>t.classList.remove("on"), 2500);
  }

  let currentRehearsalId = null;
  let selectedPersonas = new Set(["novice","challenger","operator"]);
  let viewVersion = 0;
  let detailVersion = 0;

  function selectedCourse(){
    return window.Edu && Edu.getSelectedCourse ? Edu.getSelectedCourse() : null;
  }

  function isCurrent(courseId, version){
    const course = selectedCourse();
    return version === viewVersion && String(course && course.id) === String(courseId);
  }

  function initPersonas(){
    const box = $("#rhPersonas"); if (!box) return;
    box.innerHTML = PERSONAS.map(p => {
      const on = selectedPersonas.has(p.id);
      return `<div class="rh-persona ${on?'on':''}" data-pid="${p.id}">
        <div class="avatar" style="background:${p.color}">${p.avatar}</div>
        <div>
          <div class="label">${p.name}</div>
          <div class="desc">${p.desc}</div>
        </div>
      </div>`;
    }).join("");
    $all("#rhPersonas .rh-persona").forEach(el => {
      el.addEventListener("click", () => {
        const pid = el.dataset.pid;
        if (selectedPersonas.has(pid)) selectedPersonas.delete(pid);
        else selectedPersonas.add(pid);
        initPersonas();
      });
    });
  }

  async function initPage(){
    if (!API || !window.Edu || !Edu.isLive()) return;
    const version = ++viewVersion;
    ++detailVersion;
    const c = selectedCourse();
    const courseId = c && c.id;
    currentRehearsalId = null;
    renderSession({});
    $("#rhProgressWrap").style.display = "none";
    $("#rhHistory").innerHTML = "";
    $("#rhLessonPkg").textContent = "尚未生成";
    initPersonas();
    // 显示当前课程
    if (window.Edu && Edu.getSelectedCourse){
      $("#rhCourseName").textContent = c ? `${c.name} · ${c.class||"未分班"}` : "请先选择课程";
    }
    // 显示最新备课包
    try {
      const lessons = c ? await API.tasks.list(c.id, "lesson") : [];
      if (!isCurrent(courseId, version)) return;
      if (lessons && lessons.length){
        const first = lessons[0];
        $("#rhLessonPkg").textContent = first.prompt ? first.prompt.slice(0,50) + "…" : "最新备课包";
      } else $("#rhLessonPkg").textContent = "尚未生成";
    } catch(e){ if (!isCurrent(courseId, version)) return; $("#rhLessonPkg").textContent = "尚未生成"; }
    // 加载历史
    const latest = await loadHistory();
    // 加载未完成/最近一次预演详情
    if (latest && isCurrent(courseId, version)) await openRehearsal(latest);
  }

  async function loadHistory(){
    const box = $("#rhHistory"); if (!box) return;
    const c = window.Edu && Edu.getSelectedCourse ? Edu.getSelectedCourse() : null;
    const version = viewVersion;
    if (!c){ box.innerHTML = '<div class="mini" style="color:var(--text-3)">请先选择课程</div>'; return; }
    try {
      const list = await API.rehearsals.list(c.id);
      if (!isCurrent(c.id, version)) return;
      if (!list.ok || !list.items.length){ box.innerHTML = '<div class="mini" style="color:var(--text-3)">暂无预演记录</div>'; return; }
      box.innerHTML = list.items.map(r => {
        const time = new Date(r.created_at*1000);
        const m = String(time.getMinutes()).padStart(2,"0");
        const timeStr = `${time.getMonth()+1}/${time.getDate()} ${time.getHours()}:${m}`;
        const rk = (r.summary||{}).riskCount || 0;
        const hk = (r.summary||{}).highRiskCount || 0;
        const tag = r.is_demo ? "演示" : (r.status === "completed" ? "已完成" : (r.status === "running" ? "运行中" : "失败"));
        return `<div class="rh-history-item" data-rid="${r.id}">
          <span class="time">${timeStr}</span>
          <div class="sum"><b>${hk}</b> 高风险 · <b>${rk}</b> 总风险 · ${tag}</div>
        </div>`;
      }).join("");
      $all("#rhHistory .rh-history-item").forEach(el => {
        el.addEventListener("click", () => openRehearsal(parseInt(el.dataset.rid)).catch(e => notify(e.message)));
      });
      return list.items[0].id;
    } catch(e){ if (isCurrent(c.id, version)) box.innerHTML = '<div class="mini" style="color:#D98F7A">加载失败</div>'; }
  }

  async function openRehearsal(rid){
    const c = selectedCourse();
    const version = viewVersion;
    const requestVersion = ++detailVersion;
    const r = await API.rehearsals.get(rid);
    if (!c || !isCurrent(c.id, version) || requestVersion !== detailVersion) return;
    if (!r.ok) return notify("预演记录不存在");
    if (String(r.item.course_id) !== String(c.id)) return;
    currentRehearsalId = rid;
    renderSession(r.item);
    return r.item;
  }

  function renderSession(s){
    $("#rhMock").style.display = s.is_demo ? "" : "none";
    $("#rhMode").textContent = s.is_demo ? "演示预演" : (s.review_model ? "双模型预演" : "单模型预演");
    // 顶部状态
    const stageCount = (s.timeline||[]).length;
    $("#rhStageCount").textContent = `${stageCount} 个阶段 · 共 ${(s.timeline||[]).reduce((a,b)=>a+(b.minutes||0),0)} 分钟`;
    // 进度
    renderProgress(s);
    // 时间轴
    renderTimeline(s);
    // 风险
    renderRisks(s);
    // 修补
    renderPatches(s);
  }

  function renderProgress(s){
    const wrap = $("#rhProgressWrap");
    const fail = $("#rhFail");
    const stepsBox = $("#rhPsteps");
    const fill = $("#rhProgFill");
    if (s.status === "configuring"){
      wrap.style.display = "none";
      return;
    }
    wrap.style.display = "block";
    if (s.status === "failed"){
      fail.style.display = "block";
      fail.textContent = `运行失败：${s.error || "未知错误"}`;
      fill.style.width = "30%";
      stepsBox.innerHTML = `<div class="pstep done">1. 读取资料</div><div class="pstep">2. 学生画像</div><div class="pstep">3. 模拟反应</div>`;
      return;
    }
    fail.style.display = "none";
    const steps = [
      { t: "读取资料", done: !!s.timeline && s.timeline.length },
      { t: "学生画像", done: (s.personas||[]).length > 0 },
      { t: "模拟反应", done: !!s.events && s.events.length > 0 },
      { t: "风险检查", done: !!s.risks && s.risks.length > 0 },
      { t: "生成修补", done: !!s.patches && s.patches.length > 0 },
    ];
    if (s.status === "completed") steps.forEach(step => { step.done = true; });
    const doneN = steps.filter(x=>x.done).length;
    const cur = steps.findIndex(x=>!x.done);
    stepsBox.innerHTML = steps.map((st,i)=>{
      let cls = "";
      if (st.done) cls = "done";
      else if (i === cur) cls = "cur";
      return `<div class="pstep ${cls}">${i+1}. ${st.t}</div>`;
    }).join("");
    fill.style.width = `${Math.round(doneN/steps.length*100)}%`;
    if (s.status === "running") fill.style.width = Math.max(fill.style.width.replace("%","")*1, 20) + "%";
  }

  function renderTimeline(s){
    const box = $("#rhTimeline");
    const empty = $("#rhTimelineEmpty");
    const tl = s.timeline || [];
    if (!tl.length){ box.innerHTML=""; empty.style.display="block"; return; }
    empty.style.display = "none";
    const eventsByStage = {};
    (s.events||[]).forEach(e => {
      (eventsByStage[e.stageId] = eventsByStage[e.stageId] || []).push(e);
    });
    const personaMap = {}; PERSONAS.forEach(p=>personaMap[p.id]=p);
    box.innerHTML = tl.map(stage => {
      const evs = eventsByStage[stage.stageId] || [];
      return `<div class="rh-stage">
        <div class="rh-stage-head">
          <span class="rh-stage-name">${h(stage.name)}</span>
          <span class="rh-stage-min">${h(stage.minutes||5)} 分钟</span>
        </div>
        ${stage.objective ? `<div class="rh-stage-obj">目标：${h(stage.objective)}</div>` : ""}
        ${evs.length ? evs.map(e => {
          const p = personaMap[e.personaId] || { name: "?", color: "#8FA094" };
          const etag = ({question:"提问",misconception:"误解",operation_block:"操作卡点",disengagement:"走神",challenge:"追问",time_risk:"时间风险"})[e.eventType] || "事件";
          return `<div class="rh-event">
            <div class="rh-event-head">
              <span class="pchip" style="background:${p.color}22;color:${p.color};border:1px solid ${p.color}44">${p.name}</span>
              <span class="etag">${etag}</span>
            </div>
            <q>${h(e.content)}</q>
            <div class="ev"><b>证据</b>：${h(e.evidence||"来自模型推断")}</div>
            <div class="ev"><b>影响</b>：${h(e.teacherRisk||"—")}</div>
            <div class="resp">建议回应：${h(e.suggestedResponse||"—")}</div>
          </div>`;
        }).join("") : `<div class="mini" style="color:var(--text-3)">本阶段暂无模拟事件</div>`}
      </div>`;
    }).join("");
  }

  function renderRisks(s){
    const box = $("#rhRisks");
    const empty = $("#rhEmpty");
    const sum = $("#rhSum");
    const risks = s.risks || [];
    if (!risks.length){ box.style.display="none"; empty.style.display="block"; sum.innerHTML=""; return; }
    empty.style.display = "none"; box.style.display="block";
    const high = risks.filter(r=>r.level==="high").length;
    const med = risks.filter(r=>r.level==="medium").length;
    const low = risks.filter(r=>r.level==="low").length;
    sum.innerHTML = `
      <div class="rh-sum-chip"><b>${risks.length}</b> 总风险</div>
      ${high ? `<div class="rh-sum-chip high"><b>${high}</b> 高风险</div>` : ""}
      ${med ? `<div class="rh-sum-chip med"><b>${med}</b> 中风险</div>` : ""}
      ${low ? `<div class="rh-sum-chip"><b>${low}</b> 低风险</div>` : ""}
      ${s.summary && s.summary.topWeakKnowledgePoint ? `<div class="rh-sum-chip">最易误解：${h(s.summary.topWeakKnowledgePoint)}</div>` : ""}
      ${s.summary && s.summary.largestTimeRiskStage ? `<div class="rh-sum-chip">时间压力：${h(s.summary.largestTimeRiskStage)}</div>` : ""}
    `;
    box.innerHTML = risks.map(r => {
      const levelClass = r.level === "high" ? "high" : (r.level === "medium" ? "medium" : "low");
      const patches = r.patches || [];
      return `<div class="rh-risk">
        <div class="rh-risk-head">
          <span class="rh-risk-level ${levelClass}">${h(({high:"高",medium:"中",low:"低"})[r.level] || r.level)}</span>
          <span class="rh-risk-title">${h(r.title)}</span>
        </div>
        <div class="rh-risk-meta"><b>类型</b>：${h(({knowledge_misconception:"知识误解",teaching_time:"教学时间",objective_coverage:"目标覆盖",activity_participation:"活动参与",training_executability:"实训可执行性",rubric_consistency:"评分标准一致性"})[r.type] || r.type)} · <b>证据</b>：${h(r.evidence || "—")} · <b>影响</b>：${h(r.impact || "—")}</div>
        <div class="rh-risk-patches">
          ${patches.map(pid => `<button class="rh-risk-patch-btn" data-pid="${h(pid)}">关联修补 · ${h(pid)}</button>`).join("")}
        </div>
      </div>`;
    }).join("");
    // 点击跳转到修补
    $all(".rh-risk-patch-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const pid = btn.dataset.pid;
        $all(".rh-patch").forEach(p => {
          if (p.dataset.patchId === pid){ p.scrollIntoView({behavior:"smooth",block:"center"}); p.classList.add("on"); }
          else p.classList.remove("on");
        });
      });
    });
  }

  function renderPatches(s){
    const box = $("#rhPatches"); if (!box) return;
    const patches = s.patches || [];
    if (!patches.length){ box.innerHTML = '<div class="mini" style="color:var(--text-3)">暂无修补方案</div>'; return; }
    const artMap = {lesson_plan:"教案",ppt:"PPT大纲",exercise:"课堂练习",training_task:"实训任务要求",rubric:"评分量规"};
    box.innerHTML = patches.map(p => {
      const applied = p.status === "applied";
      const rejected = p.status === "rejected";
      const stClass = applied ? "applied" : (rejected ? "rejected" : "");
      const stText = applied ? "已应用" : (rejected ? "已拒绝" : "待处理");
      const canApply = !s.is_demo && !applied && !rejected;
      const canUndo = applied;
      const canReject = !applied && !rejected;
      return `<div class="rh-patch" data-patch-id="${h(p.patchId)}">
        <div class="rh-patch-head">
          <span class="rh-patch-art">${h(artMap[p.targetArtifact] || p.targetArtifact)} · ${h(p.targetSection||"")}</span>
          <span class="rh-patch-status ${stClass}">${stText}</span>
        </div>
        <div class="rh-patch-reason"><b>为什么需要改：</b>${h(p.reason||"")}</div>
        <div class="rh-patch-before"><b>改前：</b>${h(p.before||"—")}</div>
        <div class="rh-patch-after"><b>改后：</b>${h(p.after||"—")}</div>
        <div class="rh-patch-actions">
          ${canApply ? `<button class="primary" data-action="apply" data-patch="${h(p.patchId)}">应用修改</button>` : ""}
          ${canReject ? `<button data-action="reject" data-patch="${h(p.patchId)}">暂不修改</button>` : ""}
          ${canUndo ? `<button data-action="undo" data-patch="${h(p.patchId)}">撤销本次修改</button>` : ""}
        </div>
      </div>`;
    }).join("");
    // 事件绑定
    box.onclick = async (e) => {
      const btn = e.target.closest("button[data-action]"); if (!btn) return;
      const action = btn.dataset.action, pid = btn.dataset.patch;
      const rid = currentRehearsalId, version = viewVersion;
      const course = selectedCourse();
      btn.disabled = true;
      try {
        const resp = await API.rehearsals.patch(rid, pid, action);
        if (!course || !isCurrent(course.id, version) || currentRehearsalId !== rid) return;
        if (resp.ok){
          notify(action === "apply" ? "已生成备课包 v2 草稿" : (action === "reject" ? "已拒绝" : "已撤销"));
          renderSession(resp.session);
          await loadHistory();
        } else { notify("操作失败"); btn.disabled = false; }
      } catch(err){ notify("网络错误："+err.message); btn.disabled=false; }
    };
  }

  async function runRehearsal(){
    const c = window.Edu && Edu.getSelectedCourse ? Edu.getSelectedCourse() : null;
    if (!c) return notify("请先选择课程");
    if (!selectedPersonas.size) return notify("请至少选择一位模拟学生");
    const version = viewVersion;

    $("#rhRun").disabled = true; $("#rhDemo").disabled = true;
    $("#rhRun").textContent = "正在预演…";

    try {
      const lessons = await API.tasks.list(c.id, "lesson");
      const first = lessons && lessons.length ? lessons[0] : null;
      const body = { courseId: c.id, personas: Array.from(selectedPersonas), useReviewModel: $("#rhDual").checked };
      if (first) body.lessonPackageId = first.id;

      const resp = await API.rehearsals.create(body);
      if (!isCurrent(c.id, version)) return;
      if (resp.ok){
        const result = await openRehearsal(resp.id);
        if (!isCurrent(c.id, version)) return;
        await loadHistory();
        if (!result || !isCurrent(c.id, version)) return;
        notify(result.status === "failed" ? "预演失败" : (result.is_demo ? "已回退为演示预演，未生成真实分析" : "预演完成"));
      } else { notify("预演失败："+(resp.error||"")); }
    } catch(err){ notify("网络错误："+err.message); }
    finally {
      $("#rhRun").disabled = false; $("#rhDemo").disabled = false;
      $("#rhRun").textContent = "开始预演";
    }
  }

  async function runDemo(){
    const c = window.Edu && Edu.getSelectedCourse ? Edu.getSelectedCourse() : null;
    if (!c) return notify("请先选择课程");
    const version = viewVersion;
    $("#rhDemo").disabled = true; $("#rhRun").disabled = true;
    $("#rhDemo").textContent = "生成演示中…";
    try {
      const resp = await API.rehearsals.demo({ courseId: c.id, personas: Array.from(selectedPersonas) });
      if (!isCurrent(c.id, version)) return;
      if (resp.ok){
        await openRehearsal(resp.id);
        if (!isCurrent(c.id, version)) return;
        await loadHistory();
        if (isCurrent(c.id, version)) notify("演示预演已生成");
      }
    } catch(e){ notify("演示生成失败："+e.message); }
    finally {
      $("#rhDemo").disabled = false; $("#rhRun").disabled = false;
      $("#rhDemo").textContent = "快速体验演示预演";
    }
  }

  // 事件绑定
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("button"); if (!btn) return;
    if (btn.id === "rhRun") runRehearsal();
    else if (btn.id === "rhDemo") runDemo();
  });

  if (window.Edu){
    Edu.onCourseChange(() => initPage().catch(e => notify(e.message)));
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => initPage().catch(e => notify(e.message)), {once: true});
    else initPage().catch(e => notify(e.message));
  } else {
    initPage();
  }
})();
