"""致壹 智能教育工作台 · 本地 HTTP API。

把 Streamlit 版的真实能力（课程/文件/任务读写 + 大模型生成 + Office 导出）
包装为 REST 接口，供静态站（static-web/）调用。启动：
    python api_server.py          # 监听 0.0.0.0:8700

静态站默认请求 http://127.0.0.1:8700/api ；若未启动则前端回退到内置演示数据。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

# 确保以项目根目录为工作基准，与 streamlit_app.py 行为一致
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import db, edu, agent  # noqa: E402
from app.config import ROOT as CFG_ROOT, EXPORT_DIR  # noqa: E402

API_PORT = int(os.getenv("EDU_API_PORT", "8700"))

app = FastAPI(title="致壹 智能教育工作台 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 生成产物的内存热缓存；落库由下方 _store_* 完成，重启后从 SQLite 自动恢复
STORE: dict[str, dict[str, Any]] = {
    "lessons": {},      # task_id -> {project_id, topic, pkg, ts}
    "trainings": {},
    "reviews": {},
    "nextplans": {},    # task_id -> {project_id, plan, analytics, ts}
    "tutors": {},       # thread_id -> {project_id, question, history:[{role,text}], ts}
    "analytics": {},    # project_id -> {analytics, ts}
}

# 这些桶的 key 是整数 task_id，从库里恢复时需要还原类型
_INT_KEY_BUCKETS = {"lessons", "trainings", "reviews", "nextplans"}

# 桶 -> Streamlit 工作台写入的任务类型（用于读取 tasks.meta 中的旧产物）
_TASK_KIND = {"lessons": "lesson", "trainings": "training",
              "reviews": "review", "nextplans": "nextlesson"}


def _from_task_meta(bucket: str, ref: Any) -> Optional[dict[str, Any]]:
    """从 tasks.meta 还原 Streamlit 工作台生成的产物，实现两套界面互通。"""
    task_kind = _TASK_KIND.get(bucket)
    if not task_kind:
        return None
    try:
        tid = int(ref)
    except (TypeError, ValueError):
        return None
    t = db.get_task(tid)
    if not t or t.get("kind") != task_kind:
        return None
    meta = t.get("meta") or {}
    ts = t.get("created_at") or 0
    pid = t.get("project_id")
    if bucket in ("lessons", "trainings"):
        pkg = meta.get("pkg")
        if not pkg:
            return None
        base = {"project_id": pid, "pkg": pkg, "ts": ts}
        if bucket == "lessons":
            base["topic"] = meta.get("topic") or t.get("prompt") or ""
            base["materials"] = meta.get("materials") or []
            base["version"] = meta.get("version") or "v1"
        else:
            base["scenario"] = t.get("prompt") or ""
        return base
    if bucket == "reviews":
        ai = meta.get("ai")
        if not isinstance(ai, dict) or not ai:
            return None
        return {"project_id": pid, "student": meta.get("student") or "",
                "file_name": meta.get("file") or t.get("prompt") or "",
                "review": ai, "teacher": meta.get("teacher"),
                "accepted": meta.get("accepted"), "final_total": meta.get("final_total"),
                "status": meta.get("status"), "ts": ts}
    if bucket == "nextplans":
        plan = meta.get("plan")
        if not plan:
            return None
        return {"project_id": pid, "plan": plan,
                "analytics": meta.get("analytics") or {}, "ts": ts}
    return None


def _store_put(bucket: str, key: Any, value: dict[str, Any]) -> None:
    """写内存并持久化到 artifacts 表，保证重启不丢。"""
    STORE[bucket][key] = value
    db.save_artifact(bucket, key, value, value.get("project_id"))


def _store_get(bucket: str, key: Any) -> Optional[dict[str, Any]]:
    """先读内存，再读 artifacts，最后回退 tasks.meta（兼容 Streamlit 旧产物）。"""
    if key in STORE[bucket]:
        return STORE[bucket][key]
    value = db.get_artifact(bucket, key)
    if value is None:
        value = _from_task_meta(bucket, key)
    if value is not None:
        STORE[bucket][key] = value
    return value


def _store_items(bucket: str, project_id: Optional[int] = None):
    """合并 artifacts、tasks.meta 与内存最新产物（内存优先），供 history 使用。"""
    merged: dict[Any, dict[str, Any]] = {}
    for ref, value in db.list_artifacts(bucket, project_id=project_id):
        key: Any = ref
        if bucket in _INT_KEY_BUCKETS:
            try:
                key = int(ref)
            except ValueError:
                continue
        merged[key] = value
    task_kind = _TASK_KIND.get(bucket)
    if task_kind:
        for task in db.list_tasks(project_id=project_id, kind=task_kind, limit=500):
            tid = task.get("id")
            if tid in merged:
                continue
            value = _from_task_meta(bucket, tid)
            if value is not None:
                merged[tid] = value
    merged.update(STORE[bucket])
    if project_id is not None:
        merged = {k: v for k, v in merged.items() if v.get("project_id") == project_id}
    return merged.items()


# ---------------------------------------------------------------------------
# 统一响应
# ---------------------------------------------------------------------------
def ok(data: Any = None, **kw) -> dict:
    out = {"ok": True}
    out.update(kw)
    if data is not None:
        out["data"] = data
    return out


def err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"ok": False, "error": msg})


def _now() -> float:
    return time.time()


def _file_resp(data: bytes, filename: str, media: str) -> Response:
    # HTTP 头只能是 latin-1，中文文件名需按 RFC 5987 编码，另给 ASCII 回退名
    ascii_name = filename.encode("ascii", "ignore").decode().strip() or "download"
    disposition = (f'attachment; filename="{ascii_name}"; '
                   f"filename*=UTF-8''{quote(filename)}")
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": disposition},
    )


@app.on_event("startup")
def _startup() -> None:
    db.ensure_default_project()


# ---------------------------------------------------------------------------
# 健康与配置
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    key_set = bool(os.getenv("LLM_API_KEY", "") and not os.getenv("LLM_API_KEY", "").startswith("sk-REPLACE"))
    return ok({"name": "致壹 智能教育工作台 API", "llm_configured": key_set,
               "model": os.getenv("LLM_MODEL", ""), "time": int(_now())})


@app.get("/api/settings")
def get_settings() -> dict:
    def mask(k: str) -> str:
        v = os.getenv(k, "")
        if not v:
            return ""
        return v[:4] + "…" + v[-4:] if len(v) > 8 else "已设置"
    return ok({
        "llm_base_url": os.getenv("LLM_BASE_URL", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "llm_api_key": mask("LLM_API_KEY"),
        "zhipu_base_url": os.getenv("ZHIPU_BASE_URL", ""),
        "zhipu_model": os.getenv("ZHIPU_MODEL", ""),
        "zhipu_api_key": mask("ZHIPU_API_KEY"),
        # 生成参数
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.4")),
        "top_p": float(os.getenv("LLM_TOP_P", "0.95")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "8192")),
        "thinking": os.getenv("LLM_THINKING", "disabled"),
        "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "max"),
        # 审核模型（双模型一致性检查）
        "review_model": os.getenv("LLM_REVIEW_MODEL", ""),
        "allowed_ext": sorted(t for t in os.getenv("ALLOWED_EXT", "").split(",") if t),
    })


class SettingsIn(BaseModel):
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    zhipu_base_url: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    zhipu_model: Optional[str] = None
    # 生成参数
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    thinking: Optional[str] = None          # disabled | enabled
    reasoning_effort: Optional[str] = None  # max | high | medium | low
    review_model: Optional[str] = None


@app.post("/api/settings")
def save_settings(body: SettingsIn) -> dict:
    env_path = CFG_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    kv = {
        "LLM_BASE_URL": body.llm_base_url, "LLM_API_KEY": body.llm_api_key,
        "LLM_MODEL": body.llm_model, "ZHIPU_BASE_URL": body.zhipu_base_url,
        "ZHIPU_API_KEY": body.zhipu_api_key, "ZHIPU_MODEL": body.zhipu_model,
    }
    # 数值/枚举参数：None 表示不修改，空字符串或合法值才写入
    numeric = {
        "LLM_TEMPERATURE": body.temperature, "LLM_TOP_P": body.top_p,
        "LLM_MAX_TOKENS": body.max_tokens,
    }
    string_enum = {
        "LLM_THINKING": body.thinking, "LLM_REASONING_EFFORT": body.reasoning_effort,
        "LLM_REVIEW_MODEL": body.review_model,
    }
    # 处理数值参数：只有明确传入且合法才写
    for k, v in numeric.items():
        if v is not None:
            kv[k] = str(v)
    # 处理枚举参数
    for k, v in string_enum.items():
        if v is not None and v.strip() != "":
            kv[k] = v.strip()
    changed = {k: v for k, v in kv.items() if v is not None}
    # 写回 .env
    out_lines = list(lines)
    for k, v in changed.items():
        found = False
        for i, ln in enumerate(out_lines):
            if ln.strip().startswith(k + "="):
                out_lines[i] = f"{k}={v}"
                found = True
                break
        if not found:
            out_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    # 热生效：build_llm 每次读 os.getenv
    for k, v in changed.items():
        os.environ[k] = v
    return ok({"updated": list(changed.keys()), "live": True})


# ---------------------------------------------------------------------------
# 课程项目
# ---------------------------------------------------------------------------
def _course_out(p: Optional[dict]) -> Optional[dict]:
    """把 SQLite 行归一化为前端可直接消费的课程对象。

    同时保留原始字段（class_name / hours 等）并把 hours 里的数字
    解析成 totalHours 整数，避免前端再做字符串清洗。
    """
    if not p:
        return None
    out = dict(p)
    m = re.search(r"\d+", str(p.get("hours") or ""))
    out["totalHours"] = int(m.group()) if m else 0
    out["classSize"] = int(p.get("class_size") or 0)
    out["currentSession"] = int(p.get("current_session") or 0)
    out["totalSessions"] = int(p.get("total_sessions") or 0)
    out["class"] = p.get("class_name") or ""
    out["className"] = p.get("class_name") or ""
    out["textbook"] = p.get("textbook_version") or ""
    out["desc"] = p.get("description") or ""
    out["note"] = p.get("note") or ""
    out["key"] = p.get("key_points") or ""
    out["diff"] = p.get("difficulties") or ""
    if "file_count" in out:
        out["resourceCount"] = int(out.get("file_count") or 0)
    return out


@app.get("/api/courses")
def list_courses() -> dict:
    return ok([_course_out(p) for p in db.list_projects()])


@app.get("/api/courses/{cid}")
def get_course(cid: int) -> dict:
    p = db.get_project(cid)
    if not p:
        raise HTTPException(404, "课程不存在")
    p["overview"] = db.course_overview(cid)
    return ok(_course_out(p))


@app.get("/api/courses/{cid}/overview")
def course_overview_api(cid: int) -> dict:
    return ok(db.course_overview(cid))


class CourseIn(BaseModel):
    name: str
    # 前端 camelCase 数字字段
    classSize: Optional[int] = None
    totalHours: Optional[int] = None
    currentSession: Optional[int] = None
    totalSessions: Optional[int] = None
    resourceCount: Optional[int] = None
    # 前端简写字段（class 是 Python 关键字，用 alias 接收）
    class_: Optional[str] = Field(None, alias="class")
    textbook: Optional[str] = None
    desc: Optional[str] = None
    note: Optional[str] = None
    key: Optional[str] = None
    diff: Optional[str] = None
    objectives: Optional[str] = None
    progress: Optional[str] = None
    audience: Optional[str] = None
    # 后端 snake_case 兼容字段
    class_name: Optional[str] = None
    hours: Optional[str] = None
    textbook_version: Optional[str] = None
    description: Optional[str] = ""
    key_points: Optional[str] = None
    difficulties: Optional[str] = None


@app.post("/api/courses")
def create_course(body: CourseIn) -> dict:
    if not body.name.strip():
        raise HTTPException(400, "课程名称必填")
    pid = db.create_project(body.name.strip(), description=(body.description or body.desc or ""))

    hours_val = None
    if body.totalHours is not None:
        hours_val = str(int(body.totalHours))
    elif body.hours is not None:
        hours_val = body.hours

    db.update_course(
        pid,
        audience=body.audience,
        class_name=body.class_ or body.class_name or body.audience,
        hours=hours_val,
        textbook_version=body.textbook or body.textbook_version,
        objectives=body.objectives,
        key_points=body.key or body.key_points,
        difficulties=body.diff or body.difficulties,
        progress=body.progress,
        class_size=body.classSize,
        current_session=body.currentSession,
        total_sessions=body.totalSessions,
        note=body.note,
    )
    return ok(_course_out(db.get_project(pid)), id=pid)


class CoursePatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    desc: Optional[str] = None
    audience: Optional[str] = None
    class_: Optional[str] = Field(None, alias="class")
    class_name: Optional[str] = None
    classSize: Optional[int] = None
    hours: Optional[str] = None
    totalHours: Optional[int] = None
    currentSession: Optional[int] = None
    totalSessions: Optional[int] = None
    textbook_version: Optional[str] = None
    textbook: Optional[str] = None
    objectives: Optional[str] = None
    key_points: Optional[str] = None
    key: Optional[str] = None
    difficulties: Optional[str] = None
    diff: Optional[str] = None
    progress: Optional[str] = None
    note: Optional[str] = None


@app.put("/api/courses/{cid}")
@app.patch("/api/courses/{cid}")
def update_course_api(cid: int, body: CoursePatch) -> dict:
    if not db.get_project(cid):
        raise HTTPException(404, "课程不存在")
    name = body.name.strip() if body.name is not None else None
    if body.name is not None and not name:
        raise HTTPException(400, "课程名称不能为空")

    hours_val = None
    if body.totalHours is not None:
        hours_val = str(int(body.totalHours))
    elif body.hours is not None:
        hours_val = body.hours

    try:
        db.update_project(cid, name=name, description=body.description or body.desc)
        db.update_course(
            cid,
            audience=body.audience,
            class_name=body.class_ or body.class_name,
            hours=hours_val,
            textbook_version=body.textbook or body.textbook_version,
            objectives=body.objectives,
            key_points=body.key or body.key_points,
            difficulties=body.diff or body.difficulties,
            progress=body.progress,
            class_size=body.classSize,
            current_session=body.currentSession,
            total_sessions=body.totalSessions,
            note=body.note,
        )
    except Exception as e:
        raise HTTPException(400, f"更新失败：{e}")
    return ok(_course_out(db.get_project(cid)))


@app.delete("/api/courses/{cid}")
def delete_course(cid: int) -> dict:
    db.delete_project(cid)
    return ok({"id": cid})


# ---------------------------------------------------------------------------
# 文件
# ---------------------------------------------------------------------------
@app.get("/api/files")
def list_files(project_id: Optional[int] = Query(None)) -> dict:
    return ok(db.list_files(project_id=project_id))


@app.get("/api/files/{fid}")
def get_file(fid: int) -> dict:
    f = db.get_file(fid, with_content=False)
    if not f:
        raise HTTPException(404, "文件不存在")
    return ok(f)


@app.get("/api/files/{fid}/text")
def get_file_text(fid: int) -> dict:
    return ok({"text": db.get_file_text(fid) or ""})


@app.post("/api/files")
def upload_file(project_id: int = Form(...), category: str = Form("资料"),
                visibility: str = Form("both"), file: UploadFile = File(...)) -> dict:
    data = file.file.read()
    name = file.filename or "upload"
    try:
        text, meta = edu.extract_text(name, data)
    except Exception as e:
        text, meta = "", {"note": f"解析失败：{e}", "ext": Path(name).suffix.lstrip(".").upper()}
    note = meta.get("note") or ""
    parse_status = "parsed" if text.strip() else ("failed" if note else "parsed")
    ext = meta.get("ext") or Path(name).suffix.lstrip(".").upper()
    kind = "table" if ext in ("CSV", "XLSX", "XLS") else "doc"
    try:
        fid = db.save_file(
            name=name, ext=ext, kind=kind, content=data, size=len(data),
            rows=meta.get("rows", 0), cols=meta.get("cols", 0), chars=meta.get("chars", 0),
            parsed_text=text or None, project_id=project_id, visibility=visibility,
            category=category, ai_context=1, parse_status=parse_status,
        )
    except Exception as e:
        raise HTTPException(500, f"保存失败：{e}")
    msg = f"已加入「{name}」" + (f"（{note}）" if note else (f"，解析正文 {len(text)} 字" if text else ""))
    return ok({"id": fid, "name": name, "ext": ext, "kind": kind,
               "rows": meta.get("rows", 0), "cols": meta.get("cols", 0),
               "chars": meta.get("chars", 0), "status": parse_status, "message": msg})


@app.delete("/api/files/{fid}")
def delete_file(fid: int) -> dict:
    db.delete_file(fid)
    return ok({"id": fid})


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------
@app.get("/api/tasks")
def list_tasks(project_id: Optional[int] = Query(None), kind: Optional[str] = Query(None),
               limit: int = Query(200)) -> dict:
    return ok(db.list_tasks(project_id=project_id, kind=kind, limit=limit))


@app.delete("/api/tasks/{tid}")
def delete_task(tid: int) -> dict:
    db.delete_task(tid)
    # 同步清掉该任务对应的生成产物（避免历史列表里残留已删记录）
    for bucket in ("lessons", "trainings", "reviews"):
        db.delete_artifact(bucket, tid)
        STORE[bucket].pop(tid, None)
    return ok({"id": tid})


# ---------------------------------------------------------------------------
# 一键备课
# ---------------------------------------------------------------------------
class LessonIn(BaseModel):
    project_id: int
    topic: str
    lesson_type: str = "新授课"
    hours: str = "1 课时"
    student_level: str = ""
    style: str = ""
    outputs: Optional[list[str]] = None
    file_ids: Optional[list[int]] = None
    model: str = ""
    review_model: str = ""
    dual_check: bool = False
    extra: str = ""


@app.post("/api/lesson/generate")
def gen_lesson(body: LessonIn) -> dict:
    t0 = _now()
    try:
        pkg = edu.generate_lesson_package(
            body.project_id, body.topic, extra=body.extra,
            lesson_type=body.lesson_type, hours=body.hours,
            student_level=body.student_level, style=body.style,
            outputs=body.outputs, file_ids=body.file_ids,
            model=body.model, review_model=body.review_model,
            dual_check=body.dual_check,
        )
    except Exception as e:
        return err(f"生成失败：{e.__class__.__name__}: {e}", 500)
    file_ids = set(body.file_ids or [])
    materials = [f["name"] for f in db.list_files(project_id=body.project_id, limit=500)
                 if f["id"] in file_ids]
    tid = db.save_task(prompt=body.topic, answer="备课包已生成", kind="lesson",
                       status="ok", duration_s=round(_now() - t0, 1),
                       project_id=body.project_id,
                       meta={"pkg": pkg, "topic": body.topic, "version": "v1",
                             "materials": materials, "model": body.model or "默认",
                             "review_model": body.review_model,
                             "dual_check": bool(body.dual_check),
                             "lesson_type": body.lesson_type,
                             "outputs": body.outputs or [], "created": _now(),
                             "params": body.dict(),
                             "review_status": "待教师确认", "issues": []})
    _store_put("lessons", tid, {"project_id": body.project_id, "topic": body.topic,
                                "pkg": pkg, "materials": materials, "version": "v1",
                                "ts": _now()})
    return ok({"task_id": tid, "pkg": pkg, "checks": pkg.get("checks")})


@app.get("/api/lesson/history")
def lesson_history(project_id: Optional[int] = Query(None)) -> dict:
    rows = []
    for tid, item in _store_items("lessons", project_id):
        pkg = item["pkg"]
        rows.append({"task_id": tid, "topic": item["topic"], "ts": item["ts"],
                     "model": (pkg.get("meta") or {}).get("model"),
                     "checks": pkg.get("checks"),
                     "materials": item.get("materials") or [],
                     "version": item.get("version") or "v1",
                     "slides": len(((pkg.get("ppt") or {}).get("slides") or []))})
    return ok(rows)


@app.get("/api/lesson/{tid}")
def get_lesson(tid: int) -> dict:
    item = _store_get("lessons", tid)
    if not item:
        raise HTTPException(404, "备课包不存在")
    return ok(item["pkg"])


class LessonRegenIn(BaseModel):
    section: str


# 与 edu._SECTION_PROMPT 支持单独重写的成果项保持一致
_LESSON_SECTIONS = ("lesson_plan", "ppt", "questions", "rubric")


@app.post("/api/lesson/{tid}/regenerate")
def regenerate_lesson(tid: int, body: LessonRegenIn) -> dict:
    if body.section not in _LESSON_SECTIONS:
        raise HTTPException(400, f"section 仅支持：{'、'.join(_LESSON_SECTIONS)}")
    item = _store_get("lessons", tid)
    if not item:
        raise HTTPException(404, "备课包不存在")
    try:
        pkg = edu.regenerate_section(item["project_id"], item["pkg"], body.section)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        return err(f"重新生成失败：{e.__class__.__name__}: {e}", 500)
    item["pkg"] = pkg
    _store_put("lessons", tid, item)
    task = db.get_task(tid)
    if task:
        meta = task.get("meta") or {}
        meta["pkg"] = pkg
        db.update_task(tid, meta=meta)
    return ok({"task_id": tid, "section": body.section, "pkg": pkg,
               "checks": pkg.get("checks")})


@app.get("/api/lesson/{tid}/export")
def export_lesson(tid: int, type: str = Query("docx")) -> Response:
    item = _store_get("lessons", tid)
    if not item:
        raise HTTPException(404, "备课包不存在")
    p = db.get_project(item["project_id"]) or {"name": "课程"}
    if type == "pptx":
        return _file_resp(edu.export_lesson_pptx(item["pkg"], p["name"]),
                          f"备课课件_{item['topic']}.pptx",
                          "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    if type == "xlsx":
        return _file_resp(edu.export_lesson_xlsx(item["pkg"]),
                          f"练习与评分_{item['topic']}.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return _file_resp(edu.export_lesson_docx(item["pkg"], p["name"]),
                      f"备课包_{item['topic']}.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------
# 创建实训
# ---------------------------------------------------------------------------
class TrainingIn(BaseModel):
    project_id: int
    scenario: str
    extra: str = ""


@app.post("/api/training/generate")
def gen_training(body: TrainingIn) -> dict:
    t0 = _now()
    try:
        pkg = edu.generate_training(body.project_id, body.scenario, extra=body.extra)
    except Exception as e:
        return err(f"生成失败：{e.__class__.__name__}: {e}", 500)
    pkg.setdefault("status", "draft")
    tid = db.save_task(prompt=body.scenario, answer="实训任务包已生成", kind="training",
                       status="ok", duration_s=round(_now() - t0, 1), project_id=body.project_id,
                       meta={"pkg": pkg})
    _store_put("trainings", tid, {"project_id": body.project_id, "scenario": body.scenario,
                                  "pkg": pkg, "ts": _now()})
    return ok({"task_id": tid, "pkg": pkg})


@app.get("/api/training/history")
def training_history(project_id: Optional[int] = Query(None)) -> dict:
    rows = [{"task_id": t, "scenario": v["scenario"], "ts": v["ts"],
             "status": ((v.get("pkg") or {}).get("status") or "draft")}
            for t, v in _store_items("trainings", project_id)]
    return ok(rows)


@app.get("/api/training/{tid}")
def get_training(tid: int) -> dict:
    item = _store_get("trainings", tid)
    if not item:
        raise HTTPException(404, "实训包不存在")
    return ok(item["pkg"])


@app.get("/api/training/{tid}/export")
def export_training(tid: int, type: str = Query("docx")) -> Response:
    item = _store_get("trainings", tid)
    if not item:
        raise HTTPException(404, "实训包不存在")
    p = db.get_project(item["project_id"]) or {"name": "课程"}
    if type == "pptx":
        return _file_resp(edu.export_training_pptx(item["pkg"], p["name"]), "实训说明.pptx",
                          "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    if type == "xlsx":
        return _file_resp(edu.export_training_xlsx(item["pkg"]), "实训数据表.xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return _file_resp(edu.export_training_docx(item["pkg"], p["name"]), "实训任务单.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------
# 学生答疑
# ---------------------------------------------------------------------------
class TutorIn(BaseModel):
    project_id: Optional[int] = None
    question: str
    thread_id: Optional[str] = None
    action: Optional[str] = None
    student_mode: bool = True   # False = 教师模式（可引用教师可见资料）
    student: str = "学生"


@app.post("/api/tutor/reply")
def tutor_reply(body: TutorIn) -> dict:
    tid = body.thread_id or uuid.uuid4().hex[:12]
    thread = _store_get("tutors", tid)
    if thread is None:
        thread = {"project_id": body.project_id, "question": body.question,
                  "history": [], "ts": _now()}
        _store_put("tutors", tid, thread)
    history = thread.setdefault("history", [])
    stage_index = len([m for m in history if m["role"] == "assistant"])
    t0 = _now()
    try:
        data = edu.tutor_reply(body.project_id, body.question, history, stage_index,
                               student_mode=body.student_mode, action=body.action)
    except Exception as e:
        return err(f"生成失败：{e.__class__.__name__}: {e}", 500)
    history.append({"role": "user", "text": body.question})
    history.append({"role": "assistant", "text": data.get("feedback", "")})
    _store_put("tutors", tid, thread)
    task_id = db.save_task(prompt=body.question, answer=data.get("feedback", ""), kind="qa",
                           project_id=body.project_id,
                           meta={"knowledge_point": data.get("knowledge_point"),
                                 "error_type": data.get("error_type"),
                                 "need_teacher": data.get("need_teacher"),
                                 "sources": data.get("sources") or [],
                                 "history": history, "status": "ai",
                                 "student": body.student or "学生"})
    return ok({"thread_id": tid, "task_id": task_id, "reply": data, "history": history})


@app.post("/api/tutor/full")
def tutor_full(body: TutorIn) -> dict:
    thread = _store_get("tutors", body.thread_id) if body.thread_id else None
    history = (thread or {}).get("history", [])
    try:
        data = edu.tutor_full_answer(body.project_id, body.question, history)
    except Exception as e:
        return err(f"生成失败：{e.__class__.__name__}: {e}", 500)
    return ok({"reply": data})


@app.get("/api/tutor/history")
def tutor_history(project_id: Optional[int] = Query(None)) -> dict:
    rows = [{"thread_id": t, "question": v["question"], "ts": v["ts"],
             "turns": len(v["history"]) // 2}
            for t, v in _store_items("tutors", project_id)]
    return ok(rows)


class TutorStatusIn(BaseModel):
    status: str  # ai=AI 引导中 / teacher=教师接管 / solved=已解决


@app.patch("/api/tutor/records/{tid}")
def update_tutor_record(tid: int, body: TutorStatusIn) -> dict:
    if body.status not in ("ai", "teacher", "solved"):
        raise HTTPException(400, "status 仅支持 ai / teacher / solved")
    task = db.get_task(tid)
    if not task or task.get("kind") != "qa":
        raise HTTPException(404, "答疑记录不存在")
    meta = task.get("meta") or {}
    meta["status"] = body.status
    db.update_task(tid, meta=meta)
    return ok({"id": tid, "status": body.status})


# ---------------------------------------------------------------------------
# 作业评审
# ---------------------------------------------------------------------------
class ReviewIn(BaseModel):
    project_id: Optional[int] = None
    submission_text: str
    file_name: str = "学生提交"
    student: str = ""
    class_name: str = ""
    rubric: Optional[list[dict]] = None


@app.post("/api/review/evaluate")
def review_evaluate(body: ReviewIn) -> dict:
    t0 = _now()
    try:
        review = edu.evaluate_submission(body.project_id, body.submission_text,
                                         body.file_name, rubric=body.rubric, student=body.student)
    except Exception as e:
        return err(f"评审失败：{e.__class__.__name__}: {e}", 500)
    tid = db.save_task(prompt=f"{body.student or '学生'}：{body.file_name}",
                       answer=f"总分 {review.get('total', 0)}", kind="review",
                       project_id=body.project_id,
                       meta={"student": body.student, "class_name": body.class_name,
                             "ai": review, "final_total": review.get("total", 0)})
    _store_put("reviews", tid, {"project_id": body.project_id, "review": review,
                                "student": body.student, "file_name": body.file_name, "ts": _now()})
    return ok({"task_id": tid, "review": review})


@app.get("/api/review/history")
def review_history(project_id: Optional[int] = Query(None)) -> dict:
    rows = []
    for t, v in _store_items("reviews", project_id):
        ai_total = (v.get("review") or {}).get("total")
        rows.append({"task_id": t, "student": v["student"], "file_name": v["file_name"],
                     "total": ai_total, "ai_total": ai_total,
                     "final_total": v.get("final_total", ai_total),
                     "status": v.get("status") or "ai", "ts": v["ts"]})
    return ok(rows)


@app.get("/api/review/{tid}")
def get_review(tid: int) -> dict:
    item = _store_get("reviews", tid)
    if not item:
        raise HTTPException(404, "评审记录不存在")
    return ok(item)


class ReviewFinalizeIn(BaseModel):
    scores: Optional[dict[str, float]] = None   # 维度名 -> 教师终评分
    comment: Optional[str] = None               # 教师终评评语
    reason: str = ""                            # 修改原因
    status: str = "published"                   # published / returned / manual
    accepted: Optional[dict[str, bool]] = None  # 是否接受 AI 判断
    student: Optional[str] = None
    class_name: Optional[str] = None


_REVIEW_STATUS = ("published", "returned", "manual")


@app.patch("/api/review/{tid}")
def finalize_review(tid: int, body: ReviewFinalizeIn) -> dict:
    if body.status not in _REVIEW_STATUS:
        raise HTTPException(400, "status 仅支持 published / returned / manual")
    item = _store_get("reviews", tid)
    if not item:
        raise HTTPException(404, "评审记录不存在")
    review = item.get("review") or {}
    dims = review.get("dimensions") or []
    dim_map: dict[str, dict] = {}
    for i, d in enumerate(dims):
        dim_map[d.get("name") or f"维度{i}"] = d
    # 教师终评分：未传则沿用 AI 分数
    scores: dict[str, float] = {}
    for name, val in (body.scores or {}).items():
        if name not in dim_map:
            raise HTTPException(400, f"未知评分维度：{name}")
        try:
            v = float(val)
        except (TypeError, ValueError):
            raise HTTPException(400, f"分数无效：{name}")
        mx = float(dim_map[name].get("max", 100) or 100)
        scores[name] = round(max(0.0, min(v, mx)), 1)
    if not scores:
        scores = {name: float(d.get("score", 0) or 0) for name, d in dim_map.items()}
    ai_total = review.get("total", 0)
    final_total = round(sum(scores.values()), 1)
    comment = body.comment if body.comment is not None else review.get("summary", "")
    student = body.student if body.student is not None else (item.get("student") or "")
    class_name = body.class_name or ""
    file_name = item.get("file_name") or ""
    task = db.get_task(tid)
    old_meta = (task or {}).get("meta") or {}
    versions = list(old_meta.get("versions") or [])
    versions.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "ai_total": ai_total, "final_total": final_total})
    accepted = body.accepted if body.accepted is not None else (old_meta.get("accepted") or {})
    meta = {
        "student": student, "class_name": class_name,
        "files": [file_name] if file_name else [], "file": file_name,
        "task": old_meta.get("task", ""), "rubric_name": old_meta.get("rubric_name", ""),
        "rubric": old_meta.get("rubric") or [],
        "ai": review,
        "teacher": {"scores": scores, "total": final_total,
                    "comment": comment, "reason": body.reason},
        "accepted": accepted, "final_total": final_total, "status": body.status,
        "versions": versions,
    }
    if task:
        db.update_task(tid, answer=comment, meta=meta)
    item.update({"student": student, "file_name": file_name,
                 "teacher": meta["teacher"], "accepted": accepted,
                 "final_total": final_total, "status": body.status})
    _store_put("reviews", tid, item)
    return ok({"task_id": tid, "ai_total": ai_total, "final_total": final_total,
               "status": body.status, "teacher": meta["teacher"]})


@app.get("/api/review/{tid}/export")
def export_review(tid: int) -> Response:
    item = _store_get("reviews", tid)
    if not item:
        raise HTTPException(404, "评审记录不存在")
    p = db.get_project(item["project_id"]) or {"name": "课程"}
    return _file_resp(edu.export_review_docx(item["review"], student=item["student"],
                                              course=p["name"], file_name=item["file_name"]),
                      "作业评审报告.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------
# 学情分析
# ---------------------------------------------------------------------------
class AnalyticsIn(BaseModel):
    project_id: Optional[int] = None
    sources: Optional[list[str]] = None
    days: Optional[int] = None
    knowledge_point: str = ""


@app.post("/api/analytics/aggregate")
def analytics_aggregate(body: AnalyticsIn) -> dict:
    data = edu.aggregate_analytics(body.project_id, sources=body.sources,
                                   days=body.days, knowledge_point=body.knowledge_point)
    if body.project_id:
        _store_put("analytics", body.project_id, {"project_id": body.project_id,
                                                  "analytics": data, "ts": _now()})
    return ok(data)


@app.post("/api/analytics/next")
def analytics_next(body: AnalyticsIn) -> dict:
    cached = (_store_get("analytics", body.project_id) or {}) if body.project_id else {}
    a = cached.get("analytics") or edu.aggregate_analytics(body.project_id, sources=body.sources)
    try:
        plan = edu.generate_next_lesson(body.project_id, a)
    except Exception as e:
        return err(f"生成失败：{e.__class__.__name__}: {e}", 500)
    tid = db.save_task(prompt="下一课方案", answer="已生成", kind="nextlesson",
                       project_id=body.project_id,
                       meta={"plan": plan, "analytics": a})
    _store_put("nextplans", tid, {"project_id": body.project_id, "plan": plan,
                                  "analytics": a, "ts": _now()})
    return ok({"task_id": tid, "plan": plan, "analytics": a})


@app.get("/api/analytics/next/history")
def next_plan_history(project_id: Optional[int] = Query(None)) -> dict:
    rows = [{"task_id": t, "ts": v.get("ts")}
            for t, v in _store_items("nextplans", project_id)]
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return ok(rows)


@app.get("/api/analytics/next/{tid}")
def get_next_plan(tid: int) -> dict:
    item = _store_get("nextplans", tid)
    if not item:
        raise HTTPException(404, "下一课方案不存在")
    return ok({"task_id": tid, "plan": item["plan"],
               "analytics": item.get("analytics") or {}})


@app.get("/api/analytics/{project_id}/export")
def export_next(project_id: int) -> Response:
    items = list(_store_items("nextplans", project_id))
    latest = max(items, key=lambda kv: kv[1].get("ts") or 0) if items else None
    cached = _store_get("analytics", project_id) or {}
    a = (latest[1].get("analytics") if latest else None) or cached.get("analytics") \
        or edu.aggregate_analytics(project_id)
    plan = latest[1].get("plan") if latest else edu.generate_next_lesson(project_id, a)
    p = db.get_project(project_id) or {"name": "课程"}
    return _file_resp(edu.export_next_docx(plan, p["name"], analytics=a), "下一课方案.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------
# AI 助手
# ---------------------------------------------------------------------------
class ChatIn(BaseModel):
    prompt: str
    project_id: Optional[int] = None
    context: Optional[str] = None


@app.post("/api/assistant/chat")
def assistant_chat(body: ChatIn) -> dict:
    t0 = _now()
    ctx = body.context
    if ctx is None and body.project_id:
        try:
            ctx = edu.course_context(body.project_id)
        except Exception:
            ctx = ""
    try:
        res = agent.run(body.prompt, chat_history=[], context=ctx or "")
    except Exception as e:
        return err(f"助手异常：{e.__class__.__name__}: {e}", 500)
    output = res.get("output") or res.get("error") or "(无输出)"
    tid = db.save_task(prompt=body.prompt, answer=output, kind="agent",
                       status="ok" if res.get("status") == "ok" else "error",
                       duration_s=round(_now() - t0, 1), project_id=body.project_id)
    return ok({"task_id": tid, "status": res.get("status"), "output": output,
               "steps": len(res.get("intermediate_steps") or [])})


# ---------------------------------------------------------------------------
# 智谱智能体对话（POST /v1/agents）
# ---------------------------------------------------------------------------
class AgentChatIn(BaseModel):
    agent_id: str = "intelligent_education_solve_agent"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    custom_variables: Optional[dict[str, Any]] = None
    project_id: Optional[int] = None


@app.get("/api/agent/list")
def agent_list() -> dict:
    """返回可用智能体与翻译语言枚举，供前端下拉。"""
    from app import zhipu_agent
    return ok({"agents": zhipu_agent.AGENTS, "languages": zhipu_agent.LANGUAGES,
               "default": zhipu_agent.DEFAULT_AGENT})


@app.post("/api/agent/chat")
def agent_chat(body: AgentChatIn) -> dict:
    from app import zhipu_agent
    t0 = _now()
    try:
        res = zhipu_agent.chat(body.agent_id, body.messages, body.custom_variables)
    except Exception as e:
        return err(f"智能体异常：{e.__class__.__name__}: {e}", 500)
    if res.get("status") == "error":
        return err(res.get("error") or "智能体调用失败", 502)

    prompt = ""
    for m in reversed(body.messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            prompt = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            break
    tid = db.save_task(prompt=prompt[:500], answer=res.get("content") or "", kind="agent",
                       status="ok", duration_s=round(_now() - t0, 1),
                       project_id=body.project_id)
    res["task_id"] = tid
    return ok(res)


# ---------------------------------------------------------------------------
# 学生空间汇总
# ---------------------------------------------------------------------------
@app.get("/api/student/dashboard")
def student_dashboard(project_id: Optional[int] = Query(None), student: str = Query("")) -> dict:
    qa = db.list_tasks(project_id=project_id, kind="qa", limit=200)
    reviews = db.list_tasks(project_id=project_id, kind="review", limit=200)
    trainings = db.list_tasks(project_id=project_id, kind="training", limit=100)
    lessons = db.list_tasks(project_id=project_id, kind="lesson", limit=100)
    # 学生相关：过滤 meta.student
    def _stu(t: dict) -> str:
        return ((t.get("meta") or {}).get("student") or "").strip()
    my_qa = [t for t in qa if not student or _stu(t) == student]
    my_reviews = [t for t in reviews if not student or _stu(t) == student]
    tutor_threads = [{"thread_id": k, "question": v["question"], "ts": v["ts"]}
                     for k, v in _store_items("tutors", project_id)]
    return ok({
        "my_qa": my_qa, "my_reviews": my_reviews, "trainings": trainings,
        "lessons": lessons, "tutor_threads": tutor_threads,
    })


# ---------------------------------------------------------------------------
# 智谱异步结果查询 / 图像生成 / 视频生成
# ---------------------------------------------------------------------------
class MediaGenIn(BaseModel):
    prompt: str
    model: Optional[str] = None
    poll: bool = True
    max_wait: int = 180


@app.get("/api/async/{task_id}")
def query_async(task_id: str) -> dict:
    """GET /paas/v4/async-result/{id} 的包装：查询异步生成任务结果。"""
    from app import zhipu_media
    res = zhipu_media.query_async_result(task_id.strip())
    if res.get("status") == "error":
        return err(res.get("error", "未知错误"), 400)
    # 直接返回完整结果（前端按需渲染）
    return ok(res)


@app.post("/api/image/generate")
def gen_image(body: MediaGenIn) -> dict:
    """图像生成：默认 glm-image-plus，poll=True 会等待结果（最长 180s）。"""
    from app import zhipu_media
    model = body.model or os.getenv("ZHIPU_IMAGE_MODEL", "glm-image-plus")
    res = zhipu_media.generate_image(
        prompt=body.prompt.strip(),
        model=model,
        poll=body.poll,
        max_wait=body.max_wait,
    )
    if res.get("status") == "error":
        return err(res.get("error", "图像生成失败"), 400)
    return ok(res)


@app.post("/api/video/generate")
def gen_video(body: MediaGenIn) -> dict:
    """视频生成：默认 glm-video，poll=True 会等待结果（最长 10 分钟）。"""
    from app import zhipu_media
    model = body.model or os.getenv("ZHIPU_VIDEO_MODEL", "glm-video")
    res = zhipu_media.generate_video(
        prompt=body.prompt.strip(),
        model=model,
        poll=body.poll,
        max_wait=max(body.max_wait, 600),
    )
    if res.get("status") == "error":
        return err(res.get("error", "视频生成失败"), 400)
    return ok(res)


@app.get("/api/media/models")
def media_models() -> dict:
    """返回智谱可用的图像/视频模型列表（供前端下拉）。"""
    from app import zhipu_media
    return ok({
        "image": [{"id": k, "name": v} for k, v in zhipu_media.IMAGE_MODELS.items()],
        "video": [{"id": k, "name": v} for k, v in zhipu_media.VIDEO_MODELS.items()],
    })


# ---------------------------------------------------------------------------
# 智谱网络搜索（Web Search API）
# ---------------------------------------------------------------------------
class WebSearchIn(BaseModel):
    search_query: str
    search_engine: str = "search_std"
    search_intent: bool = True
    count: int = 10
    search_domain_filter: Optional[str] = None
    search_recency_filter: str = "noLimit"
    content_size: str = "medium"
    request_id: Optional[str] = None
    user_id: Optional[str] = None


@app.post("/api/search/web")
def search_web(body: WebSearchIn) -> dict:
    """POST /paas/v4/web_search 包装。

    参数说明：
        search_query      搜索内容（建议 ≤70 字符）
        search_engine     search_std（基础）/ search_pro（高阶）/ search_pro_sogou / search_pro_quark
        search_intent     True 先做意图识别（SEARCH_NONE 会直接返回空结果）
        count             1-50，默认 10
        search_domain_filter   限定白名单域名（如 www.example.com）
        search_recency_filter  oneDay/oneWeek/oneMonth/oneYear/noLimit
        content_size      medium（摘要）/ high（最大化上下文）
    """
    from app import zhipu_search
    res = zhipu_search.web_search(
        query=body.search_query,
        search_engine=body.search_engine,
        search_intent=body.search_intent,
        count=body.count,
        domain_filter=body.search_domain_filter,
        recency_filter=body.search_recency_filter,
        content_size=body.content_size,
        request_id=body.request_id,
        user_id=body.user_id,
    )
    if res.get("status") != "ok":
        return err(res.get("error", "搜索失败"), 400)
    return ok(res)


# ---------------------------------------------------------------------------
# 备课包：整包重生成 / 审核保存到课程资料
# ---------------------------------------------------------------------------
@app.post("/api/lesson/{tid}/regenerate-all")
def regenerate_lesson_all(tid: int) -> dict:
    """按首次生成时的参数整包重生成一版。"""
    if not _store_get("lessons", tid):
        raise HTTPException(404, "备课包不存在")
    task = db.get_task(tid)
    params = ((task or {}).get("meta") or {}).get("params") or {}
    if not params:
        raise HTTPException(400, "缺少原始生成参数，无法整包重生成")
    try:
        lesson_in = LessonIn(**params)
    except Exception as e:
        raise HTTPException(400, f"参数回放失败：{e}")
    res = gen_lesson(lesson_in)
    if not res.get("ok"):
        return res
    new_tid = (res.get("data") or {}).get("task_id")
    old = db.get_task(tid)
    if old and new_tid:
        meta = old.get("meta") or {}
        meta["review_status"] = f"已换新版（任务 {new_tid}）"
        db.update_task(tid, meta=meta)
    return res


@app.post("/api/lesson/{tid}/approve")
def approve_lesson(tid: int) -> dict:
    """通过审核：把教案与课件导出成文件，存入当前课程资料。"""
    item = _store_get("lessons", tid)
    if not item:
        raise HTTPException(404, "备课包不存在")
    p = db.get_project(item["project_id"]) or {"name": "课程"}
    topic = item.get("topic") or "备课包"
    try:
        docx_b = edu.export_lesson_docx(item["pkg"], p["name"])
        pptx_b = edu.export_lesson_pptx(item["pkg"], p["name"])
    except Exception as e:
        return err(f"导出失败：{e.__class__.__name__}: {e}", 500)
    specs = [("docx", f"{topic}_教案.docx", ".docx", "教案", docx_b),
             ("pptx", f"{topic}_课件.pptx", ".pptx", "课件", pptx_b)]
    saved = []
    for _kind, name, ext, category, blob in specs:
        fid = db.save_file(name=name, ext=ext, kind="lesson", content=blob,
                           size=len(blob), project_id=item["project_id"],
                           visibility="both", category=category,
                           parsed_text=f"由备课包「{topic}」导出")
        saved.append({"id": fid, "name": name, "size": len(blob)})
    task = db.get_task(tid)
    if task:
        meta = task.get("meta") or {}
        meta["review_status"] = "已通过"
        db.update_task(tid, meta=meta)
    return ok({"task_id": tid, "files": saved})


# ---------------------------------------------------------------------------
# 实训：发布 / 存草稿
# ---------------------------------------------------------------------------
class TrainingStatusIn(BaseModel):
    status: str


@app.post("/api/training/{tid}/status")
def set_training_status(tid: int, body: TrainingStatusIn) -> dict:
    if body.status not in ("draft", "published"):
        raise HTTPException(400, "status 仅支持 draft / published")
    item = _store_get("trainings", tid)
    if not item:
        raise HTTPException(404, "实训包不存在")
    item["pkg"]["status"] = body.status
    _store_put("trainings", tid, item)
    task = db.get_task(tid)
    if task:
        meta = task.get("meta") or {}
        meta["pkg"] = item["pkg"]
        db.update_task(tid, meta=meta)
    return ok({"task_id": tid, "status": body.status})


# ---------------------------------------------------------------------------
# 数据维护：备份 / 清理临时文件 / 清空全部数据
# ---------------------------------------------------------------------------
@app.get("/api/maintenance/backup")
def export_backup() -> Response:
    import io as _io
    import zipfile
    data_dir = CFG_ROOT / ".data"
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if db.DB_PATH.exists():
            z.write(db.DB_PATH, "workbench.db")
        for sub in ("uploads", "exports"):
            root = data_dir / sub
            if not root.exists():
                continue
            for f in root.rglob("*"):
                if f.is_file():
                    z.write(f, str(f.relative_to(data_dir)).replace("\\", "/"))
    return _file_resp(buf.getvalue(),
                      f"workbench_backup_{time.strftime('%Y%m%d_%H%M')}.zip",
                      "application/zip")


@app.post("/api/maintenance/cleanup")
def cleanup_tmp() -> dict:
    root = CFG_ROOT / ".data" / "tmp"
    removed = freed = 0
    if root.exists():
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    freed += f.stat().st_size
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    return ok({"removed": removed, "freed": freed})


class ResetIn(BaseModel):
    confirm: str = ""


@app.post("/api/maintenance/reset")
def reset_data(body: ResetIn) -> dict:
    if body.confirm != "DELETE":
        raise HTTPException(400, "需要 confirm=DELETE 才能删除全部数据")
    db.reset_all()
    removed = 0
    for sub in ("uploads", "exports", "tmp"):
        root = CFG_ROOT / ".data" / sub
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    for bucket in STORE:
        STORE[bucket].clear()
    return ok({"reset": True, "files_removed": removed})


# ---------------------------------------------------------------------------
# 教学工具：量规模板 / 成绩汇总
# ---------------------------------------------------------------------------
@app.get("/api/tools/rubric/export")
def export_rubric(kind: str = Query("insight")) -> Response:
    return _file_resp(edu.export_rubric_docx(kind), f"评分量规_{kind}.docx",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/tools/grades/export")
def export_grades(project_id: Optional[int] = Query(None),
                  class_name: str = Query("")) -> Response:
    labels = {"pending": "待复核", "published": "已发布", "returned": "已退回",
              "manual": "需人工检查"}
    rows = []
    for _tid, item in _store_items("reviews", project_id):
        review = item.get("review") or {}
        status = item.get("status") or "pending"
        rows.append({
            "student": item.get("student") or "未填写",
            "file": item.get("file_name") or "",
            "ai_total": review.get("total"),
            "final_total": item.get("final_total"),
            "status": status,
            "status_label": labels.get(status, status),
            "course": (db.get_project(item.get("project_id")) or {}).get("name") or "",
        })
    if not rows:
        raise HTTPException(400, "暂无评审记录可导出")
    return _file_resp(edu.export_grades_xlsx(rows, class_name),
                      f"成绩汇总_{time.strftime('%Y%m%d')}.xlsx",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    import uvicorn
    print(f"致壹 智能教育工作台 API → http://127.0.0.1:{API_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="warning",
                timeout_keep_alive=30)
