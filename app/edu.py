"""教育模式核心能力：课程上下文、生成式教学产出、Office 交付物导出。

设计约定：
- 所有生成内容只基于当前课程项目的信息与资料，不编造教材页码；
- 生成结果统一为 dict，键名固定，供 UI 与导出复用；
- 导出文件（docx / pptx / xlsx）全部用真实 Office 库写入，教师可直接打开修改。
"""
from __future__ import annotations

import io
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app import db
from app.config import ROOT, ZHIPU_API_KEY

TMP_DIR = (ROOT / ".data" / "tmp").resolve()
TMP_DIR.mkdir(parents=True, exist_ok=True)

VISIBILITY_LABEL = {"teacher": "教师可见", "student": "学生可见", "both": "师生可见"}
CATEGORIES = ["教材", "课件", "试题", "案例", "答案", "评分标准", "作业", "作答", "其他"]
LESSON_TYPES = ["新授课", "复习课", "实训课", "讲评课"]
LESSON_OUTPUTS = ["教案", "PPT", "课堂练习", "答案与解析", "分层作业", "评分量规",
                  "教学目标对齐表", "教师讲稿"]


# ---------------------------------------------------------------------------
# 通用：模型调用与 JSON 解析
# ---------------------------------------------------------------------------
def _llm():
    from app.agent import build_llm
    return build_llm()


def _invoke(system: str, human: str) -> str:
    llm = _llm()
    msg = llm.invoke([("system", system), ("human", human)])
    return str(getattr(msg, "content", msg))


def parse_json(text: str) -> dict[str, Any]:
    """从模型输出中提取第一个 JSON 对象（容忍 ```json 包裹）。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("模型未返回 JSON")
    return json.loads(t[start:end + 1])


def _json_call(system: str, human: str) -> dict[str, Any]:
    raw = _invoke(system, human)
    try:
        return parse_json(raw)
    except Exception:
        # 再试一次：明确要求仅输出 JSON
        raw2 = _invoke(system, human + "\n\n再次强调：只输出一个 JSON 对象，不要解释、不要 Markdown 代码块。")
        return parse_json(raw2)


# ---------------------------------------------------------------------------
# 课程资料文本抽取
# ---------------------------------------------------------------------------
def extract_text(name: str, data: bytes) -> tuple[str, dict[str, Any]]:
    """把上传文件转成正文文本 + 元信息。失败时返回空文本并给出原因。"""
    ext = Path(name).suffix.lower()
    meta: dict[str, Any] = {"ext": ext.upper().lstrip("."), "rows": 0, "cols": 0, "chars": 0}
    try:
        if ext in (".txt", ".md", ".html", ".htm"):
            text = data.decode("utf-8", errors="ignore")
            meta["chars"] = len(text)
            return text, meta

        if ext in (".csv", ".xlsx", ".xls"):
            import pandas as pd
            bio = io.BytesIO(data)
            if ext == ".csv":
                df = pd.read_csv(bio)
                meta["rows"], meta["cols"] = int(df.shape[0]), int(df.shape[1])
                text = f"表格 {name}（{meta['rows']} 行 × {meta['cols']} 列）\n列名：{list(df.columns)}\n" \
                       + df.head(30).to_csv(index=False)
            else:
                sheets = pd.read_excel(bio, sheet_name=None)
                parts, first = [], None
                for sn, sdf in sheets.items():
                    if first is None:
                        first = sdf
                    parts.append(f"工作表「{sn}」：{sdf.shape[0]} 行 × {sdf.shape[1]} 列，列名 {list(sdf.columns)}\n"
                                 + sdf.head(15).to_csv(index=False))
                if first is not None:
                    meta["rows"], meta["cols"] = int(first.shape[0]), int(first.shape[1])
                text = "\n\n".join(parts)
            meta["chars"] = len(text)
            return text, meta

        if ext == ".docx":
            import docx
            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for tb in d.tables:
                for row in tb.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            text = "\n".join(parts)
            meta["chars"] = len(text)
            return text, meta

        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(io.BytesIO(data))
            parts = []
            for i, slide in enumerate(prs.slides, 1):
                line = [f"第{i}页"]
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text_frame.text.strip():
                        line.append(shape.text_frame.text.strip())
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                    line.append("讲稿：" + slide.notes_slide.notes_text_frame.text.strip())
                parts.append("\n".join(line))
            text = "\n\n".join(parts)
            meta["chars"] = len(text)
            return text, meta

        if ext in (".pdf", ".png", ".jpg", ".jpeg") and ZHIPU_API_KEY:
            from app.zhipu_parser import parse_sync
            tmp = TMP_DIR / f"edu_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext}"
            tmp.write_bytes(data)
            try:
                res = parse_sync(tmp, tool_type="lite")
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if res.get("status") == "ok":
                text = res.get("text", "")
                meta["chars"] = len(text)
                return text, meta
            meta["note"] = res.get("error", "解析失败")
            return "", meta

        meta["note"] = "该格式暂不解析正文，仅保存文件"
        return "", meta
    except Exception as e:
        meta["note"] = f"解析失败：{e.__class__.__name__}: {e}"
        return "", meta


def course_context(project_id: int | None, *, student_mode: bool = False,
                   max_chars: int = 7000,
                   file_ids: list[int] | None = None,
                   ai_only: bool = True) -> str:
    """拼装课程上下文：课程信息 + 资料清单 + 资料正文摘要。

    - student_mode：只使用 visibility in (student, both) 的资料；
    - file_ids：只使用指定资料（None=全部）；
    - ai_only：跳过「参与 AI 上下文」开关关闭的资料。
    """
    if not project_id:
        return ""
    p = db.get_project(int(project_id))
    if not p:
        return ""
    lines = [
        f"课程名称：{p.get('name') or ''}",
        f"授课对象：{p.get('audience') or '未填写'}",
        f"班级：{p.get('class_name') or '未填写'}",
        f"课时安排：{p.get('hours') or '未填写'}",
        f"学习目标：{p.get('objectives') or '未填写'}",
        f"教学重点：{p.get('key_points') or '未填写'}",
        f"教学难点：{p.get('difficulties') or '未填写'}",
        f"当前进度：{p.get('progress') or '未填写'}",
        f"教材版本：{p.get('textbook_version') or '未填写'}",
        f"课程版本：{p.get('version') or 'v1'}",
    ]
    if p.get("description"):
        lines.append(f"课程说明：{p['description']}")
    files = db.list_files(project_id=int(project_id),
                          visibility="student" if student_mode else None, limit=60)
    if file_ids is not None:
        allow = {int(x) for x in file_ids}
        files = [f for f in files if int(f["id"]) in allow]
    if ai_only:
        files = [f for f in files if int(f.get("ai_context", 1) or 0) == 1]
    if files:
        lines.append("\n可用课程资料（只能引用这里的资料，不得编造页码或章节）：")
        budget = max_chars
        for f in files:
            vis = VISIBILITY_LABEL.get(f.get("visibility", "teacher"), "教师可见")
            lines.append(f"- {f['name']}｜{f.get('category') or '未分类'}｜{vis}")
            text = (db.get_file_text(f["id"]) or "").strip()
            if text and budget > 0:
                snippet = text[: min(len(text), max(400, budget // max(len(files), 1)))]
                budget -= len(snippet)
                lines.append(f"  正文摘录：{snippet}")
    else:
        lines.append("\n当前课程没有可用于 AI 的资料。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 提示词公共约束
# ---------------------------------------------------------------------------
_BASE_RULE = (
    "你是一名资深职业教育教研员。所有内容必须基于给定的课程上下文；"
    "上下文没有的信息（如教材页码、章节号）不要编造，统一写“未提供，可按教材补充”。"
    "输出必须是合法 JSON，不要使用 Markdown 代码块，不要输出 JSON 之外的任何文字。"
)


# ---------------------------------------------------------------------------
# 1) 一键备课包
# ---------------------------------------------------------------------------
def generate_lesson_package(project_id: int, topic: str, extra: str = "", *,
                            lesson_type: str = "新授课", hours: str = "1 课时",
                            student_level: str = "", style: str = "",
                            outputs: list[str] | None = None,
                            file_ids: list[int] | None = None,
                            model: str = "", review_model: str = "",
                            dual_check: bool = False) -> dict[str, Any]:
    ctx = course_context(project_id, file_ids=file_ids)
    outs = outputs or list(LESSON_OUTPUTS)
    human = f"""请为下面这节课生成完整备课包。

课程上下文：
{ctx}

本次课题：{topic}
课型：{lesson_type}
课时：{hours}
学生基础：{student_level or '未填写'}
教学风格/活动要求：{style or '无'}
需要产出的成果：{'、'.join(outs)}
教师补充要求：{extra or '无'}

严格按以下 JSON 结构输出（数组按内容需要增减，但键必须存在）：
{{
  "topic": "课题",
  "flow45": [{{"time": "0-5 分钟", "phase": "导入", "activity": "具体活动", "goal": "达成目标"}}],
  "lesson_plan": {{
    "objectives": ["知识目标", "能力目标", "素养目标"],
    "key_points": ["重点"],
    "difficulties": ["难点"],
    "preparation": ["教师准备", "学生准备"],
    "steps": [{{"phase": "环节", "minutes": 8, "teacher": "教师活动", "student": "学生活动", "design_intent": "设计意图"}}],
    "homework": "作业布置"
  }},
  "ppt": {{"title": "课件标题", "slides": [{{"title": "页标题", "bullets": ["要点1", "要点2"], "notes": "逐页讲稿，150 字以内"}}]}},
  "questions": {{
    "basic": [{{"q": "基础题", "answer": "答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}],
    "applied": [{{"q": "应用题", "answer": "答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}],
    "extension": [{{"q": "拓展题", "answer": "参考答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}]
  }},
  "alignment": [{{"knowledge_point": "知识点", "objective": "对应目标", "activity": "对应活动", "assessment": "评价方式"}}],
  "rubric": [{{"dimension": "评分维度", "weight": 30, "excellent": "优秀标准", "good": "良好标准", "pass": "合格标准", "fail": "待改进标准"}}],
  "sources": [{{"content": "教案/PPT/题目", "source": "引用的资料名或“课程通用要求”"}}]
}}

要求：45 分钟流程 5-7 个环节；PPT 8-12 页；每类题 2 道；评分标准总分 100。
alignment 必须覆盖 lesson_plan.objectives 中的每一条目标：按知识点拆分时可以拆成多行，
但 objective 字段要直接复制对应的目标原文（同一目标可出现在多行），不要改写措辞。
另外输出 "checks" 字段，对以下 6 项给出 true/false：objectives_covered、qa_matched、
out_of_scope、consistent、untraceable（true 表示存在无法追溯的资料）。"""
    data = _json_call(_BASE_RULE, human)
    data.setdefault("topic", topic)
    data["meta"] = {"lesson_type": lesson_type, "hours": hours, "student_level": student_level,
                    "style": style, "outputs": outs, "model": model or "默认",
                    "review_model": review_model or "", "dual_check": bool(dual_check)}
    data["checks"] = lesson_checks(data)
    return data


_SECTION_PROMPT = {
    "lesson_plan": '{"objectives":["..."],"key_points":["..."],"difficulties":["..."],'
                   '"preparation":["..."],"steps":[{"phase":"","minutes":8,"teacher":"",'
                   '"student":"","design_intent":""}],"homework":""}',
    "ppt": '{"title":"","slides":[{"title":"","bullets":[""],"notes":""}]}',
    "questions": '{"basic":[{"q":"","answer":"","hint1":"","hint2":""}],'
                 '"applied":[...],"extension":[...]}',
    "rubric": '[{"dimension":"","weight":25,"excellent":"","good":"","pass":"","fail":""}]',
}


def regenerate_section(project_id: int, pkg: dict[str, Any], section: str) -> dict[str, Any]:
    """只重新生成备课包中的某一项成果，其余内容保持不变。"""
    if section not in _SECTION_PROMPT:
        raise ValueError("该成果不支持单独重新生成")
    ctx = course_context(project_id)
    human = f"""只重写备课包中的「{section}」这一项，其他内容保持不变。

课程上下文：
{ctx}

课题：{pkg.get('topic') or ''}

输出 JSON（只输出该字段对应的值，键名必须是 {section}）：
{{"{section}": {_SECTION_PROMPT[section]}}}"""
    data = _json_call(_BASE_RULE, human)
    value = data.get(section)
    if value in (None, "", [], {}):
        raise RuntimeError("模型未返回该项内容")
    pkg[section] = value
    pkg["checks"] = lesson_checks(pkg)
    return pkg


_OBJ_LABEL = re.compile(r"^(知识目标|能力目标|素养目标|教学目标)[：:]\s*")
_NON_WORD = re.compile(r"[^\u4e00-\u9fa5A-Za-z0-9]+")


def _norm_obj(s: Any) -> str:
    """归一化目标文本：去掉「知识目标：」类前缀与标点空白，便于比对。"""
    return _NON_WORD.sub("", _OBJ_LABEL.sub("", str(s or "")))


def _bigrams(s: str) -> set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def objective_coverage(objectives: list[str],
                       alignment: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐个目标判断是否被对齐表覆盖。

    对齐表通常按知识点拆成多行且会改写措辞，整句子串匹配会产生误报，
    因此改为：原文包含 → 覆盖；否则字符二元组覆盖率 ≥ 0.35 → 覆盖。
    """
    rows = [x for x in (_norm_obj(r.get("objective")) for r in alignment) if x]
    rows += [x for x in (_norm_obj(r.get("knowledge_point")) for r in alignment) if x]
    union: set[str] = set()
    for r in rows:
        union |= _bigrams(r)
    out: list[dict[str, Any]] = []
    for o in objectives:
        no = _norm_obj(o)
        exact = any(
            no and (no in r or (len(r) >= max(8, len(no) // 2) and r in no))
            for r in rows
        )
        grams = _bigrams(no)
        cov = (len(grams & union) / len(grams)) if grams else 0.0
        out.append({"objective": o, "covered": bool(exact or cov >= 0.35),
                    "coverage": round(cov, 2)})
    return out


def lesson_checks(pkg: dict[str, Any]) -> dict[str, Any]:
    """对备课包做 6 项一致性检查（本地可复算，模型结果只作参考）。"""
    lp = pkg.get("lesson_plan") or {}
    alignment = pkg.get("alignment") or []
    questions = pkg.get("questions") or {}
    rubric = pkg.get("rubric") or []
    sources = pkg.get("sources") or []
    raw = pkg.get("checks") or {}

    objectives = [str(x).strip() for x in (lp.get("objectives") or []) if str(x).strip()]
    coverage = objective_coverage(objectives, alignment)
    missing = [c["objective"] for c in coverage if not c["covered"]]
    covered = bool(objectives) and not missing

    q_items = [q for k in ("basic", "applied", "extension") for q in (questions.get(k) or [])]
    qa_matched = bool(q_items) and all(str(q.get("answer") or "").strip() for q in q_items)

    total = sum(int(r.get("weight") or 0) for r in rubric)
    untraceable = any(not str(s.get("source") or "").strip() for s in sources)
    consistent = bool(pkg.get("flow45")) and bool((pkg.get("ppt") or {}).get("slides")) and bool(q_items)
    # 超纲判断：优先用结构化结论；关键词兜底时排除 checks 自身（其标签含“超纲”，会自我命中）
    if "out_of_scope" in raw:
        out_of_scope = bool(raw.get("out_of_scope"))
    else:
        body = {k: v for k, v in pkg.items() if k != "checks"}
        text = json.dumps(body, ensure_ascii=False)
        out_of_scope = "超纲" in text

    items = [
        {"key": "objectives_covered", "label": "教学目标是否全部覆盖",
         "ok": covered,
         "detail": "对齐表已覆盖全部教学目标" if covered else
                   "未覆盖目标：" + "；".join(m[:24] for m in missing[:2])},
        {"key": "qa_matched", "label": "练习与答案是否匹配",
         "ok": qa_matched, "detail": "题目均有答案" if qa_matched else "存在缺少答案的题目"},
        {"key": "out_of_scope", "label": "是否存在超纲内容",
         "ok": not out_of_scope, "detail": "未发现超纲表述" if not out_of_scope else "检测到超纲内容，请人工核对"},
        {"key": "consistent", "label": "教案、PPT 与练习是否一致",
         "ok": consistent, "detail": "三件套结构完整" if consistent else "存在缺失的成果项"},
        {"key": "rubric_total", "label": "评分量规总分是否为 100",
         "ok": total == 100, "detail": f"当前总分 {total}"},
        {"key": "untraceable", "label": "是否存在无法追溯的资料",
         "ok": not untraceable, "detail": "全部引用可追溯" if not untraceable else "有引用未标注来源"},
    ]
    return {"ok": all(i["ok"] for i in items), "items": items,
            "rubric_total": total,
            "objectives_covered": covered, "objective_coverage": coverage,
            "qa_matched": qa_matched,
            "out_of_scope": out_of_scope, "consistent": consistent,
            "untraceable": untraceable}


def export_lesson_docx(pkg: dict[str, Any], course: str) -> bytes:
    import docx
    from docx.shared import Pt
    d = docx.Document()
    _docx_base_style(d)

    d.add_heading(f"《{pkg.get('topic', '')}》备课包", 0)
    d.add_paragraph(f"课程：{course}｜生成时间：{datetime.now():%Y-%m-%d %H:%M}")

    d.add_heading("一、45 分钟教学流程", 1)
    t = d.add_table(rows=1, cols=4)
    _docx_table_header(t, ["时间", "环节", "活动", "目标"])
    for r in pkg.get("flow45") or []:
        cells = t.add_row().cells
        for c, k in zip(cells, ("time", "phase", "activity", "goal")):
            c.text = str(r.get(k, ""))

    lp = pkg.get("lesson_plan") or {}
    d.add_heading("二、教案", 1)
    for title, key in (("教学目标", "objectives"), ("教学重点", "key_points"),
                       ("教学难点", "difficulties"), ("课前准备", "preparation")):
        d.add_heading(title, 2)
        for it in lp.get(key) or []:
            d.add_paragraph(str(it), style="List Bullet")
    d.add_heading("教学过程", 2)
    t2 = d.add_table(rows=1, cols=5)
    _docx_table_header(t2, ["环节", "时长", "教师活动", "学生活动", "设计意图"])
    for s in lp.get("steps") or []:
        cells = t2.add_row().cells
        for c, k in zip(cells, ("phase", "minutes", "teacher", "student", "design_intent")):
            c.text = str(s.get(k, ""))
    if lp.get("homework"):
        d.add_heading("作业布置", 2)
        d.add_paragraph(str(lp["homework"]))

    ppt = pkg.get("ppt") or {}
    d.add_heading("三、PPT 大纲与逐页讲稿", 1)
    for i, s in enumerate(ppt.get("slides") or [], 1):
        d.add_heading(f"第 {i} 页 · {s.get('title', '')}", 2)
        for b in s.get("bullets") or []:
            d.add_paragraph(str(b), style="List Bullet")
        if s.get("notes"):
            d.add_paragraph(f"讲稿：{s['notes']}")

    d.add_heading("四、练习题、答案与分层提示", 1)
    qn = {"basic": "基础题", "applied": "应用题", "extension": "拓展题"}
    for key, label in qn.items():
        d.add_heading(label, 2)
        for i, q in enumerate((pkg.get("questions") or {}).get(key) or [], 1):
            d.add_paragraph(f"{i}. {q.get('q', '')}")
            d.add_paragraph(f"答案：{q.get('answer', '')}")
            d.add_paragraph(f"提示1：{q.get('hint1', '')}")
            d.add_paragraph(f"提示2：{q.get('hint2', '')}")

    d.add_heading("五、知识点与教学目标对齐表", 1)
    t3 = d.add_table(rows=1, cols=4)
    _docx_table_header(t3, ["知识点", "对应目标", "对应活动", "评价方式"])
    for r in pkg.get("alignment") or []:
        cells = t3.add_row().cells
        for c, k in zip(cells, ("knowledge_point", "objective", "activity", "assessment")):
            c.text = str(r.get(k, ""))

    d.add_heading("六、评分标准", 1)
    t4 = d.add_table(rows=1, cols=6)
    _docx_table_header(t4, ["维度", "权重", "优秀", "良好", "合格", "待改进"])
    for r in pkg.get("rubric") or []:
        cells = t4.add_row().cells
        for c, k in zip(cells, ("dimension", "weight", "excellent", "good", "pass", "fail")):
            c.text = str(r.get(k, ""))

    d.add_heading("七、资料来源", 1)
    for s in pkg.get("sources") or []:
        d.add_paragraph(f"{s.get('content', '')} ← {s.get('source', '')}", style="List Bullet")

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def export_lesson_pptx(pkg: dict[str, Any], course: str) -> bytes:
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation()
    prs.slide_width = 12192000  # 16:9
    prs.slide_height = 6858000
    ppt = pkg.get("ppt") or {}

    s0 = prs.slides.add_slide(prs.slide_layouts[0])
    s0.shapes.title.text = ppt.get("title") or pkg.get("topic", "课程课件")
    s0.placeholders[1].text = f"{course}｜致壹教育工作台生成"

    for s in ppt.get("slides") or []:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = str(s.get("title", ""))
        tf = slide.placeholders[1].text_frame
        tf.clear()
        bullets = s.get("bullets") or [""]
        for i, b in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = str(b)
            p.font.size = Pt(20)
        if s.get("notes"):
            slide.notes_slide.notes_text_frame.text = str(s["notes"])

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def export_lesson_xlsx(pkg: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "题目与答案"
    ws.append(["类型", "题目", "答案", "提示1", "提示2"])
    for key, label in (("basic", "基础题"), ("applied", "应用题"), ("extension", "拓展题")):
        for q in (pkg.get("questions") or {}).get(key) or []:
            ws.append([label, q.get("q", ""), q.get("answer", ""), q.get("hint1", ""), q.get("hint2", "")])
    ws2 = wb.create_sheet("评分标准")
    ws2.append(["维度", "权重", "优秀", "良好", "合格", "待改进"])
    for r in pkg.get("rubric") or []:
        ws2.append([r.get("dimension", ""), r.get("weight", ""), r.get("excellent", ""),
                    r.get("good", ""), r.get("pass", ""), r.get("fail", "")])
    for ws_ in (ws, ws2):
        for col in ws_.columns:
            width = max(len(str(c.value or "")) for c in col)
            ws_.column_dimensions[col[0].column_letter].width = min(max(12, width * 1.6), 60)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 2) 引导式答疑
# ---------------------------------------------------------------------------
_TUTOR_STAGES = ["diagnose", "hint", "steps", "summary"]


_ACTION_STAGE = {"hint": 1, "stuck": 2, "try": 0}


def tutor_reply(project_id: int | None, question: str, history: list[dict[str, str]],
                stage_index: int, student_mode: bool = True,
                action: str | None = None) -> dict[str, Any]:
    """按「定位知识点 → 第一层提示 → 关键步骤 → 要求总结」四步响应。

    action: hint=给我一点提示 / stuck=我还是不会 / try=我想自己试试。
    """
    ctx = course_context(project_id, student_mode=student_mode)
    idx = _ACTION_STAGE[action] if action in _ACTION_STAGE else stage_index
    if action == "try":
        idx = max(1, min(idx, 2))
    stage = _TUTOR_STAGES[min(idx, len(_TUTOR_STAGES) - 1)]
    dialogs = "\n".join(f"{m.get('role')}: {m.get('text')}" for m in history[-8:])
    human = f"""课程上下文：
{ctx}

学生提交的问题（或题目）：
{question}

此前对话：
{dialogs or '（无）'}

当前应处的引导阶段：{stage}（diagnose=判断卡点并给第一层提示；hint=更具体的第二层提示；steps=给出关键步骤但不给最终答案；summary=要求学生复述方法）

规则：
- 绝不直接给出最终答案或完整解题过程；
- 先指出学生可能的卡点，再给提示；
- 每次只解决一个障碍，用提问引导学生自己完成；
- 只使用课程允许学生看到的资料，并说明引用了哪份资料；
- 若题目信息不足，先请学生补充已知条件；
- 不确定或超出资料范围时，把 need_teacher 设为 true，建议教师接管。

输出 JSON：
{{
  "knowledge_point": "学生卡住的知识点",
  "stage": "{stage}",
  "feedback": "本阶段给学生的引导内容（可直接展示）",
  "question_to_student": "向学生提出的下一步问题",
  "error_type": "概念不清|计算失误|审题偏差|方法缺失|表达不规范|其他",
  "sources": ["引用的课程资料名"],
  "need_teacher": false,
  "summary_prompt": "让学生用自己的话总结的一句话要求"
}}"""
    data = _json_call(_BASE_RULE, human)
    data["stage"] = stage
    return data


def tutor_full_answer(project_id: int | None, question: str,
                      history: list[dict[str, str]]) -> dict[str, Any]:
    """学生完成尝试后才可调用的完整解析（仅使用学生可见资料）。"""
    ctx = course_context(project_id, student_mode=True)
    dialogs = "\n".join(f"{m.get('role')}: {m.get('text')}" for m in history[-10:])
    human = f"""学生已经做过尝试，现在需要完整解析。

课程上下文：
{ctx}

学生问题：
{question}

对话记录：
{dialogs or '（无）'}

输出 JSON：
{{
  "knowledge_point": "知识点",
  "solution": "完整解析（分步骤，每步说明依据）",
  "answer": "最终答案",
  "sources": ["引用的课程资料名"],
  "similar_question": {{"q": "类似练习", "answer": "参考答案", "hint": "一句提示"}},
  "error_type": "错因标签"
}}

要求：只使用学生可见资料；解析要能对应到学生刚才卡住的步骤；不得出现教师内部评分标准。"""
    return _json_call(_BASE_RULE, human)


# ---------------------------------------------------------------------------
# 3) 实训任务生成
# ---------------------------------------------------------------------------
def generate_training(project_id: int, scenario: str, extra: str = "") -> dict[str, Any]:
    ctx = course_context(project_id)
    human = f"""把下面这个真实工作场景转化为一份可执行的课程实训任务。

课程上下文：
{ctx}

教师输入的工作场景：{scenario}
补充要求：{extra or '无'}

输出 JSON：
{{
  "title": "实训名称",
  "background": "实训背景（真实业务情境）",
  "student_role": "学生扮演的角色",
  "goal": "实训目标",
  "materials": [{{"name": "资料/数据名称", "purpose": "用途", "format": "xlsx/docx/pptx"}}],
  "data_tasks": [{{"step": 1, "task": "任务描述", "excel_requirement": "Excel 分析要求", "deliverable": "交付物", "points": 20}}],
  "excel_requirements": ["具体要求"],
  "word_requirements": ["一页经营建议的结构要求"],
  "ppt_requirements": ["五分钟汇报的页数与内容要求"],
  "rubric": [{{"dimension": "维度", "weight": 25, "excellent": "优秀", "good": "良好", "pass": "合格", "fail": "待改进"}}],
  "common_errors": [{{"error": "学生常见错误", "why": "原因", "prevention": "预防方式"}}],
  "timeline": [{{"phase": "阶段", "minutes": 30, "output": "阶段产出"}}]
}}

要求：分步骤任务单 4-6 步；评分量规总分 100；常见错误 4-6 条。"""
    data = _json_call(_BASE_RULE, human)
    data.setdefault("title", scenario[:40])
    return data


def export_training_docx(pkg: dict[str, Any], course: str) -> bytes:
    import docx
    d = docx.Document()
    _docx_base_style(d)
    d.add_heading(f"实训任务单：{pkg.get('title', '')}", 0)
    d.add_paragraph(f"课程：{course}｜生成时间：{datetime.now():%Y-%m-%d %H:%M}")

    for title, key in (("实训背景", "background"), ("学生角色", "student_role"), ("实训目标", "goal")):
        d.add_heading(title, 1)
        d.add_paragraph(str(pkg.get(key, "")))

    d.add_heading("可用资料与模拟数据", 1)
    t = d.add_table(rows=1, cols=3)
    _docx_table_header(t, ["名称", "用途", "格式"])
    for m in pkg.get("materials") or []:
        cells = t.add_row().cells
        for c, k in zip(cells, ("name", "purpose", "format")):
            c.text = str(m.get(k, ""))

    d.add_heading("分步骤任务单", 1)
    t2 = d.add_table(rows=1, cols=5)
    _docx_table_header(t2, ["步骤", "任务", "Excel 要求", "交付物", "分值"])
    for r in pkg.get("data_tasks") or []:
        cells = t2.add_row().cells
        for c, k in zip(cells, ("step", "task", "excel_requirement", "deliverable", "points")):
            c.text = str(r.get(k, ""))

    for title, key in (("Excel 数据分析要求", "excel_requirements"),
                       ("Word 交付物格式", "word_requirements"),
                       ("PPT 汇报要求", "ppt_requirements")):
        d.add_heading(title, 1)
        for it in pkg.get(key) or []:
            d.add_paragraph(str(it), style="List Bullet")

    d.add_heading("评分量规（100 分）", 1)
    t3 = d.add_table(rows=1, cols=6)
    _docx_table_header(t3, ["维度", "权重", "优秀", "良好", "合格", "待改进"])
    for r in pkg.get("rubric") or []:
        cells = t3.add_row().cells
        for c, k in zip(cells, ("dimension", "weight", "excellent", "good", "pass", "fail")):
            c.text = str(r.get(k, ""))

    d.add_heading("学生常见错误预测", 1)
    t4 = d.add_table(rows=1, cols=3)
    _docx_table_header(t4, ["常见错误", "原因", "预防方式"])
    for r in pkg.get("common_errors") or []:
        cells = t4.add_row().cells
        for c, k in zip(cells, ("error", "why", "prevention")):
            c.text = str(r.get(k, ""))

    if pkg.get("timeline"):
        d.add_heading("实训时间线", 1)
        t5 = d.add_table(rows=1, cols=3)
        _docx_table_header(t5, ["阶段", "分钟", "产出"])
        for r in pkg["timeline"]:
            cells = t5.add_row().cells
            for c, k in zip(cells, ("phase", "minutes", "output")):
                c.text = str(r.get(k, ""))

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def export_training_pptx(pkg: dict[str, Any], course: str) -> bytes:
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation()
    prs.slide_width = 12192000
    prs.slide_height = 6858000

    s0 = prs.slides.add_slide(prs.slide_layouts[0])
    s0.shapes.title.text = pkg.get("title", "实训任务")
    s0.placeholders[1].text = f"{course}｜实训说明"

    def _add(title: str, bullets: list[str]):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        tf = slide.placeholders[1].text_frame
        tf.clear()
        for i, b in enumerate(bullets[:8] or [""]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = str(b)
            p.font.size = Pt(18)

    _add("实训背景与角色", [pkg.get("background", ""), f"角色：{pkg.get('student_role', '')}",
                        f"目标：{pkg.get('goal', '')}"])
    _add("任务步骤", [f"{r.get('step')}. {r.get('task')}（{r.get('points', '')} 分）"
                   for r in (pkg.get("data_tasks") or [])])
    _add("Excel 分析要求", [str(x) for x in (pkg.get("excel_requirements") or [])])
    _add("Word 交付物要求", [str(x) for x in (pkg.get("word_requirements") or [])])
    _add("PPT 汇报要求", [str(x) for x in (pkg.get("ppt_requirements") or [])])
    _add("评分量规", [f"{r.get('dimension')}：{r.get('weight')} 分" for r in (pkg.get("rubric") or [])])

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def export_training_xlsx(pkg: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "任务单"
    ws.append(["步骤", "任务", "Excel 要求", "交付物", "分值"])
    for r in pkg.get("data_tasks") or []:
        ws.append([r.get("step"), r.get("task"), r.get("excel_requirement"),
                   r.get("deliverable"), r.get("points")])
    ws2 = wb.create_sheet("评分量规")
    ws2.append(["维度", "权重", "优秀", "良好", "合格", "待改进"])
    for r in pkg.get("rubric") or []:
        ws2.append([r.get("dimension"), r.get("weight"), r.get("excellent"),
                    r.get("good"), r.get("pass"), r.get("fail")])
    ws3 = wb.create_sheet("常见错误")
    ws3.append(["常见错误", "原因", "预防方式"])
    for r in pkg.get("common_errors") or []:
        ws3.append([r.get("error"), r.get("why"), r.get("prevention")])
    for ws_ in (ws, ws2, ws3):
        for col in ws_.columns:
            width = max(len(str(c.value or "")) for c in col)
            ws_.column_dimensions[col[0].column_letter].width = min(max(12, width * 1.6), 60)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 4) 作业评审
# ---------------------------------------------------------------------------
def evaluate_submission(project_id: int | None, submission_text: str, file_name: str,
                        rubric: list[dict[str, Any]] | None = None,
                        student: str = "") -> dict[str, Any]:
    ctx = course_context(project_id)
    rubric_txt = "\n".join(
        f"- {r.get('dimension')}（{r.get('weight')} 分）：优秀={r.get('excellent')}；良好={r.get('good')}；"
        f"合格={r.get('pass')}；待改进={r.get('fail')}"
        for r in (rubric or [])
    ) or "未提供量规，请按内容完整性、数据准确性、表达规范、结论可行性四个维度各 25 分设计。"
    human = f"""请评审学生提交的作业，必须给出可核对的证据与修改建议，不能只给总分。

课程上下文：
{ctx}

评分量规：
{rubric_txt}

学生：{student or '未填写'}
提交文件：{file_name}
提交内容（正文/表格摘要）：
{submission_text[:9000]}

输出 JSON：
{{
  "total": 0,
  "dimensions": [
    {{"name": "维度名", "max": 25, "score": 0, "evidence": "逐字引用学生内容中的证据（引用不到就写“未找到相关表述”）", "suggestion": "具体修改建议", "location": "第几页/哪个工作表/哪一段"}}
  ],
  "strengths": ["优点"],
  "improvements": ["必须改进点"],
  "summary": "教师可直接使用的总评语（120 字以内）"
}}

要求：score 不得超过 max；total 等于各维度得分之和；evidence 必须可定位，不允许编造内容。"""
    data = _json_call(_BASE_RULE, human)
    data.setdefault("total", sum(int(d.get("score", 0) or 0) for d in data.get("dimensions") or []))
    return data


def export_review_docx(review: dict[str, Any], *, student: str, course: str,
                       file_name: str) -> bytes:
    import docx
    d = docx.Document()
    _docx_base_style(d)
    d.add_heading(f"作业评审报告：{student or '学生'}", 0)
    d.add_paragraph(f"课程：{course}｜提交文件：{file_name}｜生成时间：{datetime.now():%Y-%m-%d %H:%M}")
    d.add_paragraph(f"AI 初评总分：{review.get('total', 0)} 分")

    d.add_heading("分维度评价", 1)
    t = d.add_table(rows=1, cols=5)
    _docx_table_header(t, ["维度", "得分/满分", "证据", "修改建议", "位置"])
    for r in review.get("dimensions") or []:
        cells = t.add_row().cells
        for c, k in zip(cells, ("name", "_score", "evidence", "suggestion", "location")):
            c.text = f"{r.get('score', 0)}/{r.get('max', 0)}" if k == "_score" else str(r.get(k, ""))

    d.add_heading("优点", 1)
    for s in review.get("strengths") or []:
        d.add_paragraph(str(s), style="List Bullet")
    d.add_heading("改进建议", 1)
    for s in review.get("improvements") or []:
        d.add_paragraph(str(s), style="List Bullet")
    d.add_heading("总评语", 1)
    d.add_paragraph(str(review.get("summary", "")))

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 5) 学情分析与下一课
# ---------------------------------------------------------------------------
def aggregate_analytics(project_id: int | None, *, sources: list[str] | None = None,
                        knowledge_point: str = "", days: int | None = None,
                        kp_filter: str = "") -> dict[str, Any]:
    """从答疑、评审、实训记录中汇总学情数据（全部来自真实记录，含分母）。

    sources: 数据来源子集，取值 ["答疑","评审","实训"]，None 表示全部。
    """
    pid = int(project_id) if project_id else None
    want = set(sources or ["答疑", "评审", "实训"])
    cutoff = (time.time() - days * 86400) if days else None

    def _keep(t: dict[str, Any]) -> bool:
        if cutoff and float(t.get("created_at") or 0) < cutoff:
            return False
        kp = ((t.get("meta") or {}).get("knowledge_point") or "").strip()
        if (kp_filter or knowledge_point) and kp and (kp_filter or knowledge_point) not in kp:
            return False
        return True

    qa = [t for t in db.list_tasks(project_id=pid, kind="qa", limit=500) if _keep(t)] \
        if "答疑" in want else []
    reviews = [t for t in db.list_tasks(project_id=pid, kind="review", limit=500) if _keep(t)] \
        if "评审" in want else []
    trainings = db.list_tasks(project_id=pid, kind="training", limit=200) if "实训" in want else []

    kp_count: dict[str, int] = {}
    kp_students: dict[str, set[str]] = {}
    err_count: dict[str, int] = {}
    qa_students: set[str] = set()
    for t in qa:
        meta = t.get("meta") or {}
        kp = (meta.get("knowledge_point") or "").strip()
        stu = (meta.get("student") or "").strip()
        if stu:
            qa_students.add(stu)
        if kp:
            kp_count[kp] = kp_count.get(kp, 0) + 1
            if stu:
                kp_students.setdefault(kp, set()).add(stu)
        et = (meta.get("error_type") or "").strip()
        if et:
            err_count[et] = err_count.get(et, 0) + 1

    dim_sum: dict[str, list[float]] = {}
    students: dict[str, list[float]] = {}
    for t in reviews:
        meta = t.get("meta") or {}
        ai = meta.get("ai") or {}
        for d in ai.get("dimensions") or []:
            name = (d.get("name") or "").strip()
            if not name:
                continue
            try:
                dim_sum.setdefault(name, []).append(float(d.get("score", 0)))
            except (TypeError, ValueError):
                continue
        stu = (meta.get("student") or "").strip()
        try:
            total = float(meta.get("final_total") or ai.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if stu:
            students.setdefault(stu, []).append(total)

    dim_avg = {k: round(sum(v) / len(v), 1) for k, v in dim_sum.items() if v}
    dim_cnt = {k: len(v) for k, v in dim_sum.items() if v}
    student_scores = {s: round(sum(v) / len(v), 1) for s, v in students.items()}
    need_base = [s for s, v in student_scores.items() if v < 60]
    can_extend = [s for s, v in student_scores.items() if v >= 85]
    roster = set(student_scores) | qa_students
    err_total = sum(err_count.values()) or 1

    return {
        "qa_count": len(qa),
        "review_count": len(reviews),
        "training_count": len(trainings),
        "student_total": len(roster),
        "student_answered": len(qa_students),
        "student_reviewed": len(student_scores),
        "students": sorted(roster),
        "top_knowledge": sorted(kp_count.items(), key=lambda x: -x[1])[:8],
        "knowledge_rows": [
            {"knowledge_point": k, "count": v,
             "students": len(kp_students.get(k, set())),
             "ratio": f"{len(kp_students.get(k, set()))}/{len(roster) or 0}"}
            for k, v in sorted(kp_count.items(), key=lambda x: -x[1])[:8]],
        "top_errors": sorted(err_count.items(), key=lambda x: -x[1])[:8],
        "error_rows": [
            {"error": k, "count": v, "percent": round(v * 100 / err_total, 1)}
            for k, v in sorted(err_count.items(), key=lambda x: -x[1])[:8]],
        "dimension_avg": dim_avg,
        "dimension_rows": [
            {"name": k, "avg": v, "count": dim_cnt.get(k, 0)}
            for k, v in dim_avg.items()],
        "student_scores": student_scores,
        "need_remedial": need_base,
        "can_extend": can_extend,
        "sample_warning": (len(qa) + len(reviews)) < 8,
        "source_counts": {"答疑": len(qa), "评审": len(reviews), "实训": len(trainings)},
    }


def generate_next_lesson(project_id: int | None, analytics: dict[str, Any]) -> dict[str, Any]:
    ctx = course_context(project_id)
    human = f"""基于下面的真实学情数据，生成下一课的教学调整方案。

课程上下文：
{ctx}

学情数据（JSON）：
{json.dumps(analytics, ensure_ascii=False)}

输出 JSON：
{{
  "review_lesson": {{"title": "10 分钟讲评课", "minutes": 10,
    "outline": [{{"minutes": 2, "content": "讲什么", "method": "怎么讲"}}]}},
  "remedial_exercises": [{{"q": "补偿练习", "answer": "答案", "target": "针对哪个共性错误"}}],
  "extension_tasks": [{{"title": "拓展任务", "desc": "任务描述", "target": "适合哪类学生"}}],
  "sequence_adjustment": ["下一课教学顺序调整建议"],
  "evidence": ["每条建议引用的学情数据"],
  "teacher_questions": ["需要教师重点追问的问题"],
  "prefill": {{
    "topic": "下一课课题（讲评课）",
    "objectives": ["下一课学习目标"],
    "key_points": ["薄弱知识点"],
    "materials": ["建议引用的课程资料名"],
    "remedial": ["补偿练习要求"]
  }}
}}

要求：所有建议必须能对应到学情数据中的具体条目，不得空泛；prefill 用于回填一键备课表单。"""
    data = _json_call(_BASE_RULE, human)
    top = [k for k, _ in analytics.get("top_knowledge") or []][:3]
    pf = data.get("prefill") or {}
    pf.setdefault("topic", f"讲评课：{'、'.join(top) or '本课重点'}")
    pf.setdefault("key_points", top)
    pf.setdefault("materials", [])
    pf.setdefault("remedial", [q.get("q", "") for q in data.get("remedial_exercises") or []][:3])
    data["prefill"] = pf
    data["lesson_type"] = "讲评课"
    return data


def export_next_docx(plan: dict[str, Any], course: str,
                     analytics: dict[str, Any]) -> bytes:
    import docx
    d = docx.Document()
    _docx_base_style(d)
    d.add_heading("学情回流与下一课教学建议", 0)
    d.add_paragraph(f"课程：{course}｜生成时间：{datetime.now():%Y-%m-%d %H:%M}")

    d.add_heading("一、学情概览", 1)
    d.add_paragraph(f"答疑记录：{analytics.get('qa_count', 0)} 条；作业评审：{analytics.get('review_count', 0)} 份")
    if analytics.get("top_knowledge"):
        d.add_paragraph("高频问题知识点：" + "、".join(f"{k}（{v} 次）" for k, v in analytics["top_knowledge"]))
    if analytics.get("top_errors"):
        d.add_paragraph("高频错误类型：" + "、".join(f"{k}（{v} 次）" for k, v in analytics["top_errors"]))
    if analytics.get("dimension_avg"):
        d.add_paragraph("能力维度均分：" + "、".join(f"{k} {v}" for k, v in analytics["dimension_avg"].items()))

    rl = plan.get("review_lesson") or {}
    d.add_heading(f"二、{rl.get('title') or '10 分钟讲评课'}", 1)
    t = d.add_table(rows=1, cols=3)
    _docx_table_header(t, ["分钟", "内容", "方法"])
    for r in rl.get("outline") or []:
        cells = t.add_row().cells
        for c, k in zip(cells, ("minutes", "content", "method")):
            c.text = str(r.get(k, ""))

    d.add_heading("三、补偿练习", 1)
    for i, q in enumerate(plan.get("remedial_exercises") or [], 1):
        d.add_paragraph(f"{i}. {q.get('q', '')}（针对：{q.get('target', '')}）")
        d.add_paragraph(f"答案：{q.get('answer', '')}")

    d.add_heading("四、拓展任务", 1)
    for i, q in enumerate(plan.get("extension_tasks") or [], 1):
        d.add_paragraph(f"{i}. {q.get('title', '')}：{q.get('desc', '')}（适合：{q.get('target', '')}）")

    d.add_heading("五、教学顺序调整建议", 1)
    for s in plan.get("sequence_adjustment") or []:
        d.add_paragraph(str(s), style="List Bullet")

    d.add_heading("六、数据依据", 1)
    for s in plan.get("evidence") or []:
        d.add_paragraph(str(s), style="List Bullet")

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 导出公共工具
# ---------------------------------------------------------------------------
def _docx_base_style(d) -> None:
    from docx.oxml.ns import qn
    from docx.shared import Pt
    style = d.styles["Normal"]
    style.font.name = "微软雅黑"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def _docx_table_header(table, headers: list[str]) -> None:
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = text
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True


def artifact_path(folder: Path | str | None, filename: str) -> Path:
    """在项目文件夹下生成交付物路径（同名自动加时间戳）。"""
    base = Path(folder) if folder else (ROOT / ".data" / "exports")
    base.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", filename)
    path = base / safe
    if path.exists():
        stem, suffix = path.stem, path.suffix
        path = base / f"{stem}_{datetime.now():%H%M%S}{suffix}"
    return path


def save_artifact(folder: Path | str | None, filename: str, data: bytes) -> Path:
    p = artifact_path(folder, filename)
    p.write_bytes(data)
    return p
