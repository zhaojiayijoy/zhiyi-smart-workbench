"""教育模式六个核心功能的界面层（课程闭环）。

页面入口（由 streamlit_app.py 调用）：
- render_course_page      课程驾驶舱（资料 + 统计 + 关联记录）
- render_lesson_page      一键备课包
- render_tutor_page       引导式答疑（教师记录 / 学生我的答疑）
- render_training_page    实训任务
- render_review_page      作业评审与教师复核
- render_analytics_page   学情回流与下一课

所有数据来自 SQLite；生成能力来自 app.edu（真实模型调用），
失败时如实报错，不伪造成功结果。
"""
from __future__ import annotations

import html
import json
import time
from pathlib import Path
from typing import Any

import streamlit as st

from app import db, edu
from app.config import PROJECT_DIR, ROOT

ss = st.session_state

_VIS_OPTIONS = ["教师可见", "学生可见", "师生可见"]
_VIS_MAP = {"教师可见": "teacher", "学生可见": "student", "师生可见": "both"}
_VIS_BADGE = {"teacher": ("教师可见", "warn"), "student": ("学生可见", "ok"), "both": ("师生可见", "acc")}
_STATUS_LABEL = {
    "ai": "AI引导中", "waiting": "等待学生尝试", "solved": "已解决",
    "teacher": "教师接管", "attention": "需要关注",
}
_REVIEW_STATUS = {"published": "已发布", "returned": "退回修改", "manual": "需人工检查",
                  "pending": "待复核"}
_TRAIN_STATUS = {"draft": "草稿", "published": "已发布", "closed": "已截止"}


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------
def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _proj() -> dict[str, Any] | None:
    pid = ss.get("current_project_id")
    return db.get_project(int(pid)) if pid else None


def _folder(proj: dict[str, Any] | None) -> Path:
    if proj and (proj.get("folder") or "").strip():
        p = Path(proj["folder"])
    elif proj:
        bad = '<>:"/\\|?*'
        name = "".join("_" if ch in bad else ch for ch in proj["name"]).strip() or "course"
        p = PROJECT_DIR / name
    else:
        p = ROOT / ".data" / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_student_mode() -> bool:
    return ss.get("edu_mode", "教师模式") == "学生模式"


def student_name() -> str:
    return (ss.get("edu_student_name") or "").strip()


def _last_course() -> dict[str, Any] | None:
    """最近一次使用过的课程：优先 session 记录，其次最近创建的项目。"""
    lid = ss.get("last_course_id") or ss.get("current_project_id")
    if lid:
        try:
            p = db.get_project(int(lid))
        except (TypeError, ValueError):
            p = None
        if p:
            return p
    projects = [p for p in db.list_projects() if p["name"] != "默认项目"]
    return projects[0] if projects else None


def render_course_required() -> None:
    """统一的「未选择课程」空状态：图标 + 标题 + 说明 + 两个真实按钮。"""
    st.html(
        '<div class="fm-crs-empty">'
        '<div class="ic">📘</div>'
        '<h3>还没有选择课程</h3>'
        '<p>课程是备课、答疑、实训和学情分析共同使用的上下文。</p>'
        "</div>"
    )
    recent = _last_course()
    c1, c2, c3 = st.columns([1.1, 1.1, 2.4])
    with c1:
        if st.button("创建课程项目", key="edu_need_new", use_container_width=True):
            ss["edu_open_new"] = True
            ss.nav = "课程项目"
            st.rerun()
    with c2:
        if st.button("选择已有课程", key="edu_need_pick", use_container_width=True):
            ss.nav = "课程项目"
            st.rerun()
    with c3:
        if recent:
            st.html(
                '<div style="font-size:12.5px;color:var(--text-3);padding-top:4px">'
                f'最近使用过：<b style="color:var(--text-2)">{_esc(recent["name"])}</b></div>'
            )
            if st.button(f"继续使用「{recent['name']}」", key="edu_need_recent",
                         use_container_width=True):
                ss.current_project_id = recent["id"]
                ss.current_project_name = recent["name"]
                ss["last_course_id"] = recent["id"]
                ss["last_course_name"] = recent["name"]
                st.query_params["course"] = str(recent["id"])
                st.rerun()


def render_course_summary(proj: dict[str, Any]) -> None:
    """教学页面顶部的课程摘要（课程 / 班级 / 课时 / 进度 / 资料数）。"""
    ov = db.course_overview(proj["id"])
    class_name = proj.get("class_name") or proj.get("audience") or "未填写班级"
    hours = proj.get("hours") or "未填写课时"
    progress = proj.get("progress") or "未填写进度"
    st.html(
        '<div class="fm-ctx" style="display:flex;flex-wrap:wrap;gap:6px 22px;align-items:baseline">'
        f'<div style="font-size:16px;font-weight:650;color:var(--text)">{_esc(proj["name"])}</div>'
        f'<div style="font-size:12.5px;color:var(--text-2)">班级 {_esc(class_name)}</div>'
        f'<div style="font-size:12.5px;color:var(--text-2)">课时 {_esc(hours)}</div>'
        f'<div style="font-size:12.5px;color:var(--text-2)">进度 {_esc(progress)}</div>'
        f'<div style="font-size:12.5px;color:var(--text-2)">课程资料 {ov["files_total"]} 份</div>'
        "</div>"
    )


def _require_course(show_summary: bool = True) -> dict[str, Any] | None:
    proj = _proj()
    if not proj:
        render_course_required()
        return None
    if show_summary:
        render_course_summary(proj)
    return proj


def _fmt_size(n) -> str:
    try:
        size = int(n or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return "未知大小"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _fmt_time(ts) -> str:
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError):
        return "—"


def _tag(text: str, cls: str = "") -> str:
    return f'<span class="fm-tag {cls}">{_esc(text)}</span>'


def _download(label: str, data: bytes, filename: str, key: str, mime: str) -> None:
    st.download_button(label, data=data, file_name=filename, mime=mime, key=key,
                       use_container_width=True)


def _table(rows: list[dict[str, Any]], cols: list[tuple[str, str]]) -> None:
    if not rows:
        st.html('<div class="fm-empty">（暂无数据）</div>')
        return
    head = "".join(f"<th>{_esc(t)}</th>" for _, t in cols)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{_esc(r.get(k, ''))}</td>" for k, _ in cols) + "</tr>"
    st.html('<table class="fm-etable"><thead><tr>' + head + "</tr></thead><tbody>"
            + body + "</tbody></table>")


_items_table = _table


def _sec(title: str, right: str = "") -> None:
    r = f'<span class="r">{right}</span>' if right else ""
    st.html(f'<div class="fm-cardhead"><h2>{_esc(title)}</h2>{r}</div>')


def _kpi(label: str, value, sub: str = "", tone: str = "") -> None:
    st.html(
        f'<div class="fm-kpi {tone}"><div class="k">{_esc(label)}</div>'
        f'<div class="v">{_esc(value)}</div>'
        f'<div class="s">{_esc(sub)}</div></div>'
    )


def _save_upload(uploaded, *, category: str, visibility: str, project_id: int,
                 ai_context: int = 1) -> tuple[bool, str]:
    data = uploaded.getvalue()
    name = uploaded.name
    text, meta = edu.extract_text(name, data)
    note = meta.get("note") or ""
    parse_status = "parsed" if text.strip() else ("failed" if note else "parsed")
    try:
        db.save_file(
            name=name, ext=Path(name).suffix.lower().lstrip(".").upper(),
            kind="table" if meta.get("ext") in ("CSV", "XLSX", "XLS") else "doc",
            content=data, size=len(data), rows=meta.get("rows", 0),
            cols=meta.get("cols", 0), chars=meta.get("chars", 0),
            parsed_text=text or None, project_id=project_id,
            visibility=visibility, category=category,
            ai_context=ai_context, parse_status=parse_status,
        )
    except Exception as e:
        return False, f"保存失败：{e}"
    msg = f"已加入「{name}」"
    if note:
        msg += f"（{note}）"
    elif text:
        msg += f"，解析正文 {len(text)} 字"
    return True, msg


# ---------------------------------------------------------------------------
# 1) 课程驾驶舱
# ---------------------------------------------------------------------------
def render_course_page() -> None:
    projects = [p for p in db.list_projects() if p["name"] != "默认项目"]
    proj = _proj()

    _sec("课程项目", f"{len(projects)} 门课程")
    if not proj:
        render_course_required()
    else:
        render_course_summary(proj)

    _open_new = bool(ss.get("edu_open_new")) or not proj
    with st.expander("＋ 新建课程项目", expanded=_open_new):
        with st.form("edu_new_course", clear_on_submit=True):
            st.html('<div class="fm-sec-title">课程基本信息</div>')
            c1, c2, c3 = st.columns(3)
            c1.text_input("课程名称 *", key="nc_name", placeholder="例如：消费者行为分析")
            c2.text_input("授课班级或对象 *", key="nc_class",
                          placeholder="例如：市场营销 24-1 / 2024 级营销 1 班")
            c3.text_input("课时 *", key="nc_hours", placeholder="例如：16 课时")
            c4, c5 = st.columns(2)
            c4.text_input("教材 / 课程标准版本", key="nc_textbook", placeholder="例如：第 5 版")
            c5.text_input("课程描述（可选）", key="nc_desc")

            st.html('<div class="fm-sec-title">教学目标</div>')
            st.text_area("课程学习目标 *", key="nc_objectives", height=88,
                         placeholder="知识目标、能力目标、素养目标，可分行填写")
            c6, c7 = st.columns(2)
            c6.text_input("重点", key="nc_key")
            c7.text_input("难点", key="nc_diff")

            st.html('<div class="fm-sec-title">教学安排</div>')
            c8, c9 = st.columns(2)
            c8.text_input("当前教学进度", key="nc_progress",
                          placeholder="例如：第 3 次课 / 共 8 次")
            c9.text_input("课程备注（可选）", key="nc_note")
            submitted = st.form_submit_button("创建课程项目",
                                              use_container_width=True)

        if st.button("取消", key="nc_cancel", use_container_width=True):
            ss["edu_open_new"] = False
            st.rerun()

        if submitted:
            name = (ss.get("nc_name") or "").strip()
            klass = (ss.get("nc_class") or "").strip()
            hours = (ss.get("nc_hours") or "").strip()
            objectives = (ss.get("nc_objectives") or "").strip()
            missing = [lab for lab, val in (("课程名称", name), ("授课班级或对象", klass),
                                            ("课时", hours), ("学习目标", objectives)) if not val]
            if missing:
                st.error(f"请填写必填项：{'、'.join(missing)}")
            else:
                try:
                    folder = PROJECT_DIR / "".join(
                        "_" if ch in '<>:"/\\|?*' else ch for ch in name).strip()
                    folder.mkdir(parents=True, exist_ok=True)
                    pid = db.create_project(name, ss.get("nc_desc") or "", folder=str(folder))
                    db.update_course(
                        pid, audience=klass, class_name=klass, hours=hours,
                        objectives=objectives,
                        key_points=ss.get("nc_key") or "",
                        difficulties=ss.get("nc_diff") or "",
                        progress=ss.get("nc_progress") or "",
                        textbook_version=ss.get("nc_textbook") or "",
                        version="v1",
                    )
                    if (ss.get("nc_note") or "").strip():
                        db.update_project(pid, description=ss.get("nc_note") or "")
                    ss.current_project_id = pid
                    ss.current_project_name = name
                    ss["last_course_id"] = pid
                    ss["last_course_name"] = name
                    ss["edu_open_new"] = False
                    st.query_params["course"] = str(pid)
                    st.rerun()
                except Exception as e:
                    st.error(f"创建失败：{e}")

    if not proj:
        return


    ov = db.course_overview(proj["id"])
    analytics = edu.aggregate_analytics(proj["id"], sources=["答疑"])
    top_kp = analytics["knowledge_rows"][0]["knowledge_point"] if analytics["knowledge_rows"] else "暂无"

    cols = st.columns(3)
    with cols[0]:
        _kpi("课程资料", ov["files_total"], f"学生可见 {ov['files_student']} 份")
    with cols[1]:
        _kpi("最近备课包", ov["last_lesson_title"] or "未生成",
             f"共 {ov['lesson_count']} 个备课包", "ok" if ov["lesson_count"] else "")
    with cols[2]:
        _kpi("实训任务", ov["training_count"], "含草稿与已发布")
    cols = st.columns(3)
    with cols[0]:
        _kpi("待评审作业", ov["pending_review"], f"共 {ov['review_count']} 份提交",
             "warn" if ov["pending_review"] else "")
    with cols[1]:
        _kpi("高频薄弱知识点", top_kp, f"来自 {analytics['qa_count']} 条答疑")
    with cols[2]:
        _kpi("下一课建议", "已生成" if ov["nextlesson_count"] else "未生成",
             "可在学情分析页带入一键备课")

    missing = [lab for lab, key in (("学习目标", "objectives"), ("重点", "key_points"),
                                    ("难点", "difficulties")) if not (proj.get(key) or "").strip()]
    if missing:
        st.warning(f"课程信息待完善：{'、'.join(missing)}。完善后生成内容会更贴合课程。")

    _render_course_info(proj)
    _render_materials(proj)
    _render_related(proj)


def _render_course_info(proj: dict[str, Any]) -> None:
    with st.expander("课程基础信息", expanded=False):
        with st.form("edu_edit_course"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("课程名称", value=proj.get("name") or "")
            klass = c2.text_input("授课班级或对象",
                                  value=proj.get("class_name") or proj.get("audience") or "")
            hours = c3.text_input("课时", value=proj.get("hours") or "")
            c4, c5 = st.columns(2)
            progress = c4.text_input("当前教学进度", value=proj.get("progress") or "")
            textbook = c5.text_input("教材 / 课程标准版本",
                                     value=proj.get("textbook_version") or "")
            objectives = st.text_area("课程学习目标", value=proj.get("objectives") or "", height=80)
            c7, c8 = st.columns(2)
            key_points = c7.text_area("重点", value=proj.get("key_points") or "", height=70)
            diffs = c8.text_area("难点", value=proj.get("difficulties") or "", height=70)
            c9, c10 = st.columns(2)
            model = c9.text_input("当前模型", value=proj.get("model") or "")
            review_model = c10.text_input("审核模型", value=proj.get("review_model") or "")
            desc = st.text_area("课程描述", value=proj.get("description") or "", height=70)
            if st.form_submit_button("保存课程信息", type="primary"):
                db.update_course(proj["id"], audience=klass, class_name=klass, hours=hours,
                                 objectives=objectives, key_points=key_points,
                                 difficulties=diffs, progress=progress,
                                 textbook_version=textbook, model=model,
                                 review_model=review_model)
                db.update_project(proj["id"], name=name.strip() or proj["name"], description=desc)
                st.success("课程信息已保存")
                st.rerun()


def _render_materials(proj: dict[str, Any]) -> None:
    _sec("课程资料", "支持拖拽 / 点击上传，先确认再入库")
    st.caption("教师可见资料不会自动出现在学生答疑中；关闭「参与 AI 上下文」后，该资料不参与任何生成。")

    _round = int(ss.get("edu_mat_round", 0))
    ups = st.file_uploader(
        "选择资料文件", key=f"edu_mat_files_{_round}", accept_multiple_files=True,
        type=["pdf", "docx", "pptx", "xlsx", "xls", "csv", "md", "txt", "png", "jpg", "jpeg"],
    )
    if ups:
        st.html('<div class="fm-sec-title">待加入的课程资料</div>')
        pending: list[tuple[Any, str, str, int]] = []
        for i, up in enumerate(ups):
            with st.container(key=f"mat_pending_{i}"):
                c1, c2, c3, c4 = st.columns([3, 1.4, 1.4, 1.2])
                c1.markdown(f"**{up.name}**")
                c1.caption(_fmt_size(len(up.getvalue())))
                cat = c2.selectbox("资料类型", edu.CATEGORIES, key=f"mat_cat_{i}",
                                   label_visibility="collapsed")
                vis = c3.selectbox("可见范围", _VIS_OPTIONS, key=f"mat_vis_{i}",
                                   label_visibility="collapsed")
                ai_on = c4.checkbox("参与 AI", value=True, key=f"mat_ai_{i}")
                pending.append((up, cat, _VIS_MAP[vis], 1 if ai_on else 0))
        if st.button("加入课程资料", key="edu_mat_commit", type="primary"):
            bar = st.progress(0.0, text="正在解析并写入课程资料…")
            ok_n, errs = 0, []
            for idx, (up, cat, vis, ai_on) in enumerate(pending, 1):
                ok, msg = _save_upload(up, category=cat, visibility=vis,
                                       project_id=proj["id"], ai_context=ai_on)
                if ok:
                    ok_n += 1
                else:
                    errs.append(msg)
                bar.progress(idx / len(pending), text=f"已处理 {idx}/{len(pending)}")
            bar.empty()
            # 清空待上传列表，避免重复入库
            ss["edu_mat_round"] = _round + 1
            for i in range(len(pending)):
                for k in (f"mat_cat_{i}", f"mat_vis_{i}", f"mat_ai_{i}"):
                    ss.pop(k, None)
            if errs:
                for e in errs:
                    st.error(e)
                if ok_n:
                    st.warning(f"部分成功：已加入 {ok_n} 份资料")
            else:
                st.success(f"已加入 {ok_n} 份资料")
            st.rerun()

    files = db.list_files(project_id=proj["id"], limit=200)
    if not files:
        st.html('<div class="fm-empty">还没有课程资料。上传教材、课件、试题或案例后开始备课。</div>')
        return

    rows = []
    for f in files:
        vis_label, vis_cls = _VIS_BADGE.get(f.get("visibility", "teacher"), ("教师可见", "warn"))
        parse = {"parsed": "已解析", "failed": "解析失败", "parsing": "解析中"}.get(
            f.get("parse_status") or "parsed", "已解析")
        rows.append({
            "name": f"{_ext_icon(f)} {f['name']}",
            "category": f.get("category") or "未分类",
            "size": _fmt_size(f.get("size")),
            "vis": vis_label,
            "parse": parse,
            "ai": "参与" if int(f.get("ai_context", 1) or 0) else "不参与",
            "time": _fmt_time(f.get("created_at")),
        })
    _table(rows, [("name", "资料"), ("category", "类型"), ("size", "大小"),
                  ("vis", "可见范围"), ("parse", "解析状态"), ("ai", "AI 上下文"),
                  ("time", "上传时间")])

    with st.expander("资料操作（预览 / 下载 / 可见范围 / 删除）"):
        for f in files:
            with st.container(key=f"mat_row_{f['id']}"):
                c1, c2, c3, c4 = st.columns([3, 1.6, 1.2, 1.2])
                c1.markdown(f"**{f['name']}**")
                c1.caption(f"{f.get('category') or '未分类'} · {_fmt_size(f.get('size'))}")
                cur = edu.VISIBILITY_LABEL.get(f.get("visibility", "teacher"), "教师可见")
                pick = c2.selectbox("可见范围", _VIS_OPTIONS, index=_VIS_OPTIONS.index(cur),
                                    key=f"mvis_{f['id']}", label_visibility="collapsed")
                if _VIS_MAP[pick] != f.get("visibility"):
                    db.update_file(f["id"], visibility=_VIS_MAP[pick])
                    st.rerun()
                ai_on = c3.checkbox("参与 AI", value=bool(int(f.get("ai_context", 1) or 0)),
                                    key=f"mai_{f['id']}")
                if ai_on != bool(int(f.get("ai_context", 1) or 0)):
                    db.update_file(f["id"], ai_context=1 if ai_on else 0)
                    st.rerun()
                if c4.button("删除", key=f"mdel_{f['id']}"):
                    ss[f"mat_del_confirm_{f['id']}"] = True
                if ss.get(f"mat_del_confirm_{f['id']}"):
                    st.warning(f"确认删除「{f['name']}」？删除后无法恢复。")
                    d1, d2 = st.columns(2)
                    if d1.button("确认删除", key=f"mdel_yes_{f['id']}", type="primary"):
                        db.delete_file(f["id"])
                        ss.pop(f"mat_del_confirm_{f['id']}", None)
                        st.rerun()
                    if d2.button("取消", key=f"mdel_no_{f['id']}"):
                        ss.pop(f"mat_del_confirm_{f['id']}", None)
                        st.rerun()
                with st.expander("预览 / 下载"):
                    full = db.get_file(f["id"], with_content=True) or {}
                    text = (full.get("parsed_text") or "").strip()
                    st.text_area("正文摘录", value=text[:2000] or "（该文件未解析出正文）",
                                 height=140, disabled=True, key=f"mprev_{f['id']}")
                    if full.get("content"):
                        st.download_button(
                            "下载原文件", data=full["content"], file_name=f["name"],
                            key=f"mdl_{f['id']}", use_container_width=True)


def _ext_icon(f: dict[str, Any]) -> str:
    ext = (f.get("ext") or "").upper()
    return {"DOCX": "[W]", "DOC": "[W]", "PPTX": "[P]", "PPT": "[P]",
            "XLSX": "[E]", "XLS": "[E]", "CSV": "[E]", "PDF": "[PDF]"}.get(ext, "[文]")


def _render_related(proj: dict[str, Any]) -> None:
    _sec("关联记录", "点击进入对应页面")
    kinds = [("lesson", "备课包", "一键备课"), ("qa", "答疑", "学生答疑"),
             ("training", "实训", "创建实训"), ("review", "作业评审", "作业评审"),
             ("nextlesson", "下一课方案", "学情分析")]
    for k, label, nav in kinds:
        n = len(db.list_tasks(project_id=proj["id"], kind=k, limit=500))
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.markdown(f"**{label}**")
        c2.caption(f"{n} 条记录")
        if c3.button("查看", key=f"rel_{k}", use_container_width=True, disabled=n == 0):
            ss.nav = nav
            st.rerun()


# ---------------------------------------------------------------------------
# 2) 一键备课
# ---------------------------------------------------------------------------
def render_lesson_page() -> None:
    proj = _require_course()
    if not proj:
        return

    prefill = ss.pop("edu_lesson_prefill", None) or {}
    files = [f for f in db.list_files(project_id=proj["id"], limit=100)
             if int(f.get("ai_context", 1) or 0) == 1]
    default_ids = [f["id"] for f in files]
    if prefill.get("materials"):
        want = set(prefill["materials"])
        picked = [f["id"] for f in files if f["name"] in want]
        if picked:
            default_ids = picked

    st.html(
        '<div class="fm-ctx">'
        f'<div><span class="k">授课对象</span><b>{_esc(proj.get("audience") or "未填写")}</b></div>'
        f'<div><span class="k">课时</span><b>{_esc(proj.get("hours") or "未填写")}</b></div>'
        f'<div><span class="k">学习目标</span><b>{_esc((proj.get("objectives") or "未填写")[:60])}</b></div>'
        f'<div><span class="k">重点 / 难点</span><b>{_esc((proj.get("key_points") or "—")[:30])} / '
        f'{_esc((proj.get("difficulties") or "—")[:30])}</b></div>'
        f'<div><span class="k">可用资料</span><b>{len(files)} 份</b></div>'
        '</div>'
    )

    with st.form("lesson_form"):
        c1, c2, c3 = st.columns([2, 1, 1])
        topic = c1.text_input("本次课题 *", value=prefill.get("topic") or "",
                              placeholder="例如：消费者购买决策过程")
        default_type = prefill.get("lesson_type") or "新授课"
        lt_index = edu.LESSON_TYPES.index(default_type) if default_type in edu.LESSON_TYPES else 0
        lesson_type = c2.selectbox("课型", edu.LESSON_TYPES, index=lt_index)
        hours = c3.text_input("课时", value=proj.get("hours") or "1 课时")
        c4, c5 = st.columns(2)
        level = c4.text_input("学生基础 / 能力水平", placeholder="例如：已学过营销基础，数据分析较弱")
        style = c5.text_input("教学风格 / 课堂活动要求", placeholder="例如：多小组活动，案例用本地超市")
        outputs = st.multiselect("输出物", edu.LESSON_OUTPUTS,
                                 default=prefill.get("outputs") or
                                 ["教案", "PPT", "课堂练习", "答案与解析", "评分量规"])
        picked_ids = st.multiselect(
            "本次使用的课程资料", options=default_ids,
            default=default_ids, format_func=lambda i: next(
                (f["name"] for f in files if f["id"] == i), str(i)),
            help="默认选中全部可参与 AI 的资料")
        c6, c7, c8 = st.columns(3)
        model = c6.text_input("生成模型", value=proj.get("model") or "")
        review_model = c7.text_input("审核模型", value=proj.get("review_model") or "")
        dual = c8.checkbox("双模型一致性检查", value=False)
        extra = st.text_area("补充要求（可选）", height=70)
        st.html(f'<div class="fm-note">本次将使用 <b>{len(picked_ids)}</b> 份课程资料。'
                f'<span class="muted">教师可见资料同样参与备课，但不会出现在学生答疑中。</span></div>')
        go = st.form_submit_button("生成备课包", type="primary")

    if go:
        if not (topic or "").strip():
            st.error("请填写本次课题")
        else:
            _run_lesson_generation(proj, topic.strip(), extra.strip(), lesson_type, hours,
                                   level, style, outputs, picked_ids, model, review_model, dual)

    pkg = ss.get("edu_lesson_pkg") or {}
    if not pkg:
        st.html('<div class="fm-empty">还没有生成备课包。填写课题后点击「生成备课包」。</div>')
        _render_lesson_history(proj)
        return

    _render_lesson_result(proj, pkg)
    _render_lesson_history(proj)


def _run_lesson_generation(proj, topic, extra, lesson_type, hours, level, style,
                           outputs, file_ids, model, review_model, dual) -> None:
    status = st.status("正在生成备课包…", expanded=True)
    with status:
        st.write("① 正在解析课程资料")
        st.write("② 正在规划教学流程")
        try:
            pkg = edu.generate_lesson_package(
                proj["id"], topic, extra, lesson_type=lesson_type, hours=hours,
                student_level=level, style=style, outputs=outputs,
                file_ids=file_ids or [], model=model, review_model=review_model,
                dual_check=dual)
            st.write("③ 正在生成教案与 PPT 大纲")
            st.write("④ 正在生成练习、答案与评分量规")
            folder = _folder(proj)
            paths = [
                edu.save_artifact(folder, f"备课包_{topic}.docx",
                                  edu.export_lesson_docx(pkg, proj["name"])),
                edu.save_artifact(folder, f"课件_{topic}.pptx",
                                  edu.export_lesson_pptx(pkg, proj["name"])),
                edu.save_artifact(folder, f"练习与评分_{topic}.xlsx",
                                  edu.export_lesson_xlsx(pkg)),
            ]
            st.write("⑤ 正在检查目标覆盖和内容一致性")
            names = [f["name"] for f in db.list_files(project_id=proj["id"], limit=100)
                     if f["id"] in set(file_ids or [])]
            meta = {"pkg": pkg, "topic": topic, "version": "v1", "materials": names,
                    "model": model or "默认", "review_model": review_model,
                    "dual_check": bool(dual), "lesson_type": lesson_type,
                    "outputs": outputs, "created": time.time(),
                    "review_status": "待教师确认", "issues": [],
                    "paths": [str(p) for p in paths]}
            tid = db.save_task(kind="lesson", prompt=topic, answer="备课包已生成",
                               project_id=proj["id"], meta=meta)
            ss["edu_lesson_pkg"] = pkg
            ss["edu_lesson_topic"] = topic
            ss["edu_lesson_task_id"] = tid
            ss["edu_lesson_paths"] = [str(p) for p in paths]
            ss["edu_lesson_meta"] = meta
            status.update(label="备课包生成完成", state="complete", expanded=False)
            st.success("备课包已生成，并已写入课程文件夹")
        except Exception as e:
            status.update(label=f"生成失败：{e}", state="error", expanded=True)
            ss["edu_lesson_error"] = str(e)
    if ss.get("edu_lesson_error"):
        if st.button("重试生成", key="edu_lesson_retry", type="primary"):
            ss.pop("edu_lesson_error", None)
            _run_lesson_generation(proj, topic, extra, lesson_type, hours, level, style,
                                   outputs, file_ids, model, review_model, dual)
        return


def _render_lesson_result(proj: dict[str, Any], pkg: dict[str, Any]) -> None:
    meta = ss.get("edu_lesson_meta") or {}
    tid = ss.get("edu_lesson_task_id")
    c1, c2, c3, c4 = st.columns(4)
    c1.caption(f"课题：**{pkg.get('topic', '')}**")
    c2.caption(f"版本：{meta.get('version', 'v1')}")
    c3.caption(f"生成时间：{_fmt_time(meta.get('created'))}")
    c4.caption(f"模型：{meta.get('model', '—')}｜审核：{meta.get('review_status', '待教师确认')}")

    # 每次都本地重算，避免历史备课包沿用旧版检查逻辑
    checks = edu.lesson_checks(pkg)
    items = checks.get("items") or []
    ok_n = sum(1 for it in items if it.get("ok"))
    with st.expander(f"检查结果 · {ok_n}/{len(items)} 通过", expanded=ok_n < len(items)):
        cols = st.columns(3)
        for i, it in enumerate(items):
            tone = "ok" if it.get("ok") else "warn"
            with cols[i % 3]:
                st.html(f'<div class="fm-check {tone}"><div class="t">{_esc(it["label"])}</div>'
                        f'<div class="d">{_esc(it["detail"])}</div></div>')

    tabs = st.tabs(["教案", "PPT", "练习", "答案与解析", "评分量规", "教学目标对齐表", "来源与引用"])
    lp = pkg.get("lesson_plan") or {}
    with tabs[0]:
        for title, key in (("教学目标", "objectives"), ("重点", "key_points"),
                           ("难点", "difficulties"), ("课前准备", "preparation")):
            st.markdown(f"**{title}**")
            for it in lp.get(key) or []:
                st.markdown(f"- {it}")
        st.markdown("**教学过程**")
        _table([{"phase": s.get("phase", ""), "min": s.get("minutes", ""),
                 "teacher": s.get("teacher", ""), "student": s.get("student", ""),
                 "intent": s.get("design_intent", "")} for s in lp.get("steps") or []],
               [("phase", "环节"), ("min", "分钟"), ("teacher", "教师活动"),
                ("student", "学生活动"), ("intent", "设计意图")])
        if lp.get("homework"):
            st.markdown(f"**作业布置**：{lp['homework']}")
    with tabs[1]:
        ppt = pkg.get("ppt") or {}
        st.markdown(f"### {ppt.get('title', '')}")
        for i, s in enumerate(ppt.get("slides") or [], 1):
            with st.expander(f"第 {i} 页 · {s.get('title', '')}"):
                for b in s.get("bullets") or []:
                    st.markdown(f"- {b}")
                if s.get("notes"):
                    st.caption(f"讲稿：{s['notes']}")
    with tabs[2]:
        for key, label in (("basic", "基础题"), ("applied", "应用题"), ("extension", "拓展题")):
            st.markdown(f"**{label}**")
            for i, q in enumerate((pkg.get("questions") or {}).get(key) or [], 1):
                st.markdown(f"{i}. {q.get('q', '')}")
    with tabs[3]:
        for key, label in (("basic", "基础题"), ("applied", "应用题"), ("extension", "拓展题")):
            st.markdown(f"**{label}**")
            for i, q in enumerate((pkg.get("questions") or {}).get(key) or [], 1):
                st.markdown(f"{i}. {q.get('q', '')}")
                st.caption(f"答案：{q.get('answer', '')}｜提示1：{q.get('hint1', '')}｜"
                           f"提示2：{q.get('hint2', '')}")
    with tabs[4]:
        _table([{"d": r.get("dimension", ""), "w": r.get("weight", ""),
                 "ex": r.get("excellent", ""), "ps": r.get("pass", "")}
                for r in pkg.get("rubric") or []],
               [("d", "维度"), ("w", "权重"), ("ex", "优秀"), ("ps", "合格")])
        st.caption(f"量规总分：{sum(int(r.get('weight') or 0) for r in pkg.get('rubric') or [])}")
    with tabs[5]:
        _table([{"kp": r.get("knowledge_point", ""), "obj": r.get("objective", ""),
                 "act": r.get("activity", ""), "ass": r.get("assessment", "")}
                for r in pkg.get("alignment") or []],
               [("kp", "知识点"), ("obj", "对应目标"), ("act", "对应活动"), ("ass", "评价方式")])
    with tabs[6]:
        _table([{"c": s.get("content", ""), "s": s.get("source", "")}
                for s in pkg.get("sources") or []], [("c", "成果内容"), ("s", "引用资料")])
        st.caption("本次参与生成的课程资料：" + ("、".join(meta.get("materials") or []) or "未记录"))

    with st.expander("在线编辑与重新生成"):
        section = st.selectbox("选择成果", list(edu._SECTION_PROMPT.keys()),
                               format_func=lambda k: {"lesson_plan": "教案", "ppt": "PPT",
                                                      "questions": "练习与答案",
                                                      "rubric": "评分量规"}[k],
                               key="edu_sec_pick")
        draft = st.text_area("内容（JSON，可直接修改后保存）",
                             value=json.dumps(pkg.get(section), ensure_ascii=False, indent=2),
                             height=220, key=f"edu_sec_edit_{section}")
        c1, c2 = st.columns(2)
        if c1.button("保存修订", key="edu_sec_save", type="primary"):
            try:
                pkg[section] = json.loads(draft)
                pkg["checks"] = edu.lesson_checks(pkg)
                if tid:
                    db.update_task(int(tid), meta={**meta, "pkg": pkg})
                ss["edu_lesson_pkg"] = pkg
                ss["edu_lesson_meta"] = {**meta, "pkg": pkg}
                st.success("已保存修订")
                st.rerun()
            except Exception as e:
                st.error(f"保存失败：{e}")
        if c2.button("重新生成这一项", key="edu_sec_regen"):
            try:
                with st.spinner("正在重新生成…"):
                    pkg = edu.regenerate_section(proj["id"], pkg, section)
                if tid:
                    db.update_task(int(tid), meta={**meta, "pkg": pkg})
                ss["edu_lesson_pkg"] = pkg
                ss["edu_lesson_meta"] = {**meta, "pkg": pkg}
                st.success("已重新生成")
                st.rerun()
            except Exception as e:
                st.error(f"重新生成失败：{e}")

    with st.expander("下载成果文件（Word / PPT / Excel）", expanded=False):
        cols = st.columns(3)
        with cols[0]:
            _download("下载 Word 备课包", edu.export_lesson_docx(pkg, proj["name"]),
                      f"备课包_{pkg.get('topic', '课程')}.docx", "dl_lesson_docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with cols[1]:
            _download("下载 PPT 课件", edu.export_lesson_pptx(pkg, proj["name"]),
                      f"课件_{pkg.get('topic', '课程')}.pptx", "dl_lesson_pptx",
                      "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        with cols[2]:
            _download("下载 Excel 练习与评分", edu.export_lesson_xlsx(pkg),
                      f"练习与评分_{pkg.get('topic', '课程')}.xlsx", "dl_lesson_xlsx",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.html('<div class="fm-sec-title">教师确认</div>')
    c4, c5 = st.columns(2)
    if c4.button("确认备课包", key="edu_lesson_ok", type="primary"):
        if tid:
            db.update_task(int(tid), meta={**meta, "pkg": pkg, "review_status": "已确认"})
        ss["edu_lesson_meta"] = {**meta, "pkg": pkg, "review_status": "已确认"}
        st.success("已确认")
        st.rerun()
    issue = c5.text_input("标记问题（可选）", key="edu_lesson_issue")
    if issue.strip():
        if st.button("保存问题标记", key="edu_lesson_issue_save"):
            issues = list(meta.get("issues") or []) + [issue.strip()]
            if tid:
                db.update_task(int(tid), meta={**meta, "pkg": pkg, "issues": issues,
                                               "review_status": "有问题待处理"})
            ss["edu_lesson_meta"] = {**meta, "pkg": pkg, "issues": issues,
                                     "review_status": "有问题待处理"}
            st.success("已标记")
            st.rerun()


def _render_lesson_history(proj: dict[str, Any]) -> None:
    tasks = db.list_tasks(project_id=proj["id"], kind="lesson", limit=20)
    if not tasks:
        return
    with st.expander(f"历史备课包（{len(tasks)}）"):
        for t in tasks:
            m = t.get("meta") or {}
            c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.6])
            c1.markdown(f"**{t['prompt']}**")
            c1.caption(f"{_fmt_time(t['created_at'])} · 资料 {len(m.get('materials') or [])} 份 · "
                       f"{m.get('review_status') or '待教师确认'}")
            c2.caption(m.get("version") or "v1")
            if c3.button("继续编辑", key=f"edu_lesson_load_{t['id']}"):
                pkg = m.get("pkg")
                if pkg:
                    ss["edu_lesson_pkg"] = pkg
                    ss["edu_lesson_topic"] = t["prompt"]
                    ss["edu_lesson_task_id"] = t["id"]
                    ss["edu_lesson_meta"] = m
                    st.rerun()
            if c4.button("复制为新版本", key=f"edu_lesson_copy_{t['id']}"):
                pkg = m.get("pkg")
                if pkg:
                    new_pkg = json.loads(json.dumps(pkg, ensure_ascii=False))
                    new_meta = {**m, "pkg": new_pkg,
                                "version": f"v{len(tasks) + 1}",
                                "created": time.time(), "review_status": "待教师确认"}
                    new_id = db.save_task(kind="lesson", prompt=t["prompt"] + "（副本）",
                                          answer="备课包副本", project_id=proj["id"],
                                          meta=new_meta)
                    ss["edu_lesson_pkg"] = new_pkg
                    ss["edu_lesson_task_id"] = new_id
                    ss["edu_lesson_meta"] = new_meta
                    st.rerun()


# ---------------------------------------------------------------------------
# 3) 引导式答疑
# ---------------------------------------------------------------------------
def render_tutor_page() -> None:
    proj = _require_course()
    if not proj:
        return
    if is_student_mode():
        _render_student_tutor(proj)
    else:
        _render_teacher_tutor(proj)


def _render_teacher_tutor(proj: dict[str, Any]) -> None:
    _sec("答疑记录", "学生答疑管理 · 点击查看完整对话")
    qa = db.list_tasks(project_id=proj["id"], kind="qa", limit=200)
    if not qa:
        st.html('<div class="fm-empty">本课程还没有答疑记录。学生在「学生空间 → 我的答疑」提问后会显示在这里。</div>')
        return
    status_filter = st.multiselect("按状态筛选", list(_STATUS_LABEL.values()),
                                   default=list(_STATUS_LABEL.values()))
    label_to_key = {v: k for k, v in _STATUS_LABEL.items()}
    want = {label_to_key[x] for x in status_filter}
    rows, shown = [], []
    for t in qa:
        m = t.get("meta") or {}
        if (m.get("status") or "ai") not in want:
            continue
        shown.append(t)
        rows.append({
            "stu": m.get("student") or "匿名学生",
            "time": _fmt_time(t["created_at"]),
            "kp": m.get("knowledge_point") or "—",
            "err": m.get("error_type") or "—",
            "q": (t.get("prompt") or "")[:46],
            "status": _STATUS_LABEL.get(m.get("status") or "ai", "AI引导中"),
            "src": "、".join(m.get("sources") or []) or "—",
            "common": "是" if m.get("common_mistake") else "否",
        })
    _table(rows, [("stu", "学生"), ("time", "提问时间"), ("kp", "知识点"), ("err", "错因"),
                  ("q", "问题摘要"), ("status", "当前状态"), ("src", "使用资料"),
                  ("common", "共性误区")])

    st.html('<div class="fm-sec-title">完整对话</div>')
    opts = {f"{_fmt_time(t['created_at'])} · {(t.get('meta') or {}).get('student') or '匿名'} · "
            f"{(t.get('meta') or {}).get('knowledge_point') or ''}": t["id"] for t in shown}
    if not opts:
        st.caption("当前筛选下没有记录")
        return
    pick = st.selectbox("选择一条记录", list(opts.keys()), key="edu_tutor_pick")
    task = next(t for t in shown if t["id"] == opts[pick])
    m = task.get("meta") or {}
    st.caption(f"状态：{_STATUS_LABEL.get(m.get('status') or 'ai', 'AI引导中')}｜"
               f"错因：{m.get('error_type') or '—'}｜资料：{'、'.join(m.get('sources') or []) or '—'}")
    for msg in m.get("history") or []:
        _chat_bubble(msg.get("role", "AI"), msg.get("text", ""))
    c1, c2 = st.columns(2)
    if c1.button("标记教师接管", key=f"edu_takeover_{task['id']}"):
        db.update_task(task["id"], meta={**m, "status": "teacher"})
        st.rerun()
    if c2.button("标记已解决", key=f"edu_solved_{task['id']}"):
        db.update_task(task["id"], meta={**m, "status": "solved"})
        st.rerun()


def _render_student_tutor(proj: dict[str, Any]) -> None:
    if not student_name():
        st.caption("请先在顶部「学生身份」中填写匿名标识（例如 学生A），提问记录会归属到该身份。")

    _sec("我的答疑", "AI 分层引导，不直接给答案")
    mine = [t for t in db.list_tasks(project_id=proj["id"], kind="qa", limit=200)
            if ((t.get("meta") or {}).get("student") or "") == student_name()]
    if mine:
        _table([{"t": _fmt_time(t["created_at"]),
                 "kp": (t.get("meta") or {}).get("knowledge_point") or "—",
                 "q": (t.get("prompt") or "")[:50],
                 "s": _STATUS_LABEL.get((t.get("meta") or {}).get("status") or "ai", "AI引导中")}
                for t in mine],
               [("t", "时间"), ("kp", "知识点"), ("q", "问题"), ("s", "状态")])
    else:
        st.html('<div class="fm-empty">还没有提问记录。点击下方「新建答疑」开始。</div>')

    if st.button("新建答疑", key="edu_tutor_new", type="primary"):
        ss["edu_tutor"] = {"history": [], "stage": 0, "task_id": None, "attempts": 0,
                           "question": "", "full": None}
        st.rerun()

    state = ss.get("edu_tutor")
    if not state:
        _render_my_feedback(proj)
        return

    st.html('<div class="fm-sec-title">答疑对话</div>')
    up = st.file_uploader("上传题目（图片 / PDF / Word / PPT / Excel）", key="edu_tutor_up",
                          type=["png", "jpg", "jpeg", "pdf", "docx", "pptx", "xlsx", "txt", "md"])
    ocr_text = ""
    if up is not None:
        if up.type and up.type.startswith("image/"):
            st.image(up, caption=up.name, use_container_width=False)
        text, meta = edu.extract_text(up.name, up.getvalue())
        if text.strip():
            ocr_text = st.text_area("识别结果（可修改）", value=text[:2000], height=100,
                                    key="edu_tutor_ocr")
        else:
            st.warning(f"未能识别该文件：{meta.get('note') or '未知原因'}")

    q = st.text_area("题目或卡点描述", value=state.get("question") or "", height=90,
                     key="edu_tutor_q")
    for msg in state["history"]:
        _chat_bubble(msg["role"], msg["text"])

    if not state["history"]:
        if st.button("提交问题", key="edu_tutor_send", type="primary"):
            question = (q or "").strip() or (ocr_text or "").strip()
            if not question:
                st.error("请描述问题，或上传题目文件")
            else:
                state["question"] = question
                _tutor_step(proj, state, question, action="try")
                st.rerun()
    else:
        c1, c2, c3 = st.columns(3)
        if c1.button("给我一点提示", key="edu_btn_hint"):
            _tutor_step(proj, state, state["question"], action="hint")
            st.rerun()
        if c2.button("我还是不会", key="edu_btn_stuck"):
            _tutor_step(proj, state, state["question"], action="stuck")
            st.rerun()
        if c3.button("我想自己试试", key="edu_btn_try"):
            _tutor_step(proj, state, state["question"], action="try")
            st.rerun()
        if state.get("attempts", 0) >= 1:
            if st.button("查看完整解析", key="edu_tutor_full"):
                try:
                    with st.spinner("正在整理完整解析…"):
                        full = edu.tutor_full_answer(proj["id"], state["question"], state["history"])
                    state["full"] = full
                    ss["edu_tutor"] = state
                    st.rerun()
                except Exception as e:
                    st.error(f"生成失败：{e}")
        last = state.get("last") or {}
        if last.get("need_teacher"):
            st.warning("这个问题超出当前资料范围，建议教师接管。")
        if last.get("summary_prompt"):
            st.caption(f"请用自己的话总结：{last['summary_prompt']}")

    full = state.get("full")
    if full:
        st.html('<div class="fm-sec-title">完整解析</div>')
        st.markdown(full.get("solution", ""))
        st.markdown(f"**答案**：{full.get('answer', '')}")
        if full.get("sources"):
            st.caption("引用资料：" + "、".join(full["sources"]))
        sq = full.get("similar_question") or {}
        if sq:
            st.markdown(f"**类似练习**：{sq.get('q', '')}")
            st.caption(f"提示：{sq.get('hint', '')}｜答案：{sq.get('answer', '')}")

    if st.button("结束本次答疑", key="edu_tutor_reset"):
        ss.pop("edu_tutor", None)
        st.rerun()

    _render_my_feedback(proj)


def _tutor_step(proj: dict[str, Any], state: dict[str, Any], question: str,
                action: str) -> None:
    try:
        with st.spinner("正在判断卡点并给出引导…"):
            reply = edu.tutor_reply(proj["id"], question, state["history"], state["stage"],
                                    student_mode=True, action=action)
        state["history"].append({"role": "学生", "text": question if not state["history"]
                                 else {"hint": "给我一点提示", "stuck": "我还是不会",
                                       "try": "我想自己试试"}[action]})
        state["history"].append({"role": "AI", "text": reply.get("feedback", "")})
        state["stage"] = min(state["stage"] + 1, 3)
        state["attempts"] = int(state.get("attempts", 0)) + 1
        state["last"] = reply
        meta = {
            "student": student_name() or "匿名学生",
            "knowledge_point": reply.get("knowledge_point", ""),
            "error_type": reply.get("error_type", ""),
            "stage": reply.get("stage", ""),
            "status": "waiting" if not reply.get("need_teacher") else "attention",
            "sources": reply.get("sources") or [],
            "history": state["history"],
        }
        if state.get("task_id"):
            db.update_task(state["task_id"], answer=reply.get("feedback", ""), meta=meta)
        else:
            state["task_id"] = db.save_task(
                kind="qa", prompt=question[:1000], answer=reply.get("feedback", ""),
                project_id=proj["id"], meta=meta)
        ss["edu_tutor"] = state
    except Exception as e:
        st.error(f"生成失败：{e}")


def _chat_bubble(role: str, text: str) -> None:
    cls = "stu" if role == "学生" else "ai"
    st.html(f'<div class="fm-msg {cls}"><div class="who">{_esc(role)}</div>'
            f'<div class="txt">{_esc(text)}</div></div>')


def _render_my_feedback(proj: dict[str, Any]) -> None:
    name = student_name()
    if not name:
        return
    rows = []
    for t in db.list_tasks(project_id=proj["id"], kind="review", limit=200):
        m = t.get("meta") or {}
        if (m.get("student") or "") != name or m.get("status") != "published":
            continue
        rows.append({"task": t["prompt"], "ai": (m.get("ai") or {}).get("total", ""),
                     "final": m.get("final_total", ""), "c": (m.get("teacher") or {}).get("comment", "")})
    if rows:
        st.html('<div class="fm-sec-title">我的作业反馈（教师已发布）</div>')
        _table(rows, [("task", "任务"), ("final", "最终得分"), ("c", "教师评语")])


# ---------------------------------------------------------------------------
# 4) 实训任务
# ---------------------------------------------------------------------------
def render_training_page() -> None:
    proj = _require_course()
    if not proj:
        return
    tasks = db.list_tasks(project_id=proj["id"], kind="training", limit=50)

    if is_student_mode():
        _sec("实训任务", "教师已发布")
        pub = [t for t in tasks if ((t.get("meta") or {}).get("pkg") or {}).get("status") == "published"]
        if not pub:
            st.html('<div class="fm-empty">暂时没有已发布的实训任务。</div>')
            return
        for t in pub:
            pkg = (t.get("meta") or {}).get("pkg") or {}
            with st.expander(f"{pkg.get('title') or t['prompt'][:30]}（已发布）", expanded=True):
                st.markdown(f"**背景**：{pkg.get('background', '')}")
                st.markdown(f"**角色**：{pkg.get('student_role', '')}｜**目标**：{pkg.get('goal', '')}")
                for title, key in (("Excel 要求", "excel_requirements"),
                                   ("Word 交付物", "word_requirements"),
                                   ("PPT 汇报", "ppt_requirements")):
                    st.markdown(f"**{title}**")
                    for it in pkg.get(key) or []:
                        st.markdown(f"- {it}")
        return

    _sec("实训任务生成器", "把真实工作场景转成可执行实训")
    with st.form("edu_training_form"):
        scenario = st.text_area(
            "真实工作场景 *", height=100,
            placeholder="例如：超市要做一次消费者行为分析，需要根据销售数据写出一页经营建议并做五分钟汇报")
        extra = st.text_input("补充要求（可选）", placeholder="例如：4 课时、三人一组、使用 Excel 2019")
        go = st.form_submit_button("生成实训任务包", type="primary")

    if go:
        if not (scenario or "").strip():
            st.error("请填写工作场景")
        else:
            try:
                with st.spinner("正在生成实训背景、任务单、量规与常见错误…"):
                    pkg = edu.generate_training(proj["id"], scenario.strip(), (extra or "").strip())
                pkg["status"] = "draft"
                title = pkg.get("title") or "实训任务"
                folder = _folder(proj)
                paths = [
                    edu.save_artifact(folder, f"实训任务单_{title}.docx",
                                      edu.export_training_docx(pkg, proj["name"])),
                    edu.save_artifact(folder, f"实训说明_{title}.pptx",
                                      edu.export_training_pptx(pkg, proj["name"])),
                    edu.save_artifact(folder, f"实训任务与量规_{title}.xlsx",
                                      edu.export_training_xlsx(pkg)),
                ]
                tid = db.save_task(kind="training", prompt=scenario.strip(),
                                   answer="实训任务包已生成", project_id=proj["id"],
                                   meta={"pkg": pkg, "paths": [str(p) for p in paths]})
                ss["edu_training_pkg"] = pkg
                ss["edu_training_task_id"] = tid
                st.success("实训任务包已生成（草稿），确认后可发布")
            except Exception as e:
                st.error(f"生成失败：{e}")

    if not tasks:
        st.html('<div class="fm-empty">还没有实训任务。填写真实工作场景后点击生成。</div>')
        return

    st.html('<div class="fm-sec-title">实训任务列表</div>')
    rows = []
    for t in tasks:
        pkg = (t.get("meta") or {}).get("pkg") or {}
        rows.append({"title": pkg.get("title") or t["prompt"][:30],
                     "status": _TRAIN_STATUS.get(pkg.get("status") or "draft", "草稿"),
                     "time": _fmt_time(t["created_at"]),
                     "points": sum(int(r.get("points") or 0) for r in pkg.get("data_tasks") or [])})
    _table(rows, [("title", "任务"), ("status", "状态"), ("points", "任务总分"), ("time", "创建时间")])

    st.html('<div class="fm-sec-title">任务操作</div>')
    opts = {f"{(t.get('meta') or {}).get('pkg', {}).get('title') or t['prompt'][:30]}": t["id"]
            for t in tasks}
    pick = st.selectbox("选择实训任务", list(opts.keys()), key="edu_tr_pick")
    task = next(t for t in tasks if t["id"] == opts[pick])
    pkg = (task.get("meta") or {}).get("pkg") or {}
    cur = pkg.get("status") or "draft"
    c1, c2, c3 = st.columns([1.4, 1, 1])
    new_status = c1.selectbox("发布状态", list(_TRAIN_STATUS.keys()),
                              index=list(_TRAIN_STATUS.keys()).index(cur)
                              if cur in _TRAIN_STATUS else 0,
                              format_func=lambda k: _TRAIN_STATUS[k], key="edu_tr_status")
    if c2.button("保存状态", key="edu_tr_status_save"):
        pkg["status"] = new_status
        db.update_task(task["id"], meta={**(task.get("meta") or {}), "pkg": pkg})
        st.success("状态已更新")
        st.rerun()
    if c3.button("进入作业评审", key="edu_tr_to_review"):
        ss["edu_review_task_id"] = task["id"]
        ss.nav = "作业评审"
        st.rerun()

    with st.expander("任务详情与交付要求"):
        st.markdown(f"**{pkg.get('title', '')}**")
        st.caption(pkg.get("goal", ""))
        _table([{"s": r.get("step", ""), "t": r.get("task", ""), "d": r.get("deliverable", ""),
                 "p": r.get("points", "")} for r in pkg.get("data_tasks") or []],
               [("s", "步骤"), ("t", "任务"), ("d", "交付物"), ("p", "分值")])
        _download("下载 Word 任务单", edu.export_training_docx(pkg, proj["name"]),
                  f"实训任务单_{pkg.get('title', '')}.docx", "dl_tr_docx",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        _download("下载 Excel 任务与量规", edu.export_training_xlsx(pkg),
                  f"实训任务与量规_{pkg.get('title', '')}.xlsx", "dl_tr_xlsx",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# 5) 作业评审与教师复核
# ---------------------------------------------------------------------------
def _rubric_options(proj: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for t in db.list_tasks(project_id=proj["id"], kind="lesson", limit=20):
        pkg = (t.get("meta") or {}).get("pkg") or {}
        if pkg.get("rubric"):
            out.append({"label": f"备课包 · {t['prompt']}",
                        "rubric": pkg["rubric"], "task": t["prompt"], "kind": "备课包"})
    for t in db.list_tasks(project_id=proj["id"], kind="training", limit=20):
        pkg = (t.get("meta") or {}).get("pkg") or {}
        if pkg.get("rubric"):
            out.append({"label": f"实训 · {pkg.get('title') or t['prompt'][:20]}",
                        "rubric": pkg["rubric"], "task": pkg.get("title") or t["prompt"],
                        "kind": "实训"})
    return out


def render_review_page() -> None:
    proj = _require_course()
    if not proj:
        return
    _sec("作业评审", "AI 按量规初评 → 教师逐项复核 → 发布终评")

    rubrics = _rubric_options(proj)
    ups = st.file_uploader("上传学生提交（可多选：Word / Excel / PPT / PDF）", key="edu_review_up",
                           accept_multiple_files=True,
                           type=["docx", "xlsx", "xls", "pptx", "pdf", "txt", "md", "csv"])
    c1, c2 = st.columns(2)
    student = c1.text_input("学生姓名 / 匿名编号", value=student_name(), key="edu_review_student")
    klass = c2.text_input("班级", value=proj.get("class_name") or "", key="edu_review_class")
    if rubrics:
        labels = [f"{r['label']}｜{sum(int(x.get('weight') or 0) for x in r['rubric'])} 分 / "
                  f"{len(r['rubric'])} 个维度" for r in rubrics]
        pick = st.selectbox("评分量规", labels, key="edu_review_rubric_pick")
        rubric_row = rubrics[labels.index(pick)]
    else:
        rubric_row = None
        st.warning("当前课程还没有评分量规。请先在「一键备课」生成评分量规，或在「创建实训」生成含量规的任务。")

    reason = ""
    if not ups:
        reason = "请先上传学生提交文件"
    elif not rubric_row:
        reason = "请先选择评分量规"
    if reason:
        st.caption(f"开始评审不可用：{reason}")
    if st.button("开始评审", key="edu_review_run", type="primary", disabled=bool(reason)):
        texts, names = [], []
        for up in ups:
            text, meta = edu.extract_text(up.name, up.getvalue())
            names.append(up.name)
            texts.append(f"【{up.name}】\n{text[:6000] or '（未能提取正文：' + str(meta.get('note')) + '）'}")
        try:
            with st.spinner("正在按量规逐维度评审并定位证据…"):
                review = edu.evaluate_submission(proj["id"], "\n\n".join(texts),
                                                 "、".join(names), rubric=rubric_row["rubric"],
                                                 student=student)
            ss["edu_review"] = review
            ss["edu_review_meta"] = {"student": student, "class_name": klass,
                                     "files": names, "text": "\n\n".join(texts)[:6000],
                                     "rubric": rubric_row["rubric"],
                                     "rubric_name": rubric_row["label"],
                                     "task": rubric_row["task"]}
            st.success("AI 初评完成，请核对证据并给出终评")
        except Exception as e:
            st.error(f"评审失败：{e}")

    review = ss.get("edu_review")
    rmeta = ss.get("edu_review_meta") or {}
    if not review:
        st.html('<div class="fm-empty">上传提交物并选择量规后开始评审。</div>')
        _render_review_history(proj)
        return

    left, right = st.columns([1, 1.15])
    with left:
        st.html('<div class="fm-sec-title">学生提交</div>')
        st.caption(f"{rmeta.get('student') or '未填写学生'} · {rmeta.get('class_name') or ''} · "
                   f"{len(rmeta.get('files') or [])} 个文件")
        st.caption("、".join(rmeta.get("files") or []))
        st.text_area("提交内容摘录", value=rmeta.get("text", ""), height=430, disabled=True,
                     key="edu_review_text")
    with right:
        st.html('<div class="fm-sec-title">分维度评分证据</div>')
        accepted = ss.setdefault("edu_review_accept", {})
        for i, d in enumerate(review.get("dimensions") or []):
            name = d.get("name", f"维度{i}")
            with st.expander(f"{name} · {d.get('score', 0)}/{d.get('max', 0)} 分",
                             expanded=i == 0):
                st.markdown(f"**依据**：{d.get('evidence', '')}")
                st.markdown(f"**扣分原因 / 建议**：{d.get('suggestion', '')}")
                st.caption(f"位置：{d.get('location', '')}")
                accepted[name] = st.checkbox("教师接受 AI 判断", value=True, key=f"edu_acc_{i}")
        st.html(f'<div class="fm-note">AI 初评总分：<b>{review.get("total", 0)}</b> 分</div>')
        ss["edu_review_accept"] = accepted

    st.html('<div class="fm-sec-title">教师复核与终评</div>')
    with st.form("edu_review_teacher"):
        finals: dict[str, float] = {}
        cols = st.columns(min(max(len(review.get("dimensions") or []), 1), 4))
        for i, d in enumerate(review.get("dimensions") or []):
            name = d.get("name", f"维度{i}")
            finals[name] = cols[i % len(cols)].number_input(
                f"{name}（满分 {d.get('max', 0)}）", min_value=0.0,
                max_value=float(d.get("max", 100) or 100), value=float(d.get("score", 0) or 0),
                step=1.0, key=f"edu_final_{i}")
        comment = st.text_area("教师终评评语", value=review.get("summary", ""), height=90,
                               key="edu_review_comment")
        reason_txt = st.text_input("修改原因（调整分数时填写）", key="edu_review_reason")
        status = st.radio("处理结果", ["通过并发布", "退回修改", "需要人工进一步检查"],
                          horizontal=True, key="edu_review_status")
        if st.form_submit_button("保存教师终评", type="primary"):
            final_total = round(sum(finals.values()), 1)
            status_key = {"通过并发布": "published", "退回修改": "returned",
                          "需要人工进一步检查": "manual"}[status]
            record = {
                "student": rmeta.get("student", ""), "class_name": rmeta.get("class_name", ""),
                "files": rmeta.get("files") or [], "file": "、".join(rmeta.get("files") or []),
                "task": rmeta.get("task", ""), "rubric_name": rmeta.get("rubric_name", ""),
                "rubric": rmeta.get("rubric") or [],
                "ai": review,
                "teacher": {"scores": finals, "total": final_total, "comment": comment,
                            "reason": reason_txt},
                "accepted": ss.get("edu_review_accept") or {},
                "final_total": final_total, "status": status_key,
                "versions": [{"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                              "ai_total": review.get("total", 0), "final_total": final_total}],
            }
            db.save_task(kind="review", prompt=f"{rmeta.get('student') or '学生'} · "
                                               f"{rmeta.get('task') or '实训提交'}",
                         answer=comment, project_id=proj["id"], meta=record)
            ss.pop("edu_review", None)
            ss.pop("edu_review_meta", None)
            ss.pop("edu_review_accept", None)
            st.success(f"已保存：{final_total} 分（AI 初评 {review.get('total', 0)} 分）· {status}")
            st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        _download("下载评审报告 Word",
                  edu.export_review_docx(review, student=rmeta.get("student", ""),
                                         course=proj["name"],
                                         file_name="、".join(rmeta.get("files") or [])),
                  f"评审报告_{rmeta.get('student') or '学生'}.docx", "dl_review_docx",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c2:
        if st.button("清除当前评审", key="edu_review_clear"):
            ss.pop("edu_review", None)
            ss.pop("edu_review_meta", None)
            st.rerun()

    _render_review_history(proj)


def _render_review_history(proj: dict[str, Any]) -> None:
    tasks = db.list_tasks(project_id=proj["id"], kind="review", limit=50)
    if not tasks:
        return
    st.html('<div class="fm-sec-title">评审记录</div>')
    rows = []
    for t in tasks:
        m = t.get("meta") or {}
        rows.append({
            "stu": m.get("student") or "—",
            "task": m.get("task") or t["prompt"][:20],
            "files": len(m.get("files") or ([m["file"]] if m.get("file") else [])),
            "ai": (m.get("ai") or {}).get("total", ""),
            "final": m.get("final_total", ""),
            "status": _REVIEW_STATUS.get(m.get("status") or "pending", "待复核"),
            "sub": _fmt_time(t["created_at"]),
        })
    _table(rows, [("stu", "学生"), ("task", "任务"), ("files", "文件数"), ("ai", "AI 初评"),
                  ("final", "教师终评"), ("status", "状态"), ("sub", "提交时间")])
    opts = {f"{r['stu']} · {r['task']} · {r['sub']}": t["id"] for r, t in zip(rows, tasks)}
    pick = st.selectbox("查看完整评审结果", list(opts.keys()), key="edu_review_hist_pick")
    task = next(t for t in tasks if t["id"] == opts[pick])
    m = task.get("meta") or {}
    st.caption(f"状态：{_REVIEW_STATUS.get(m.get('status') or 'pending', '待复核')}｜"
               f"AI 初评 {(m.get('ai') or {}).get('total', 0)}｜教师终评 {m.get('final_total', '')}")
    for d in (m.get("ai") or {}).get("dimensions") or []:
        st.markdown(f"- **{d.get('name')}**：{d.get('score')}/{d.get('max')}　"
                    f"{d.get('evidence', '')}")
    if (m.get("teacher") or {}).get("comment"):
        st.caption(f"教师评语：{m['teacher']['comment']}")


# ---------------------------------------------------------------------------
# 6) 学情分析与下一课
# ---------------------------------------------------------------------------
def render_analytics_page() -> None:
    proj = _require_course()
    if not proj:
        return
    _sec("学情分析", "所有统计均标注数据来源与分母")

    with st.container(key="edu_ana_filters"):
        c1, c2, c3, c4 = st.columns(4)
        c1.text_input("班级", value=proj.get("class_name") or "", disabled=True,
                      key="edu_ana_class")
        days = c2.selectbox("时间范围", ["全部", "近 7 天", "近 30 天"], key="edu_ana_days")
        all_kp = sorted({(t.get("meta") or {}).get("knowledge_point") or ""
                         for t in db.list_tasks(project_id=proj["id"], kind="qa", limit=500)} - {""})
        kp = c3.selectbox("知识点", ["全部"] + all_kp, key="edu_ana_kp")
        sources = c4.multiselect("数据来源", ["答疑", "评审", "实训"],
                                 default=["答疑", "评审"], key="edu_ana_src")

    a = edu.aggregate_analytics(
        proj["id"], sources=sources,
        days={"近 7 天": 7, "近 30 天": 30}.get(days),
        kp_filter="" if kp == "全部" else kp)

    cols = st.columns(4)
    with cols[0]:
        _kpi("答疑记录", a["qa_count"], f"{a['student_answered']}/{a['student_total']} 名学生提问")
    with cols[1]:
        _kpi("作业评审", a["review_count"], f"{a['student_reviewed']}/{a['student_total']} 名学生已评")
    with cols[2]:
        _kpi("建议重点支持", len(a["need_remedial"]), f"依据：均分 < 60（{a['student_reviewed']} 份样本）",
             "warn")
    with cols[3]:
        _kpi("建议提供拓展任务", len(a["can_extend"]), "依据：均分 ≥ 85", "ok")

    if a["sample_warning"]:
        st.warning("当前样本量不足，以下内容仅作为教学参考，不应据此给学生贴标签。")

    if a["qa_count"] == 0 and a["review_count"] == 0:
        st.html(
            '<div class="fm-crs-empty"><div class="ic">📊</div>'
            "<h3>还没有学情数据</h3>"
            "<p>学生提问或提交作业并通过评审后，这里会自动汇总薄弱知识点与下一课建议。</p></div>"
        )
        c1, c2, _ = st.columns([1.4, 1.4, 3])
        with c1:
            if st.button("去学生答疑", key="ana_go_qa", use_container_width=True):
                ss.nav = "学生答疑"
                st.rerun()
        with c2:
            if st.button("去作业评审", key="ana_go_review", type="primary",
                         use_container_width=True):
                ss.nav = "作业评审"
                st.rerun()
        return

    t1, t2, t3, t4 = st.tabs(["高频知识点", "错误类型占比", "能力维度均分", "学习支持建议"])
    with t1:
        if a["knowledge_rows"]:
            _bars([{"label": r["knowledge_point"], "value": r["count"],
                    "note": f"{r['ratio']} 名学生"} for r in a["knowledge_rows"]])
            st.caption(f"数据来源：答疑 {a['qa_count']} 条")
        else:
            st.caption("暂无答疑数据")
        _render_kp_materials(proj, [r["knowledge_point"] for r in a["knowledge_rows"][:5]])
    with t2:
        if a["error_rows"]:
            _bars([{"label": r["error"], "value": r["percent"],
                    "note": f"{r['count']} 次"} for r in a["error_rows"]], suffix="%")
        else:
            st.caption("暂无错因数据")
    with t3:
        if a["dimension_rows"]:
            _bars([{"label": r["name"], "value": r["avg"], "note": f"{r['count']} 份样本"}
                   for r in a["dimension_rows"]], suffix=" 分")
        else:
            st.caption("暂无评审数据")
    with t4:
        _render_support(a)

    st.html('<div class="fm-sec-title">下一课方案</div>')
    disabled = a["qa_count"] == 0 and a["review_count"] == 0
    if disabled:
        st.caption("生成下一课方案不可用：当前筛选下没有答疑或评审数据。")
    if st.button("一键生成下一课方案", key="edu_next_gen", type="primary", disabled=disabled):
        try:
            with st.spinner("正在根据学情生成讲评课、补偿练习与拓展任务…"):
                plan = edu.generate_next_lesson(proj["id"], a)
            folder = _folder(proj)
            p = edu.save_artifact(folder, "下一课方案.docx",
                                  edu.export_next_docx(plan, proj["name"], a))
            db.save_task(kind="nextlesson", prompt=plan.get("prefill", {}).get("topic")
                         or "下一课方案", answer="已生成", project_id=proj["id"],
                         meta={"plan": plan, "analytics": a, "path": str(p)})
            ss["edu_next_plan"] = plan
            ss["edu_next_path"] = str(p)
            st.success("下一课方案已生成并保存到当前课程")
            st.rerun()
        except Exception as e:
            st.error(f"生成失败：{e}")

    plan = ss.get("edu_next_plan")
    if plan:
        _render_next_plan(proj, plan, a)
    _render_next_history(proj)


def _bars(rows: list[dict[str, Any]], suffix: str = "") -> None:
    top = max([float(r["value"] or 0) for r in rows] + [1])
    html_rows = []
    for r in rows:
        v = float(r["value"] or 0)
        width = max(3.0, min(100.0, v * 100 / top))
        html_rows.append(
            f'<div class="fm-bar"><div class="lb">{_esc(r["label"])}</div>'
            f'<div class="tr"><div class="fl" style="width:{width:.1f}%"></div></div>'
            f'<div class="vl">{_esc(r["value"])}{_esc(suffix)}</div>'
            f'<div class="nt">{_esc(r.get("note", ""))}</div></div>'
        )
    st.html('<div class="fm-bars">' + "".join(html_rows) + "</div>")


def _render_kp_materials(proj: dict[str, Any], kps: list[str]) -> None:
    if not kps:
        return
    files = db.list_files(project_id=proj["id"], limit=100)
    rows = []
    for kp in kps:
        hits = []
        for f in files:
            text = (db.get_file_text(f["id"]) or "")[:4000]
            if kp and kp[:4] in text:
                hits.append(f["name"])
        rows.append({"kp": kp, "src": "、".join(hits[:3]) or "未在课程资料中找到直接对应"})
    st.caption("薄弱知识点与课程资料的关联")
    _table(rows, [("kp", "知识点"), ("src", "关联资料")])


def _render_support(a: dict[str, Any]) -> None:
    ignored = ss.setdefault("edu_ana_ignored", set())
    need = [s for s in a["need_remedial"] if ("need", s) not in ignored]
    extend = [s for s in a["can_extend"] if ("ext", s) not in ignored]
    if len(need) != len(a["need_remedial"]) or len(extend) != len(a["can_extend"]):
        if st.button("恢复全部建议", key="edu_ana_restore"):
            ss["edu_ana_ignored"] = set()
            st.rerun()
    if need:
        st.markdown("**建议重点支持**")
        st.caption(f"依据：评审均分低于 60 分（{a['student_reviewed']} 份样本）。"
                   "这只是系统建议，不是学生标签。")
        for s in need:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"- {s}（均分 {a['student_scores'].get(s)}）")
            if c2.button("忽略", key=f"ignore_need_{s}"):
                ignored.add(("need", s))
                ss["edu_ana_ignored"] = ignored
                st.rerun()
    if extend:
        st.markdown("**建议提供拓展任务**")
        st.caption(f"依据：评审均分不低于 85 分（{a['student_reviewed']} 份样本）。")
        for s in extend:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"- {s}（均分 {a['student_scores'].get(s)}）")
            if c2.button("忽略", key=f"ignore_ext_{s}"):
                ignored.add(("ext", s))
                ss["edu_ana_ignored"] = ignored
                st.rerun()
    if not need and not extend:
        st.caption("暂无足够评审数据形成分层建议。")


def _render_next_plan(proj: dict[str, Any], plan: dict[str, Any],
                      analytics: dict[str, Any]) -> None:
    rl = plan.get("review_lesson") or {}
    st.markdown(f"**{rl.get('title') or '10 分钟讲评课'}（{rl.get('minutes', 10)} 分钟）**")
    _table([{"m": r.get("minutes", ""), "c": r.get("content", ""), "w": r.get("method", "")}
            for r in rl.get("outline") or []], [("m", "分钟"), ("c", "内容"), ("w", "方法")])
    st.markdown("**补偿练习**")
    for i, q in enumerate(plan.get("remedial_exercises") or [], 1):
        st.markdown(f"{i}. {q.get('q', '')}（针对：{q.get('target', '')}）")
        st.caption(f"答案：{q.get('answer', '')}")
    st.markdown("**拓展任务**")
    for i, q in enumerate(plan.get("extension_tasks") or [], 1):
        st.markdown(f"{i}. {q.get('title', '')}：{q.get('desc', '')}（适合：{q.get('target', '')}）")
    if plan.get("teacher_questions"):
        st.markdown("**需要教师重点追问的问题**")
        for s in plan["teacher_questions"]:
            st.markdown(f"- {s}")
    st.markdown("**教学顺序调整建议**")
    for s in plan.get("sequence_adjustment") or []:
        st.markdown(f"- {s}")
    st.markdown("**数据来源**")
    for s in plan.get("evidence") or []:
        st.markdown(f"- {s}")
    st.caption(f"统计口径：答疑 {analytics.get('qa_count', 0)} 条、评审 {analytics.get('review_count', 0)} 份、"
               f"学生 {analytics.get('student_total', 0)} 名")

    c1, c2 = st.columns(2)
    if c1.button("带入一键备课", key="edu_next_to_lesson", type="primary"):
        pf = plan.get("prefill") or {}
        ss["edu_lesson_prefill"] = {
            "topic": pf.get("topic") or "讲评课",
            "lesson_type": "讲评课",
            "objectives": pf.get("objectives") or [],
            "key_points": pf.get("key_points") or [],
            "materials": pf.get("materials") or [],
            "remedial": pf.get("remedial") or [],
            "outputs": ["教案", "PPT", "课堂练习", "答案与解析", "评分量规"],
        }
        ss["edu_lesson_pkg"] = {}
        ss.nav = "一键备课"
        st.rerun()
    with c2:
        _download("下载下一课方案 Word",
                  edu.export_next_docx(plan, proj["name"], analytics),
                  "下一课方案.docx", "dl_next_docx",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _render_next_history(proj: dict[str, Any]) -> None:
    tasks = db.list_tasks(project_id=proj["id"], kind="nextlesson", limit=10)
    if not tasks:
        return
    with st.expander(f"历史下一课方案（{len(tasks)}）"):
        for t in tasks:
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{_fmt_time(t['created_at'])} · {t['prompt']}")
            if c2.button("载入", key=f"next_load_{t['id']}"):
                plan = (t.get("meta") or {}).get("plan")
                if plan:
                    ss["edu_next_plan"] = plan
                    st.rerun()


# ---------------------------------------------------------------------------
# 学生空间：我的任务 / 教师反馈 / 错题回顾
# ---------------------------------------------------------------------------
def render_student_tasks_page() -> None:
    proj = _require_course(show_summary=False)
    if not proj:
        return
    _sec("我的任务", "教师已发布")
    pub = [t for t in db.list_tasks(project_id=proj["id"], kind="training", limit=100)
           if ((t.get("meta") or {}).get("pkg") or {}).get("status") == "published"]
    if not pub:
        st.html('<div class="fm-empty">老师还没有发布实训任务。发布后会出现在这里。</div>')
        return
    for t in pub:
        pkg = (t.get("meta") or {}).get("pkg") or {}
        with st.expander(f"{pkg.get('title') or t['prompt'][:30]}（已发布）", expanded=True):
            st.markdown(f"**背景**：{pkg.get('background', '')}")
            st.markdown(f"**角色**：{pkg.get('student_role', '')}｜**目标**：{pkg.get('goal', '')}")
            for title, key in (("Excel 要求", "excel_requirements"),
                               ("Word 交付物", "word_requirements"),
                               ("PPT 汇报", "ppt_requirements")):
                st.markdown(f"**{title}**")
                for it in pkg.get(key) or []:
                    st.markdown(f"- {it}")
            steps = pkg.get("data_tasks") or []
            if steps:
                _table([{"s": r.get("step", ""), "t": r.get("task", ""),
                         "d": r.get("deliverable", ""), "p": r.get("points", "")} for r in steps],
                       [("s", "步骤"), ("t", "任务"), ("d", "交付物"), ("p", "分值")])


def _my_published_reviews(proj: dict[str, Any]) -> list[dict[str, Any]]:
    name = student_name()
    if not name:
        return []
    return [t for t in db.list_tasks(project_id=proj["id"], kind="review", limit=200)
            if (t.get("meta") or {}).get("student") == name
            and (t.get("meta") or {}).get("status") == "published"]


def render_student_feedback_page() -> None:
    proj = _require_course(show_summary=False)
    if not proj:
        return
    name = student_name()
    _sec("教师反馈", name or "未填写学生身份")
    if not name:
        st.html('<div class="fm-empty">请先在顶部「当前用户」填写你的姓名或学号，'
                "才能查看对应的教师反馈。</div>")
        return
    records = _my_published_reviews(proj)
    if not records:
        st.html('<div class="fm-empty">还没有已发布的作业反馈。教师发布后会出现在这里。</div>')
        return
    rows = []
    for t in records:
        m = t.get("meta") or {}
        rows.append({"task": m.get("task") or t["prompt"],
                     "final": m.get("final_total", ""),
                     "ai": (m.get("ai") or {}).get("total", ""),
                     "time": _fmt_time(t["created_at"])})
    _table(rows, [("task", "任务"), ("final", "最终得分"), ("ai", "AI 初评分"),
                  ("time", "发布时间")])
    for t in records:
        m = t.get("meta") or {}
        with st.expander(f"{m.get('task') or t['prompt']} · 教师评语"):
            st.markdown((m.get("teacher") or {}).get("comment") or "（无评语）")
            for d in (m.get("ai") or {}).get("dimensions") or []:
                st.markdown(f"- **{d.get('name', '')}**：{d.get('score', 0)}/{d.get('max', 0)} · "
                            f"{d.get('suggestion', '')}")


def render_student_wrong_page() -> None:
    proj = _require_course(show_summary=False)
    if not proj:
        return
    name = student_name()
    _sec("错题回顾", name or "未填写学生身份")
    if not name:
        st.html('<div class="fm-empty">请先在顶部「当前用户」填写你的姓名或学号，'
                "才能查看对应的错题记录。</div>")
        return
    agg: dict[str, dict[str, Any]] = {}
    for t in _my_published_reviews(proj):
        for d in (t.get("meta") or {}).get("ai", {}).get("dimensions") or []:
            max_s = float(d.get("max") or 0)
            score = float(d.get("score") or 0)
            if max_s <= 0:
                continue
            rate = score / max_s
            if rate >= 0.8:
                continue
            row = agg.setdefault(d.get("name", "未命名维度"),
                                 {"name": d.get("name", "未命名维度"), "times": 0,
                                  "rate": 0.0, "advice": d.get("suggestion", "")})
            row["times"] += 1
            row["rate"] += rate
            if d.get("suggestion"):
                row["advice"] = d["suggestion"]
    if not agg:
        st.html('<div class="fm-empty">暂无明显薄弱点。继续保持，或等待教师发布新的作业反馈。</div>')
        return
    st.html('<div class="fm-sec-title">薄弱知识点 / 维度</div>')
    rows = []
    for r in sorted(agg.values(), key=lambda x: x["rate"] / max(x["times"], 1)):
        rows.append({"kp": r["name"], "times": r["times"],
                     "rate": f'{r["rate"] / r["times"] * 100:.0f}%',
                     "advice": r["advice"] or "建议复习对应课程资料并重做同类练习。"})
    _table(rows, [("kp", "知识点 / 维度"), ("times", "出现次数"), ("rate", "平均得分率"),
                  ("advice", "改进建议")])
