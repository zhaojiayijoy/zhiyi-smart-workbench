"""教学闭环冒烟测试（不依赖模型调用，也不写入任何假数据）。

覆盖：课程 → 备课 → 答疑 → 评审 → 学情 → 下一课 → 回到备课预填。

运行：
    python -m app.smoke_test

测试在临时课程中构造最小样本，结束后自动清理，不影响真实课程。
"""
from __future__ import annotations

import io
import sys
import time
import traceback

from app import db, edu

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [PASS] {name}")
    else:
        FAILS.append(f"{name}：{detail}")
        print(f"  [FAIL] {name} {detail}")


def _lesson_pkg() -> dict:
    return {
        "topic": "消费者购买决策过程",
        "lesson_plan": {
            "objectives": ["说出决策五阶段", "能用边际贡献做定价判断"],
            "key_points": ["决策五阶段"],
            "difficulties": ["边际贡献计算"],
            "preparation": ["案例投影"],
            "steps": [{"phase": "导入", "minutes": 10, "teacher": "案例提问",
                       "student": "讨论", "design_intent": "激活经验"}],
            "homework": "完成分层练习",
        },
        "ppt": {"title": "消费者购买决策", "slides": [{"title": "导入", "bullets": ["为什么买？"],
                                                     "notes": "提问导入"}]},
        "questions": {"basic": [{"q": "决策第一阶段是什么？", "answer": "问题识别",
                                 "hint1": "先想需求从哪来", "hint2": "看教材第 2 节"}],
                      "applied": [{"q": "计算边际贡献", "answer": "收入-变动成本",
                                   "hint1": "先找变动成本", "hint2": "用单价减单位变动成本"}],
                      "extension": [{"q": "给超市定价建议", "answer": "结合案例分析"}]},
        "rubric": [{"dimension": "数据准确性", "weight": 30, "excellent": "全部准确",
                    "good": "基本准确", "pass": "少量错误", "fail": "大量错误"},
                   {"dimension": "分析深度", "weight": 30},
                   {"dimension": "结构表达", "weight": 20},
                   {"dimension": "汇报呈现", "weight": 20}],
        "alignment": [{"knowledge_point": "决策五阶段", "objective": "说出决策五阶段",
                       "activity": "案例讨论", "assessment": "课堂提问"},
                      {"knowledge_point": "边际贡献", "objective": "能用边际贡献做定价判断",
                       "activity": "计算练习", "assessment": "练习批改"}],
        "sources": [{"content": "决策五阶段", "source": "教材节选.docx 第 2 章"}],
        "flow45": [{"phase": "导入", "minutes": 10}],
    }


def _temp_course() -> int:
    name = f"冒烟测试课程_{int(time.time())}"
    pid = db.create_project(name, "自动测试创建的临时课程")
    db.set_project_demo(pid, 1)  # 仅用于测试结束后允许删除临时课程
    db.update_course(pid, audience="测试对象", class_name="测试班", hours="2 课时",
                     objectives="理解消费者决策过程", key_points="决策五阶段",
                     difficulties="边际贡献计算", progress="第 1 次课", version="v1")
    db.save_file(name="教材节选.docx", ext="DOCX", kind="doc", content=b"demo",
                 size=2048, parsed_text="消费者购买决策包括问题识别、信息搜索、方案评估、购买、购后行为。",
                 project_id=pid, visibility="teacher", category="教材", ai_context=1)
    db.save_file(name="学生数据表.xlsx", ext="XLSX", kind="table", content=b"demo",
                 size=0, parsed_text="学生,边际贡献\n学生A,12\n学生B,18",
                 project_id=pid, visibility="student", category="案例", ai_context=1)
    db.save_file(name="教师答案.docx", ext="DOCX", kind="doc", content=b"demo",
                 size=1024, parsed_text="内部答案：边际贡献 = 收入 - 变动成本。",
                 project_id=pid, visibility="teacher", category="答案", ai_context=1)
    return pid


def run() -> int:
    pid = _temp_course()
    try:
        print("== 1. 课程上下文与权限隔离 ==")
        teacher_ctx = edu.course_context(pid, student_mode=False)
        student_ctx = edu.course_context(pid, student_mode=True)
        check("教师上下文含教师可见资料", "教师答案" in teacher_ctx)
        check("学生上下文不含教师可见答案", "教师答案" not in student_ctx)
        check("学生上下文不含「教师可见」标记", "教师可见" not in student_ctx)
        check("AI 上下文开关生效", "教师答案" in edu.course_context(pid, ai_only=True))

        print("== 2. 备课包结构与检查 ==")
        pkg = _lesson_pkg()
        pkg["checks"] = edu.lesson_checks(pkg)
        checks = pkg["checks"]
        check("评分量规总分 100", checks["rubric_total"] == 100, str(checks["rubric_total"]))
        check("6 项检查齐全", len(checks["items"]) == 6)
        check("目标覆盖检查通过", checks["objectives_covered"])
        check("练习与答案匹配", checks["qa_matched"])

        print("== 3. 导出 Office 文件可读 ==")
        try:
            import docx
            from pptx import Presentation
            from openpyxl import load_workbook
            d = docx.Document(io.BytesIO(edu.export_lesson_docx(pkg, "测试课程")))
            check("Word 备课包可读", len(d.paragraphs) > 3)
            p = Presentation(io.BytesIO(edu.export_lesson_pptx(pkg, "测试课程")))
            check("PPT 课件可读", len(p.slides) > 0)
            wb = load_workbook(io.BytesIO(edu.export_lesson_xlsx(pkg)))
            check("Excel 练习可读", len(wb.sheetnames) >= 2)
        except Exception as e:  # noqa: BLE001
            check("Office 导出", False, str(e))

        print("== 4. 备课 → 答疑 → 评审 → 学情 → 下一课 ==")
        ltid = db.save_task(kind="lesson", prompt="消费者购买决策过程", answer="备课包已生成",
                            project_id=pid,
                            meta={"pkg": pkg, "version": "v1", "materials": ["教材节选.docx"],
                                  "review_status": "待教师确认", "created": time.time()})
        check("备课包记录写入", ltid > 0)

        db.save_task(kind="qa", prompt="边际贡献怎么算？", answer="先算收入减变动成本。",
                     project_id=pid,
                     meta={"student": "测试学生A", "knowledge_point": "边际贡献",
                           "error_type": "概念不清", "status": "waiting",
                           "sources": ["教材节选.docx"], "history": []})
        db.save_task(kind="review", prompt="测试学生A · 实训提交", answer="结构清晰",
                     project_id=pid,
                     meta={"student": "测试学生A", "class_name": "测试班",
                           "files": ["作业.docx", "数据.xlsx", "汇报.pptx"],
                           "task": "消费者行为分析", "rubric_name": "实训量规",
                           "ai": {"total": 78, "dimensions": [
                               {"name": "数据准确性", "score": 18, "max": 25}]},
                           "final_total": 82, "status": "published"})

        a = edu.aggregate_analytics(pid, sources=["答疑", "评审"])
        check("学情统计含分母", "student_total" in a and "student_reviewed" in a)
        check("答疑计入统计", a["qa_count"] == 1, str(a["qa_count"]))
        check("评审计入统计", a["review_count"] == 1, str(a["review_count"]))
        check("高频知识点来自答疑", a["top_knowledge"][0][0] == "边际贡献", str(a["top_knowledge"]))
        check("错误类型占比有数据", bool(a["error_rows"]))

        plan = {"review_lesson": {"title": "边际贡献讲评", "minutes": 10, "outline": []},
                "remedial_exercises": [{"q": "计算边际贡献", "answer": "收入-变动成本",
                                        "target": "边际贡献"}],
                "extension_tasks": [{"title": "定价决策", "desc": "综合案例", "target": "测试学生B"}],
                "sequence_adjustment": ["先复习概念再进入案例"],
                "evidence": ["答疑 1 条：边际贡献概念不清"],
                "teacher_questions": ["为什么先算变动成本？"],
                "prefill": {"topic": "讲评课：边际贡献", "objectives": ["掌握边际贡献计算"],
                            "key_points": ["边际贡献"], "materials": ["教材节选.docx"],
                            "remedial": ["计算边际贡献"]},
                "lesson_type": "讲评课"}
        nid = db.save_task(kind="nextlesson", prompt=plan["prefill"]["topic"],
                           answer="已生成", project_id=pid, meta={"plan": plan})
        check("下一课方案保存并关联课程", nid > 0)
        check("可预填一键备课", plan["prefill"]["topic"] and plan["lesson_type"] in edu.LESSON_TYPES)
        check("预填资料可用于备课",
              any(f["name"] == plan["prefill"]["materials"][0]
                  for f in db.list_files(project_id=pid, limit=50)))

        ov = db.course_overview(pid)
        check("驾驶舱统计正确", ov["files_total"] == 3 and ov["lesson_count"] == 1
              and ov["qa_count"] == 1 and ov["review_count"] == 1
              and ov["nextlesson_count"] == 1, str(ov))
        check("待评审数量正确", ov["pending_review"] == 0, str(ov["pending_review"]))

        sizes = {f["name"]: f["size"] for f in db.list_files(project_id=pid, limit=50)}
        check("0 字节文件保留原始 0（UI 显示未知大小）", sizes.get("学生数据表.xlsx") == 0)
    finally:
        db.delete_project_data(pid, delete_project=True)
        check("临时课程已清理", db.get_project(pid) is None)

    print()
    if FAILS:
        print(f"共 {len(FAILS)} 项失败：")
        for f in FAILS:
            print(" -", f)
        return 1
    print("全部冒烟检查通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
