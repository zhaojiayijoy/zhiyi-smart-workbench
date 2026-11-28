"""AI 课堂预演引擎：模拟学生反应、风险检查、修补方案。

两种模式：
1. live 模式：有备课包且 LLM 可用时，拼装上下文让 LLM 生成；
2. demo 模式：无备课包或 API 调用失败时，返回可重复初始化的演示数据。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from app import db
from app.edu import _invoke, _json_call, parse_json  # 复用项目已有的 LLM 调用封装

# ---------------------------------------------------------------------------
# 模拟学生角色定义
# ---------------------------------------------------------------------------
PERSONAS = {
    "novice": {
        "name": "基础薄弱型",
        "desc": "容易跟不上讲解速度，不理解前置概念，练习题中容易使用错误概念",
    },
    "challenger": {
        "name": "深度追问型",
        "desc": "会追问概念边界，会提出教材之外的延伸问题，会挑战案例是否成立",
    },
    "operator": {
        "name": "操作不熟练型",
        "desc": "Excel操作较慢，不清楚Word和PPT交付要求，实训任务中容易漏掉字段或格式",
    },
}

EVENT_TYPES = {
    "question": "学生提问",
    "misconception": "概念误解",
    "operation_block": "操作卡点",
    "disengagement": "走神",
    "challenge": "深度追问",
    "time_risk": "时间风险",
}

RISK_TYPES = {
    "knowledge_misconception": "知识误解",
    "teaching_time": "教学时间",
    "objective_coverage": "目标覆盖",
    "activity_participation": "活动参与",
    "training_executability": "实训可执行性",
    "rubric_consistency": "评分标准一致性",
}


# ---------------------------------------------------------------------------
# JSON 容错：从 LLM 输出里提取第一个合法 JSON
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """从可能被前后解释文本包裹的输出里抠出 JSON。失败返回 None。"""
    if not text:
        return None
    text = text.strip()
    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 找第一个 { 到最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except Exception:
            pass
    # 用正则扫
    for m in re.finditer(r"\{[^{}]*\}", text):
        try:
            return json.loads(m.group())
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# 从备课包里拼装时间轴和上下文
# ---------------------------------------------------------------------------
def _timeline_from_lesson(lesson: Optional[dict], course: Optional[dict]) -> list[dict[str, Any]]:
    """从教案或 PPT 里抽取阶段，失败时生成默认 6 阶段。"""
    if not lesson:
        return _default_timeline()
    timeline = []
    pkg = (lesson.get("meta") or {}).get("pkg") or {}
    steps = (pkg.get("lesson_plan") or {}).get("steps") or []
    if steps:
        return [{"stageId": f"stage-{i}", "name": step.get("phase") or f"阶段 {i}",
                 "minutes": step.get("minutes") or 5, "objective": step.get("design_intent") or "",
                 "activities": [step.get("teacher") or ""], "practice": step.get("student") or ""}
                for i, step in enumerate(steps, 1) if isinstance(step, dict)]
    answer = lesson.get("answer") or ""
    lesson_plan = answer.get("教案", "") if isinstance(answer, dict) else str(answer)
    stages = re.findall(r"(?:^|\n)\s*(\d+)[.、]\s*(导入|讲解|新授|互动|练习|实训|讨论|总结|作业|拓展)[^\n]*", lesson_plan)
    if stages:
        for i, (idx, name) in enumerate(stages, start=1):
            timeline.append({
                "stageId": f"stage-{i}",
                "name": name,
                "minutes": 8,
                "objective": "",
                "activities": [name],
                "practice": "",
            })
    if not timeline:
        timeline = _default_timeline()
    return timeline


def _default_timeline() -> list[dict[str, Any]]:
    return [
        {"stageId": "stage-1", "name": "导入", "minutes": 5,
         "objective": "唤起兴趣，建立新概念锚点", "activities": ["情境提问"], "practice": ""},
        {"stageId": "stage-2", "name": "概念讲解", "minutes": 12,
         "objective": "区分参照群体与意见领袖", "activities": ["概念定义", "案例对比"], "practice": "辨析题1道"},
        {"stageId": "stage-3", "name": "课堂互动", "minutes": 8,
         "objective": "学生举例并互相评价", "activities": ["小组分享"], "practice": ""},
        {"stageId": "stage-4", "name": "实训演示", "minutes": 10,
         "objective": "演示Excel实训模板填写", "activities": ["教师演示"], "practice": "实训模板第1-2页"},
        {"stageId": "stage-5", "name": "学生实训", "minutes": 25,
         "objective": "独立完成Excel实训", "activities": ["独立操作", "教师巡导"], "practice": "完整实训包"},
        {"stageId": "stage-6", "name": "总结与作业", "minutes": 5,
         "objective": "回顾并布置作业", "activities": ["课堂小结"], "practice": "作业1份"},
    ]


# ---------------------------------------------------------------------------
# LLM 调用（优先 live，失败回退 demo）
# ---------------------------------------------------------------------------
def run_rehearsal(*, rehearsal_id: int, course_id: int,
                  personas: list[str], use_review_model: bool = True) -> None:
    """同步执行预演：读备课包 → 生成时间轴 → 模拟 → 风险 → 修补 → 写回 DB。"""
    session = db.get_rehearsal(rehearsal_id)
    if not session:
        return

    # 0. 标记为运行中
    db.update_rehearsal(rehearsal_id, status="running")

    # 1. 读课程 + 最新备课包
    course = db.get_project(course_id)
    lesson_pkg = None
    if session.get("lesson_package_id"):
        lesson_pkg = db.get_task(int(session["lesson_package_id"]))
    if not lesson_pkg:
        lessons = db.list_tasks(project_id=course_id, kind="lesson", limit=1)
        lesson_pkg = lessons[0] if lessons else None

    timeline = _timeline_from_lesson(lesson_pkg, course)

    # 有备课包 → 尝试 live 生成；失败或无备课包 → 回退 demo
    if lesson_pkg:
        try:
            live_result = _live_run(course, lesson_pkg, timeline, personas, use_review_model)
            summary = live_result.get("summary")
            db.update_rehearsal(
                rehearsal_id,
                status="completed",
                timeline=timeline,
                events=live_result.get("events", []),
                risks=live_result.get("risks", []),
                patches=live_result.get("patches", []),
                summary=summary,
                is_demo=False, error="",
                completed_at=time.time(),
            )
            return
        except Exception as exc:
            # live 失败 → 退回 demo
            db.update_rehearsal(rehearsal_id, status="failed", error=str(exc))
            _finalize_demo(rehearsal_id, course, personas, timeline, fallback_from=str(exc))
            return

    # 无备课包 → 直接用 demo 数据
    _finalize_demo(rehearsal_id, course, personas, timeline)


# ---------------------------------------------------------------------------
# 演示数据（可重复初始化，明确标记 demo）
# ---------------------------------------------------------------------------
def _finalize_demo(rehearsal_id: int, course: Optional[dict],
                   personas: list[str], timeline: list[dict],
                   fallback_from: str = "") -> None:
    """写入一份可重复的演示预演数据，标记 is_demo=1。"""
    course_name = (course or {}).get("name") or "消费者行为分析"
    course_hours = (course or {}).get("hours") or "第6次课：消费者态度与说服"

    persona_list = personas or ["novice", "challenger", "operator"]
    # 事件
    events: list[dict] = []
    if "novice" in persona_list:
        events.append({
            "stageId": "stage-2", "personaId": "novice",
            "eventType": "misconception",
            "content": "意见领袖不就是参照群体吗？那为什么教材又把两者分开？",
            "evidence": "教材第5页「参照群体」定义与 PPT 第6页案例「网红种草」",
            "teacherRisk": "学生可能无法正确完成实训中的参照群体判断",
            "suggestedResponse": "用「直接影响/间接影响」路径区分，用2分钟对比表 + 一道辨析题落地",
        })
        events.append({
            "stageId": "stage-5", "personaId": "novice",
            "eventType": "operation_block",
            "content": "Excel 里「目标人群」字段写什么？模板里没有说明啊。",
            "evidence": "实训任务要求第3条，模板 Excel 缺少字段注释",
            "teacherRisk": "基础薄弱学生在实训环节容易卡住，影响整体时间推进",
            "suggestedResponse": "在实训模板首个 Excel 里增加「字段说明」sheet，每个字段给一句填写示例",
        })
    if "challenger" in persona_list:
        events.append({
            "stageId": "stage-2", "personaId": "challenger",
            "eventType": "challenge",
            "content": "老师说参照群体影响消费，那品牌做公益算不算一种「意见领袖」行为？",
            "evidence": "教案 PPT 第7页「参照群体分类」未覆盖品牌角色",
            "teacherRisk": "延伸问题会拉走教学时间，其他学生跟不上主线",
            "suggestedResponse": "把品牌作为「扩展阅读」放到最后，留1分钟快速讨论+课后链接",
        })
    if "operator" in persona_list:
        events.append({
            "stageId": "stage-4", "personaId": "operator",
            "eventType": "operation_block",
            "content": "PPT 的页数要求是多少？Word 实训报告要写哪些章节？评分里没说啊。",
            "evidence": "评分量规里的「交付完整性」维度没有页数和章节描述",
            "teacherRisk": "实训交付物格式不一致，评分时难以客观判断",
            "suggestedResponse": "在实训任务要求里加「Word章节×4 / PPT页数×6」的明确数字",
        })
        events.append({
            "stageId": "stage-5", "personaId": "operator",
            "eventType": "time_risk",
            "content": "25 分钟独立实训 Excel 填写，连字段注释都没有，我怕会超时。",
            "evidence": "实训模板 Excel 无字段说明 + 评分量规无填写路径",
            "teacherRisk": "超过一半学生可能无法在 25 分钟内提交，拖慢课堂节奏",
            "suggestedResponse": "在实训开始前给 2 分钟「如何填 Excel」的快速演示 + 模板字段说明",
        })

    # 风险（6 类覆盖）
    risks: list[dict] = [
        {
            "riskId": "risk-1", "type": "knowledge_misconception", "level": "high",
            "title": "参照群体与意见领袖容易混淆",
            "evidence": "2 个模拟学生（基础薄弱 + 深度追问）都出现同类误解",
            "impact": "影响实训中的目标人群判断，评分时易出现概念错误",
            "stageId": "stage-2", "objectiveId": "obj-2",
            "patches": ["patch-1", "patch-2"],
        },
        {
            "riskId": "risk-2", "type": "training_executability", "level": "high",
            "title": "25 分钟小组实训缺少 Excel 填写模板与字段说明",
            "evidence": "模板 Excel 无字段注释；2 个操作类模拟学生在实训阶段卡住",
            "impact": "超过 50% 学生可能无法按时提交，拖慢课堂节奏",
            "stageId": "stage-5", "objectiveId": "obj-3",
            "patches": ["patch-2", "patch-4"],
        },
        {
            "riskId": "risk-3", "type": "rubric_consistency", "level": "medium",
            "title": "评分量规没有说明如何判断「论证充分」",
            "evidence": "评分量规只有标题，没有对应证据要求",
            "impact": "AI 评审无法客观判断，教师评分主观性大",
            "stageId": "stage-6", "objectiveId": "obj-4",
            "patches": ["patch-5"],
        },
        {
            "riskId": "risk-4", "type": "teaching_time", "level": "medium",
            "title": "深度追问可能拉走主线教学时间",
            "evidence": "深度追问型学生在导入阶段提出超出教材的问题",
            "impact": "主线内容讲解时长被压缩，影响目标覆盖",
            "stageId": "stage-2", "objectiveId": "obj-1",
            "patches": ["patch-1"],
        },
        {
            "riskId": "risk-5", "type": "objective_coverage", "level": "low",
            "title": "教学目标「能区分参照群体」缺少专项练习",
            "evidence": "教案里没有独立的辨析题或判断题",
            "impact": "学生课上听了但没动手练，形成不了迁移",
            "stageId": "stage-3", "objectiveId": "obj-2",
            "patches": ["patch-3"],
        },
        {
            "riskId": "risk-6", "type": "activity_participation", "level": "low",
            "title": "小组活动没有明确分工，部分学生可能只看不做",
            "evidence": "教案小组活动只说「分组讨论」，没说谁写谁汇报",
            "impact": "少数学生主导，基础薄弱型容易走神",
            "stageId": "stage-3", "objectiveId": "obj-3",
            "patches": ["patch-3"],
        },
    ]

    # 修补
    patches: list[dict] = [
        {
            "patchId": "patch-1", "riskId": "risk-1",
            "targetArtifact": "lesson_plan", "targetSection": "2.概念讲解",
            "reason": "学生混淆参照群体与意见领袖，需要明确区分",
            "before": "介绍参照群体和意见领袖的基本概念（约 10 分钟）",
            "after": "用对比表（定义 / 影响路径 / 课堂例子）区分直接参照群体和意见领袖；配套 1 道辨析题：「网红种草属于哪种参照群体？」（3 分钟讲解 + 2 分钟练习）",
            "status": "pending",
        },
        {
            "patchId": "patch-2", "riskId": "risk-2",
            "targetArtifact": "training_task", "targetSection": "实训模板",
            "reason": "模板 Excel 无字段说明，操作型学生易卡住",
            "before": "提供 Excel 实训模板（共 2 页，无字段注释）",
            "after": "模板首页新增「字段说明」sheet：目标人群 / 品牌角色 / 参照群体 / 购买意图 各给 1 句填写示例；实训开始前教师先快速演示 2 分钟",
            "status": "pending",
        },
        {
            "patchId": "patch-3", "riskId": "risk-5",
            "targetArtifact": "exercise", "targetSection": "课堂练习",
            "reason": "缺少独立辨析练习，学生没动手迁移",
            "before": "课堂练习放在实训包里，没有独立辨析题",
            "after": "增加 3 道辨析题（每道 1 分钟）：1）参照群体与意见领袖区别；2）家人和明星分别属于哪类；3）品牌算不算意见领袖",
            "status": "pending",
        },
        {
            "patchId": "patch-4", "riskId": "risk-2",
            "targetArtifact": "ppt", "targetSection": "PPT 第 8-10 页",
            "reason": "实训要求章节 PPT 页数与交付物规格缺失",
            "before": "PPT 第 8 页只说「完成实训」，没有规格",
            "after": "PPT 第 8 页明确：Word 实训报告 × 4 章节 / PPT 汇报 × 6 页 / Excel 模板 × 1 份",
            "status": "pending",
        },
        {
            "patchId": "patch-5", "riskId": "risk-3",
            "targetArtifact": "rubric", "targetSection": "评分量规·论证充分维度",
            "reason": "「论证充分」没有可操作的评分依据",
            "before": "论证充分（0-20分）：视质量评分",
            "after": "论证充分（0-20分）：\n  - 20分：≥ 3 个不同来源的证据 + 对应概念\n  - 15分：2 个证据 + 对应概念\n  - 10分：只有 1 个证据\n  - 0 分：无证据",
            "status": "pending",
        },
    ]

    high = sum(1 for r in risks if r["level"] == "high")
    medium = sum(1 for r in risks if r["level"] == "medium")
    summary = {
        "riskCount": len(risks), "highRiskCount": high, "mediumRiskCount": medium,
        "topWeakKnowledgePoint": "参照群体与意见领袖的区分",
        "largestTimeRiskStage": "学生实训（25分钟）",
        "topPatchTitle": "实训模板补字段说明",
    }

    db.update_rehearsal(
        rehearsal_id,
        status="completed",
        timeline=timeline, events=events, risks=risks, patches=patches,
        summary=summary, completed_at=time.time(), is_demo=True,
    )


# ---------------------------------------------------------------------------
# Live 模式：调用 LLM 生成（失败时抛出）
# ---------------------------------------------------------------------------
def _live_run(course: Optional[dict], lesson_pkg: Optional[dict],
              timeline: list[dict], personas: list[str],
              use_review: bool = True) -> dict[str, Any]:
    """复用项目 _json_call 调用 LLM 生成预演结果。"""
    course_text = ""
    if course:
        course_text = json.dumps({
            "name": course.get("name"),
            "class_name": course.get("class_name"),
            "hours": course.get("hours"),
            "audience": course.get("audience"),
            "objectives": course.get("objectives"),
            "key_points": course.get("key_points"),
            "difficulties": course.get("difficulties"),
        }, ensure_ascii=False)
    lesson_text = ""
    if lesson_pkg:
        pkg = (lesson_pkg.get("meta") or {}).get("pkg") or lesson_pkg.get("answer") or ""
        lesson_text = json.dumps(pkg, ensure_ascii=False)[:12000]

    persona_text = json.dumps({k: PERSONAS[k] for k in personas if k in PERSONAS}, ensure_ascii=False)
    timeline_text = json.dumps(timeline, ensure_ascii=False)

    system_prompt = (
        "你是一位资深教学预演引擎，请基于课程资料和备课包模拟学生反应。"
        "返回严格 JSON，不要在 JSON 外追加任何解释。"
    )
    human_prompt = (
        f"## 课程\n{course_text}\n"
        f"## 备课包（节选）\n{lesson_text}\n"
        f"## 模拟学生角色\n{persona_text}\n"
        f"## 课堂时间轴\n{timeline_text}\n"
        "\n请返回以下结构：\n"
        '{"summary":{"riskCount":int,"highRiskCount":int,'
        '"topWeakKnowledgePoint":"...","largestTimeRiskStage":"..."},\n'
        '"events":[{"stageId":"stage-?","personaId":"novice|challenger|operator",'
        '"eventType":"question|misconception|operation_block|disengagement|challenge|time_risk",'
        '"content":"学生原话，必须具体，禁止空泛","evidence":"来自教案/PPT/资料的位置",'
        '"teacherRisk":"对教学的影响","suggestedResponse":"教师如何回应"} ...],\n'
        '"risks":[{"riskId":"risk-?","type":"knowledge_misconception|teaching_time|objective_coverage|activity_participation|training_executability|rubric_consistency",'
        '"level":"high|medium|low","title":"风险标题","evidence":"证据","impact":"影响",'
        '"stageId":"stage-?","objectiveId":"obj-?","patches":["patch-?"]} ...],\n'
        '"patches":[{"patchId":"patch-?","riskId":"risk-?","targetArtifact":"lesson_plan|ppt|exercise|training_task|rubric",'
        '"targetSection":"具体章节","reason":"为什么要改","before":"修改前","after":"修改后","status":"pending"} ...]}'
    )

    parsed = _json_call(system_prompt, human_prompt)

    # 用智谱审核（可选）—— 只要 review 函数能跑就调一下，失败忽略
    if use_review and parsed.get("risks"):
        try:
            parsed = _review_with_secondary(parsed, timeline)
        except Exception:
            pass  # 审核失败不阻塞结果

    return parsed


def _review_with_secondary(parsed: dict, timeline: list[dict]) -> dict:
    """用同一个 LLM 做第二轮审核（模拟双模型分工）。"""
    risks = parsed.get("risks", [])
    events = parsed.get("events", [])
    if not risks:
        return parsed

    human_prompt = (
        "你是一位教学审核专家，请检查下面的预演结果：\n"
        "1. 每个风险是否有对应事件/证据？没有证据的风险降级为 low。\n"
        "2. 修补方案是否覆盖了对应风险？没有对应修补的风险添加一条 pending 修补。\n"
        "返回 JSON：{\"risks\":[...相同字段...],\"patches\":[...相同字段...]}\n\n"
        f"## 时间轴\n{json.dumps(timeline, ensure_ascii=False)}\n"
        f"## 风险\n{json.dumps(risks, ensure_ascii=False)}\n"
        f"## 事件\n{json.dumps(events, ensure_ascii=False)}\n"
    )
    try:
        reviewed = _json_call("你是一位教学审核专家。返回严格 JSON，不要解释。", human_prompt)
        if isinstance(reviewed, dict):
            if reviewed.get("risks"):
                parsed["risks"] = reviewed["risks"]
            if reviewed.get("patches"):
                existing_patch_ids = {p.get("patchId") for p in parsed.get("patches", [])}
                for p in reviewed["patches"]:
                    if p.get("patchId") not in existing_patch_ids:
                        parsed.setdefault("patches", []).append(p)
    except Exception:
        pass
    return parsed


# ---------------------------------------------------------------------------
# API 辅助：生成演示预演（给前端快速体验）
# ---------------------------------------------------------------------------
def create_demo_rehearsal(course_id: int, personas: Optional[list[str]] = None) -> int:
    """创建并直接写入演示数据（不调 LLM）。"""
    rehearsal_id = db.create_rehearsal(
        course_id=course_id,
        personas=personas or ["novice", "challenger", "operator"],
        is_demo=True,
        generation_model="demo",
        review_model="demo",
    )
    course = db.get_project(course_id)
    _finalize_demo(rehearsal_id, course, personas or ["novice", "challenger", "operator"],
                   _default_timeline())
    return rehearsal_id
