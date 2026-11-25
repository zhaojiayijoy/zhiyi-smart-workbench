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


def _as_list(value: Any) -> list:
    """模型可能把数组写成字符串，这里统一成列表。"""
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\n；;]+", value)
        return [p.strip("•·- ").strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple)):
        return [x for x in value if x is not None]
    return [value]


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


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
_PPT_REQUIRED_KINDS = {
    "cover": "封面", "objectives": "学习目标", "agenda": "课堂流程",
    "quiz": "课堂练习", "homework": "分层作业", "summary": "总结", "board": "板书设计",
}


def ppt_structure_issues(pkg: dict[str, Any]) -> list[str]:
    """检查课件结构是否达标；返回问题列表，空列表表示通过。"""
    slides = ((pkg.get("ppt") or {}).get("slides")) or []
    slides = [s for s in slides if isinstance(s, dict)]
    issues: list[str] = []
    if len(slides) < 14:
        issues.append(f"课件只有 {len(slides)} 页，少于 14 页")
    kinds = [str(s.get("kind") or "").strip() for s in slides]
    for kind, label in _PPT_REQUIRED_KINDS.items():
        if kind not in kinds:
            issues.append(f"缺少{label}页（kind={kind}）")
    flow = [r for r in (pkg.get("flow45") or []) if isinstance(r, dict)]
    if flow and kinds.count("activity") < min(len(flow), 3):
        issues.append("活动页数量不足，未覆盖课堂流程")
    thin = [s for s in slides
            if s.get("kind") in ("concept", "example")
            and not 2 <= len(_as_list(s.get("bullets"))) <= 6]
    if thin:
        issues.append(f"有 {len(thin)} 页知识讲解页要点不在 2-6 条之间")
    short = [s for s in slides if len(str(s.get("notes") or "")) < 80]
    if short and len(short) > max(2, len(slides) // 3):
        issues.append("多页讲稿过短（不足 80 字）")
    return issues[:6]


def regenerate_ppt_only(pkg: dict[str, Any], topic: str, ctx: str,
                        issues: list[str]) -> dict[str, Any]:
    """课件结构不达标时，仅重生成 ppt 部分；失败则保留原内容。"""
    flow = [r for r in (pkg.get("flow45") or []) if isinstance(r, dict)]
    outline = "；".join(
        f"{r.get('time', '')} {r.get('phase', '')}（{r.get('activity', '')}）" for r in flow
    )
    blueprint = ["第1页 cover 封面",
                 "第2页 objectives 学习目标",
                 "第3页 agenda 课堂流程（含 table）"]
    n = 4
    for r in flow[:6]:
        blueprint.append(f"第{n}页 activity {r.get('phase', '')}（写 duration_min/teacher_action/student_action/notes）")
        n += 1
    # 知识讲解页补足到至少 15 页，保证结构校验（≥14 页）可一次通过
    content_n = max(3, min(8, 15 - n - 4))
    for i in range(content_n):
        blueprint.append(f"第{n + i}页 {'concept' if i < content_n - 1 else 'example'} "
                         f"知识讲解/案例分析（3-5 条要点，至少 1 页含 table）")
    n += content_n
    blueprint += [f"第{n}页 quiz 课堂练习", f"第{n + 1}页 homework 分层作业（基础/提升/挑战）",
                  f"第{n + 2}页 board 板书设计", f"第{n + 3}页 summary 总结"]
    human = f"""重新生成这份课件的 PPT 部分，其余成果保持不变。

课程上下文：
{ctx}

本次课题：{topic}
课堂流程：{outline or '未提供'}

上一版课件的问题：{'；'.join(issues)}

请严格按下面的页面清单逐页输出，不得合并或省略任何一页：
{chr(10).join(blueprint)}

只输出一个 JSON 对象：{{"ppt": {{"title": "课件标题", "slides": [...]}}}}
slides 数组长度必须与页面清单一致（共 {len(blueprint)} 页），顺序一致。
每页字段：kind、layout、title、key_takeaway、bullets、table、visual、duration_min、
teacher_action、student_action、notes。
要求：知识讲解页每页 3-5 条要点且每条不超过 20 字；至少 2 页含 table（headers/rows 可直接排版）；
每页 notes 必须 120-180 个汉字（少于 120 字视为不合格），口语化并写出提问、举例或互动，
例如：“同学们先看屏幕上这个计数器，点按钮数字没变，问题出在哪？对，状态没有声明……”"""
    data = _json_call(_BASE_RULE, human)
    ppt = data.get("ppt") if isinstance(data, dict) else None
    if isinstance(ppt, dict) and ppt.get("slides"):
        pkg["ppt"] = ppt
        pkg.setdefault("meta", {})["ppt_regenerated"] = True
    return pkg


def generate_lesson_package(project_id: int, topic: str, extra: str = "", *,
                            lesson_type: str = "新授课", hours: str = "1 课时",
                            student_level: str = "", style: str = "",
                            outputs: list[str] | None = None,
                            file_ids: list[int] | None = None,
                            model: str = "", review_model: str = "",
                            dual_check: bool = False) -> dict[str, Any]:
    ctx = course_context(project_id, file_ids=file_ids)
    outs = outputs or list(LESSON_OUTPUTS)
    human = f"""请为下面这节课生成一份可直接上课的完整备课包（含课件）。

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
  "ppt": {{"title": "课件标题", "slides": [
    {{"kind": "cover", "layout": "title", "title": "课件标题",
      "key_takeaway": "本页一句话结论（不超过 30 字）",
      "bullets": ["3-5 条，每条不超过 20 字"],
      "table": {{"headers": ["列名"], "rows": [["单元格"]]}},
      "visual": {{"type": "diagram|chart|photo|none", "prompt": "可画出的具体画面描述"}},
      "duration_min": 5,
      "teacher_action": "教师做什么",
      "student_action": "学生做什么",
      "notes": "120-180 字口语化讲稿，含提问或互动"}}
  ]}},
  "questions": {{
    "basic": [{{"q": "基础题", "answer": "答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}],
    "applied": [{{"q": "应用题", "answer": "答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}],
    "extension": [{{"q": "拓展题", "answer": "参考答案", "hint1": "第一层提示", "hint2": "关键步骤提示"}}]
  }},
  "alignment": [{{"knowledge_point": "知识点", "objective": "对应目标", "activity": "对应活动", "assessment": "评价方式"}}],
  "rubric": [{{"dimension": "评分维度", "weight": 30, "excellent": "优秀标准", "good": "良好标准", "pass": "合格标准", "fail": "待改进标准"}}],
  "sources": [{{"content": "教案/PPT/题目", "source": "引用的资料名或“课程通用要求”"}}]
}}

课件（ppt.slides）硬性要求：
1. 共 14-18 页，kind 只能取 cover/objectives/agenda/concept/example/activity/quiz/homework/summary/board；
2. 必备页：cover 封面 1 页、objectives 学习目标 1 页、agenda 课堂流程 1 页、
   activity 活动页（flow45 每个环节至少 1 页，写清 duration_min、teacher_action、student_action）、
   quiz 课堂练习 1-2 页、homework 分层作业 1 页、summary 总结 1 页、board 板书设计 1 页；
3. concept/example 知识讲解页 4-8 页，每页 bullets 3-5 条、每条不超过 20 字，并给出 key_takeaway；
4. 至少 2 页提供 table（课堂流程、对比表或量规表），headers 与 rows 要能直接排版；
5. 确有图示价值时填写 visual，type 用 diagram/chart/photo，prompt 描述可画出的具体画面，否则填 none；
6. notes 每页 120-180 字，口语化，写出提问、举例或互动；
7. homework 页按基础/提升/挑战三档分层布置；board 页给出主板书结构与分支要点。

其他要求：45 分钟流程 5-7 个环节；每类题 2 道；评分标准总分 100。
alignment 必须覆盖 lesson_plan.objectives 中的每一条目标：按知识点拆分时可以拆成多行，
但 objective 字段要直接复制对应的目标原文（同一目标可出现在多行），不要改写措辞。
另外输出 "checks" 字段，对以下 6 项给出 true/false：objectives_covered、qa_matched、
out_of_scope、consistent、untraceable（true 表示存在无法追溯的资料）。"""
    data = _json_call(_BASE_RULE, human)
    data.setdefault("topic", topic)
    data["meta"] = {"lesson_type": lesson_type, "hours": hours, "student_level": student_level,
                    "style": style, "outputs": outs, "model": model or "默认",
                    "review_model": review_model or "", "dual_check": bool(dual_check)}
    issues = ppt_structure_issues(data)
    if issues:
        # 结构不达标时自动重生成一次课件，其余产物保持不变；只有变好才采纳
        try:
            retry = regenerate_ppt_only(data, topic, ctx, issues)
            if isinstance(retry, dict) and isinstance(retry.get("ppt"), dict):
                new_issues = ppt_structure_issues({**data, "ppt": retry["ppt"]})
                if len(new_issues) <= len(issues):
                    data["ppt"] = retry["ppt"]
                    data["meta"]["ppt_regenerated"] = True
                    data["meta"]["ppt_issues_before"] = issues
                    data["meta"]["ppt_issues_after"] = new_issues
                else:
                    data["meta"]["ppt_regen_rejected"] = new_issues
        except Exception as exc:  # noqa: BLE001 - 重生成失败不影响主流程
            data["meta"]["ppt_regen_error"] = f"{exc.__class__.__name__}: {exc}"
    data["checks"] = lesson_checks(data)
    return data


_SECTION_PROMPT = {
    "lesson_plan": '{"objectives":["..."],"key_points":["..."],"difficulties":["..."],'
                   '"preparation":["..."],"steps":[{"phase":"","minutes":8,"teacher":"",'
                   '"student":"","design_intent":""}],"homework":""}',
    "ppt": '{"title":"","slides":[{"kind":"concept","layout":"bullets","title":"",'
           '"key_takeaway":"","bullets":[""],"table":{"headers":[""],"rows":[[""]]},'
           '"visual":{"type":"none","prompt":""},"duration_min":5,"teacher_action":"",'
           '"student_action":"","notes":""}]}',
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
        if not isinstance(s, dict):
            continue
        d.add_heading(f"第 {i} 页 · {s.get('title', '')}", 2)
        for b in _as_list(s.get("bullets")):
            d.add_paragraph(str(b), style="List Bullet")
        if s.get("key_takeaway"):
            d.add_paragraph(f"要点：{s['key_takeaway']}")
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
    """把备课包渲染成可直接上课的课件：统一主题 + 多种版式。

    使用 pkg 中的 flow45 / lesson_plan.steps / questions / rubric / alignment
    以及扩展后的 ppt.slides（kind、table、visual、duration、师生活动、讲稿）。
    """
    import math

    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt
    from pptx.oxml.ns import qn
    from lxml import etree

    EMU = 914400
    W, H = 12192000, 6858000
    FONT = "微软雅黑"
    C_PRIMARY = RGBColor(0x1F, 0x4E, 0x79)
    C_ACCENT = RGBColor(0xE6, 0x9A, 0x2C)
    C_TEXT = RGBColor(0x22, 0x2B, 0x38)
    C_MUTED = RGBColor(0x6B, 0x72, 0x80)
    C_LIGHT = RGBColor(0xF4, 0xF7, 0xFB)
    C_LINE = RGBColor(0xD7, 0xDE, 0xE8)
    C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    C_SOFT = RGBColor(0xD6, 0xE4, 0xF0)
    C_BOARD = RGBColor(0x1E, 0x3A, 0x34)

    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]
    page = {"n": 0}

    def set_font(run, size, bold=False, color=C_TEXT, name=FONT):
        f = run.font
        f.size = Pt(size)
        f.bold = bold
        f.name = name
        if color is not None:
            f.color.rgb = color
        rPr = None
        for attr in ("_r", "_element"):
            el = getattr(run, attr, None)
            if el is not None and hasattr(el, "get_or_add_rPr"):
                rPr = el.get_or_add_rPr()
                break
        if rPr is None:
            return
        ea = rPr.find(qn("a:ea"))
        if ea is None:
            ea = etree.SubElement(rPr, qn("a:ea"))
            latin = rPr.find(qn("a:latin"))
            if latin is not None:
                latin.addnext(ea)
        ea.set("typeface", name)

    def text(slide, l, t, w, h, value, size=16, bold=False, color=C_TEXT,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line=1.18):
        box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        lines = str(value).split("\n")
        for i, raw in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.line_spacing = line
            r = p.add_run()
            r.text = raw
            set_font(r, size, bold, color)
        return box

    def rect(slide, l, t, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE):
        sp = slide.shapes.add_shape(shape, Inches(l), Inches(t), Inches(w), Inches(h))
        sp.shadow.inherit = False
        if fill is None:
            sp.fill.background()
        else:
            sp.fill.solid()
            sp.fill.fore_color.rgb = fill
        if line is None:
            sp.line.fill.background()
        else:
            sp.line.color.rgb = line
            sp.line.width = Pt(1.2)
        return sp

    def bg(slide, color):
        sp = rect(slide, 0, 0, W / EMU, H / EMU, fill=color)
        tree = slide.shapes._spTree
        tree.remove(sp._element)
        tree.insert(2, sp._element)

    def header(slide, title, kicker=None):
        rect(slide, 0, 0, W / EMU, 0.12, fill=C_PRIMARY)
        if kicker:
            text(slide, 0.62, 0.42, 10.5, 0.3, kicker, 11, True, C_ACCENT)
        text(slide, 0.62, 0.7 if kicker else 0.52, 11.6, 0.8, title, 25, True, C_PRIMARY)
        rect(slide, 0.62, 1.52, 1.1, 0.06, fill=C_ACCENT)

    def footer(slide, light=False):
        page["n"] += 1
        if not light:
            rect(slide, 0, H / EMU - 0.05, W / EMU, 0.05, fill=C_PRIMARY)
        color = C_SOFT if light else C_MUTED
        text(slide, 0.62, H / EMU - 0.55, 9.5, 0.3,
             f"致壹智能教育工作台 · {course}", 9, False, color)
        text(slide, 12.0, H / EMU - 0.55, 0.8, 0.3, f"{page['n']:02d}", 9, False,
             color, PP_ALIGN.RIGHT)

    def as_list(value) -> list:
        return _as_list(value)

    def as_dict(value) -> dict:
        return _as_dict(value)

    def bullets(slide, l, t, w, h, items, size=19, color=C_TEXT):
        items = [str(x) for x in as_list(items) if str(x).strip()][:6]
        if not items:
            return
        if max(len(x) for x in items) > 30:
            size = max(14, size - 3)
        box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(10)
            p.line_spacing = 1.25
            r = p.add_run()
            r.text = "• " + item
            set_font(r, size, False, color)
        return box

    def callout(slide, value, t=6.15, l=0.62, w=12.1):
        rect(slide, l, t, w, 0.42, fill=C_LIGHT)
        rect(slide, l, t, 0.08, 0.42, fill=C_ACCENT)
        text(slide, l + 0.2, t + 0.06, w - 0.35, 0.32, value, 12, True, C_PRIMARY)

    def table(slide, l, t, w, headers, rows, size=11, col_w=None, row_h=0.36):
        headers = as_list(headers) or ["—"]
        if isinstance(rows, str):
            rows = [re.split(r"\s*[|｜,，\t]\s*", ln.strip())
                    for ln in rows.splitlines() if ln.strip()]
        norm_rows = []
        for row in as_list(rows)[:8]:
            if isinstance(row, (list, tuple)):
                norm_rows.append([str(c) for c in row])
            elif isinstance(row, dict):
                norm_rows.append([str(v) for v in row.values()])
            elif row is not None:
                norm_rows.append([str(row)])
        rows = norm_rows
        headers = [str(x) for x in headers]
        ncol = len(headers)
        if not ncol:
            return
        height = row_h * (len(rows) + 1)
        shape = slide.shapes.add_table(len(rows) + 1, ncol, Inches(l), Inches(t),
                                       Inches(w), Inches(height))
        tbl = shape.table
        if col_w:
            for j, cw in enumerate(col_w[:ncol]):
                tbl.columns[j].width = Inches(cw)
        for j, head in enumerate(headers):
            cell = tbl.cell(0, j)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = C_PRIMARY
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = head
            set_font(r, size, True, C_WHITE)
            cell.margin_left = Inches(0.07)
            cell.margin_right = Inches(0.05)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
        for i, row in enumerate(rows, start=1):
            for j in range(ncol):
                cell = tbl.cell(i, j)
                cell.text = ""
                cell.fill.solid()
                cell.fill.fore_color.rgb = C_WHITE if i % 2 else C_LIGHT
                p = cell.text_frame.paragraphs[0]
                p.line_spacing = 1.1
                r = p.add_run()
                r.text = row[j] if j < len(row) else ""
                set_font(r, max(8, size - 1), False, C_TEXT)
                cell.margin_left = Inches(0.07)
                cell.margin_right = Inches(0.05)
                cell.margin_top = Inches(0.03)
                cell.margin_bottom = Inches(0.03)

    def visual_box(slide, l, t, w, h, visual):
        desc = str((as_dict(visual)).get("prompt") or "")
        rect(slide, l, t, w, h, fill=C_LIGHT, line=C_LINE)
        text(slide, l + 0.22, t + 0.18, w - 0.44, 0.3, "图示建议", 11, True, C_MUTED)
        text(slide, l + 0.22, t + 0.52, w - 0.44, h - 0.7,
             desc or "可在此放置示意图 / 实物图 / 板书照片", 12, False, C_TEXT)

    def page_cover(title, meta_lines):
        s = prs.slides.add_slide(blank)
        bg(s, C_PRIMARY)
        rect(s, 0, 0, 0.22, H / EMU, fill=C_ACCENT)
        text(s, 0.9, 1.55, 11.6, 1.7, title, 38, True, C_WHITE, line=1.12)
        text(s, 0.9, 3.35, 11.2, 0.42, course, 18, False, C_SOFT)
        text(s, 0.9, 3.95, 11.2, 1.0, "\n".join(meta_lines), 12, False, C_SOFT)
        rect(s, 0.9, 5.45, 3.4, 0.07, fill=C_ACCENT)
        text(s, 0.9, 5.7, 10.5, 0.35, "致壹智能教育工作台 · AI 备课", 11, False, C_SOFT)
        page["n"] += 1

    def page_objectives(items):
        s = prs.slides.add_slide(blank)
        header(s, "学习目标", "OBJECTIVES")
        y = 1.9
        for i, item in enumerate(items[:5]):
            rect(s, 0.62, y, 0.55, 0.55, fill=C_PRIMARY, shape=MSO_SHAPE.OVAL)
            text(s, 0.62, y + 0.1, 0.55, 0.35, str(i + 1), 16, True, C_WHITE,
                 PP_ALIGN.CENTER)
            text(s, 1.38, y + 0.06, 10.8, 0.62, item, 17, False, C_TEXT)
            y += 0.92
        footer(s)

    def page_agenda(flow, steps):
        s = prs.slides.add_slide(blank)
        header(s, "课堂流程", "AGENDA")
        rows = [[r.get("time", ""), r.get("phase", ""), r.get("activity", ""),
                 r.get("goal", "")] for r in flow[:7]]
        table(s, 0.5, 1.85, 12.3, ["时间", "环节", "课堂活动", "达成目标"], rows,
              size=11, col_w=[1.9, 1.7, 4.9, 3.8], row_h=0.52)
        minutes = sum(int(r.get("minutes") or 0) for r in steps)
        if minutes:
            callout(s, f"合计约 {minutes} 分钟；每个环节的活动页见后文")
        footer(s)

    def page_activity(row, step, idx):
        s = prs.slides.add_slide(blank)
        header(s, f"{row.get('phase') or '课堂环节'}｜{row.get('time') or ''}",
               f"环节 {idx}")
        duration = ""
        if step and step.get("minutes"):
            duration = f"{step.get('minutes')} 分钟"
        elif row.get("time"):
            duration = str(row.get("time"))
        if duration:
            rect(s, 10.35, 0.6, 2.3, 0.52, fill=C_ACCENT,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE)
            text(s, 10.35, 0.7, 2.3, 0.32, duration, 12, True, C_WHITE,
                 PP_ALIGN.CENTER)
        teacher = str((step or {}).get("teacher") or row.get("activity") or "—")
        student = str((step or {}).get("student") or "跟随活动完成任务，记录关键结论")
        rect(s, 0.62, 1.85, 5.75, 3.25, fill=C_LIGHT)
        text(s, 0.88, 1.98, 5.2, 0.3, "教师活动", 12, True, C_PRIMARY)
        text(s, 0.88, 2.4, 5.2, 2.5, teacher, 15, False, C_TEXT)
        rect(s, 6.75, 1.85, 5.95, 3.25, fill=C_LIGHT)
        text(s, 7.0, 1.98, 5.4, 0.3, "学生活动", 12, True, C_PRIMARY)
        text(s, 7.0, 2.4, 5.4, 2.5, student, 15, False, C_TEXT)
        text(s, 0.62, 5.4, 11.8, 0.42,
             "达成目标：" + str(row.get("goal") or "—"), 13, True, C_PRIMARY)
        if step and step.get("design_intent"):
            text(s, 0.62, 5.88, 11.8, 0.5,
                 "设计意图：" + str(step.get("design_intent")), 11, False, C_MUTED)
        footer(s)

    def page_content(slide_data, label):
        s = prs.slides.add_slide(blank)
        header(s, str(slide_data.get("title") or label), label)
        items = as_list(slide_data.get("bullets"))
        tb = as_dict(slide_data.get("table"))
        vis = as_dict(slide_data.get("visual"))
        has_tbl = bool(tb.get("rows"))
        has_vis = str(vis.get("type") or "none") != "none" and bool(vis.get("prompt"))
        left_w = 7.3 if (has_tbl or has_vis) else 11.6
        bullets(s, 0.62, 1.9, left_w, 3.5, items, size=19)
        if has_tbl:
            table(s, 8.25, 1.92, 4.45, tb.get("headers") or [], tb.get("rows") or [],
                  size=10, row_h=0.4)
        elif has_vis:
            visual_box(s, 8.25, 1.9, 4.45, 3.5, vis)
        if slide_data.get("key_takeaway"):
            callout(s, "结论｜" + str(slide_data["key_takeaway"]))
        if slide_data.get("notes"):
            s.notes_slide.notes_text_frame.text = str(slide_data["notes"])
        footer(s)

    def page_quiz(title, items):
        s = prs.slides.add_slide(blank)
        header(s, title, "QUIZ")
        y = 1.9
        for i, q in enumerate(items[:4]):
            text(s, 0.62, y, 11.9, 0.42, f"{i + 1}. {q.get('q', '')}", 15, True, C_TEXT)
            hint = str(q.get("hint1") or "")
            if hint:
                text(s, 0.95, y + 0.44, 11.2, 0.32, "提示：" + hint, 11, False, C_MUTED)
                y += 1.0
            else:
                y += 0.78
        keys = [f"{i + 1}. 答案：{q.get('answer', '')}"
                for i, q in enumerate(items[:4])]
        s.notes_slide.notes_text_frame.text = "\n".join(keys)
        footer(s)

    def page_rubric(rows):
        s = prs.slides.add_slide(blank)
        header(s, "评分量规", "RUBRIC")
        data = [[r.get("dimension", ""), f"{r.get('weight', '')}%", r.get("excellent", ""),
                 r.get("good", ""), r.get("pass", ""), r.get("fail", "")]
                for r in rows[:6]]
        table(s, 0.45, 1.82, 12.4, ["维度", "权重", "优秀", "良好", "合格", "待改进"],
              data, size=9, col_w=[1.55, 0.75, 2.6, 2.55, 2.45, 2.45], row_h=0.55)
        footer(s)

    def page_homework(slide_hw, plan_hw):
        s = prs.slides.add_slide(blank)
        header(s, "分层作业", "HOMEWORK")
        items = [str(b) for b in as_list((slide_hw or {}).get("bullets")) if str(b).strip()]
        levels = ["基础", "提升", "挑战"]
        groups = [[], [], []]
        if items:
            per = max(1, math.ceil(len(items) / 3))
            for i, item in enumerate(items):
                groups[min(i // per, 2)].append(item)
        x = 0.62
        for gi, name in enumerate(levels):
            rect(s, x, 1.85, 3.85, 3.5, fill=C_LIGHT, line=C_LINE)
            rect(s, x, 1.85, 3.85, 0.55, fill=C_PRIMARY)
            text(s, x + 0.2, 1.95, 3.4, 0.35, name + "任务", 13, True, C_WHITE)
            bullets(s, x + 0.22, 2.6, 3.45, 2.5, groups[gi] or ["按课堂内容完成对应练习"], size=13)
            x += 4.1
        if plan_hw:
            callout(s, "统一要求：" + str(plan_hw)[:70], t=5.65)
        if slide_hw and slide_hw.get("notes"):
            s.notes_slide.notes_text_frame.text = str(slide_hw["notes"])
        footer(s)

    def page_board(slide_bd, key_points):
        s = prs.slides.add_slide(blank)
        bg(s, C_BOARD)
        text(s, 0.62, 0.5, 11.5, 0.55, "板书设计", 24, True, C_WHITE)
        rect(s, 0.62, 1.15, 2.2, 0.06, fill=C_ACCENT)
        topic = str(pkg.get("topic") or (slide_bd or {}).get("title") or "本课主题")
        rect(s, 2.6, 1.55, 8.1, 0.75, line=C_WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(s, 2.8, 1.7, 7.7, 0.45, topic, 17, True, C_WHITE, PP_ALIGN.CENTER)
        branches = [str(b) for b in as_list((slide_bd or {}).get("bullets"))
                    if str(b).strip()] or [str(k) for k in key_points]
        for i, b in enumerate(branches[:5]):
            col = i % 3
            rowi = i // 3
            bx = 0.65 + col * 4.15
            by = 2.85 + rowi * 1.85
            rect(s, bx, by, 3.75, 1.35, line=C_WHITE)
            text(s, bx + 0.18, by + 0.15, 3.4, 1.05, b, 12, False, C_WHITE)
        page["n"] += 1
        text(s, 12.0, H / EMU - 0.55, 0.8, 0.3, f"{page['n']:02d}", 9, False,
             C_SOFT, PP_ALIGN.RIGHT)

    def page_summary(slide_sum, objectives, takeaways):
        s = prs.slides.add_slide(blank)
        header(s, "课堂小结", "SUMMARY")
        items = [str(b) for b in as_list((slide_sum or {}).get("bullets"))
                 if str(b).strip()] or takeaways[:5] or objectives[:4]
        bullets(s, 0.62, 1.95, 11.7, 3.4, items, size=20)
        if slide_sum and slide_sum.get("key_takeaway"):
            callout(s, "一句话总结｜" + str(slide_sum["key_takeaway"]))
        if slide_sum and slide_sum.get("notes"):
            s.notes_slide.notes_text_frame.text = str(slide_sum["notes"])
        footer(s)

    def page_alignment(rows):
        s = prs.slides.add_slide(blank)
        header(s, "教学对齐表", "ALIGNMENT")
        data = [[r.get("knowledge_point", ""), r.get("objective", ""),
                 r.get("activity", ""), r.get("assessment", "")] for r in rows[:8]]
        table(s, 0.45, 1.82, 12.4, ["知识点", "对应目标", "对应活动", "评价方式"],
              data, size=9, col_w=[2.3, 4.4, 3.2, 2.5], row_h=0.5)
        footer(s)

    def page_sources(rows):
        s = prs.slides.add_slide(blank)
        header(s, "资料与依据", "SOURCES")
        y = 1.95
        for i, r in enumerate(rows[:7]):
            text(s, 0.62, y, 11.9, 0.38,
                 f"{i + 1}. {r.get('source', '')}", 13, True, C_TEXT)
            if r.get("content"):
                text(s, 0.95, y + 0.38, 11.4, 0.3,
                     "用于：" + str(r.get("content")), 10, False, C_MUTED)
                y += 0.9
            else:
                y += 0.55
        footer(s)

    ppt = pkg.get("ppt") or {}
    slides = [s for s in (ppt.get("slides") or []) if isinstance(s, dict)]
    plan = pkg.get("lesson_plan") or {}
    flow = [r for r in (pkg.get("flow45") or []) if isinstance(r, dict)]
    steps = [r for r in (plan.get("steps") or []) if isinstance(r, dict)]
    questions = pkg.get("questions") or {}
    rubric = [r for r in (pkg.get("rubric") or []) if isinstance(r, dict)]
    alignment = [r for r in (pkg.get("alignment") or []) if isinstance(r, dict)]
    sources = [r for r in (pkg.get("sources") or []) if isinstance(r, dict)]
    meta = pkg.get("meta") or {}

    def by_kind(*kinds):
        return [s for s in slides if str(s.get("kind") or "") in kinds]

    cover = (by_kind("cover") or [None])[0]
    title = ((cover or {}).get("title") or ppt.get("title")
             or pkg.get("topic") or "课程课件")
    page_cover(title, [
        f"课型：{meta.get('lesson_type', '—')}    课时：{meta.get('hours', '—')}",
        f"学生基础：{meta.get('student_level') or '未填写'}",
    ])

    objectives = [str(x) for x in (plan.get("objectives") or []) if str(x).strip()]
    obj_slide = (by_kind("objectives") or [None])[0]
    if not objectives and obj_slide:
        objectives = [str(b) for b in as_list(obj_slide.get("bullets")) if str(b).strip()]
    if objectives:
        page_objectives(objectives)

    if flow:
        page_agenda(flow, steps)
        for i, row in enumerate(flow):
            matched = None
            for st in steps:
                ph = str(st.get("phase") or "")
                if ph and (ph in str(row.get("phase") or "")
                           or str(row.get("phase") or "") in ph):
                    matched = st
                    break
            if matched is None and i < len(steps):
                matched = steps[i]
            page_activity(row, matched, i + 1)

    handled = {"cover", "objectives", "agenda", "quiz", "homework", "summary", "board"}
    takeaways = []
    for sd in slides:
        kind = str(sd.get("kind") or "concept")
        if kind in handled:
            continue
        if sd.get("key_takeaway"):
            takeaways.append(str(sd["key_takeaway"]))
        page_content(sd, "案例分析" if kind == "example" else "知识讲解")

    basic = [q for q in (questions.get("basic") or []) if isinstance(q, dict)]
    applied = [q for q in (questions.get("applied") or []) if isinstance(q, dict)]
    extension = [q for q in (questions.get("extension") or []) if isinstance(q, dict)]
    quiz_slide = (by_kind("quiz") or [None])[0]
    if basic or applied:
        page_quiz("课堂练习 · 基础与应用", basic + applied)
        if extension:
            page_quiz("课堂练习 · 拓展提升", extension)
    elif quiz_slide:
        page_content(quiz_slide, "课堂练习")

    if rubric:
        page_rubric(rubric)

    hw_slide = (by_kind("homework") or [None])[0]
    if hw_slide or plan.get("homework"):
        page_homework(hw_slide, plan.get("homework"))

    board_slide = (by_kind("board") or [None])[0]
    kp = [str(k) for k in (plan.get("key_points") or []) if str(k).strip()]
    if board_slide or kp:
        page_board(board_slide, kp)

    sum_slide = (by_kind("summary") or [None])[0]
    if sum_slide or takeaways or objectives:
        page_summary(sum_slide, objectives, takeaways)

    if alignment:
        page_alignment(alignment)
    if sources:
        page_sources(sources)

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
