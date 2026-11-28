"""致壹 智能教育工作台 · 本地 HTTP API。

把 Streamlit 版的真实能力（课程/文件/任务读写 + 大模型生成 + Office 导出）
包装为 REST 接口，供静态站（static-web/）调用。启动：
    python api_server.py          # 默认仅监听本机 127.0.0.1:8700

静态站默认请求 http://127.0.0.1:8700/api ；若未启动则前端回退到内置演示数据。
"""
from __future__ import annotations

import csv
import copy
import io
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

# 确保以项目根目录为工作基准，与 streamlit_app.py 行为一致
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import db, edu, agent, backup  # noqa: E402
from app import db, rehearsal_engine, auth  # noqa: E402
from app.config import ROOT as CFG_ROOT, EXPORT_DIR, PROJECT_DIR, UPLOAD_DIR, BACKUP_EXTRA_DIRS  # noqa: E402

API_PORT = int(os.getenv("EDU_API_PORT", "8700"))

app = FastAPI(title="致壹 智能教育工作台 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 登录鉴权：除公开接口外 /api/* 一律需要令牌；学生账号只能访问学生接口
# ---------------------------------------------------------------------------
_AUTH_PUBLIC = {"/api/health", "/api/auth/login", "/api/auth/logout"}


def _request_token(request: Request) -> str:
    authz = request.headers.get("authorization") or ""
    if authz.lower().startswith("bearer "):
        return authz[7:].strip()
    return (request.headers.get("x-edu-token") or request.cookies.get("edu_token") or "").strip()


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    if path in _AUTH_PUBLIC:
        return await call_next(request)
    token = _request_token(request)
    user = await run_in_threadpool(auth.resolve_token, token)
    if not user:
        return JSONResponse(status_code=401,
                            content={"ok": False, "code": "unauthorized", "error": "未登录或登录已过期"})
    request.state.user = user
    request.state.token = token
    if user.get("role") == "student":
        allowed = (path.startswith("/api/student/") or path.startswith("/api/auth/")
                   or (path == "/api/courses" and request.method == "GET"))
        if not allowed:
            return JSONResponse(status_code=403,
                                content={"ok": False, "code": "forbidden", "error": "学生账号无权访问教师端接口"})
        # 首次登录 / 被教师重置密码后，必须先改密才能进入空间
        if user.get("must_change") and not (path.startswith("/api/auth/") or path == "/api/courses"):
            return JSONResponse(status_code=403,
                                content={"ok": False, "code": "must_change", "error": "请先修改初始密码"})
    return await call_next(request)


def _user(request: Request) -> dict[str, Any]:
    return getattr(request.state, "user", {}) or {}


# 生成产物的内存热缓存；落库由下方 _store_* 完成，重启后从 SQLite 自动恢复
STORE: dict[str, dict[str, Any]] = {
    "lessons": {},      # task_id -> {project_id, topic, pkg, ts}
    "trainings": {},
    "reviews": {},
    "nextplans": {},    # task_id -> {project_id, plan, analytics, ts}
    "tutors": {},       # thread_id -> {project_id, question, history:[{role,text}], ts}
    "analytics": {},    # project_id -> {analytics, ts}
    "outlines": {},     # project_id -> {project_id, status, outline, sessions_state, ...}
}

# 这些桶的 key 是整数 task_id，从库里恢复时需要还原类型
_INT_KEY_BUCKETS = {"lessons", "trainings", "reviews", "nextplans", "outlines"}

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
                "status": meta.get("status"), "ts": ts,
                "file_id": meta.get("file_id") or 0,
                "submission_id": meta.get("submission_id") or 0,
                "submission_task_id": meta.get("submission_task_id") or 0,
                "student_no": meta.get("student_no") or ""}
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
    # 建默认教师账号、回填学生账号、清理过期会话
    auth.ensure_bootstrap()


# ---------------------------------------------------------------------------
# 健康与配置
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    key_set = bool(os.getenv("LLM_API_KEY", "") and not os.getenv("LLM_API_KEY", "").startswith("sk-REPLACE"))
    return ok({"name": "致壹 智能教育工作台 API", "llm_configured": key_set,
               "model": os.getenv("LLM_MODEL", ""), "time": int(_now())})


# ---------------------------------------------------------------------------
# 登录 / 身份
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    role: str = "teacher"      # teacher | student
    username: str = ""
    password: str = ""


class BindIn(BaseModel):
    college: str = ""
    major: str = ""
    class_name: str = ""


class PasswordIn(BaseModel):
    old_password: str = ""
    new_password: str = ""


class UpdateMeIn(BaseModel):
    """学生更新自己的个人资料（display_name / 学籍字段）。"""
    display_name: str = ""
    college: str = ""
    major: str = ""
    class_name: str = ""


@app.post("/api/auth/login")
def auth_login(body: LoginIn, request: Request):
    role = (body.role or "").strip().lower()
    if role not in ("teacher", "student"):
        raise HTTPException(400, "登录身份仅支持教师或学生")
    try:
        user, token = auth.login(role, body.username, body.password,
                                  source=request.client.host if request.client else "unknown")
    except auth.LoginRateLimited as e:
        return JSONResponse(status_code=429, headers={"Retry-After": str(e.retry_after), "Cache-Control": "no-store"},
                            content={"ok": False, "code": "rate_limited", "error": str(e)})
    if not user:
        return err(token, 401)
    return JSONResponse(content=ok({"token": token, "user": auth.public_user(user)}),
                        headers={"Cache-Control": "no-store"})


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    return ok(auth.public_user(_user(request)))


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> dict:
    token = _request_token(request)
    if token:
        db.delete_session(token)
    return ok({"logged_out": True})


@app.post("/api/auth/bind")
def auth_bind(body: BindIn, request: Request) -> dict:
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "只有学生账号需要绑定学院、专业与班级")
    college = (body.college or "").strip()
    major = (body.major or "").strip()
    class_name = (body.class_name or "").strip()
    if not (college and major and class_name):
        return err("学院、专业、班级均为必填")
    _validate_student_class(user, class_name)
    db.update_user(int(user["id"]), college=college, major=major,
                   class_name=class_name, bound=1)
    return ok(auth.public_user(db.get_user(int(user["id"]))))


@app.post("/api/auth/password")
def auth_password(body: PasswordIn, request: Request) -> dict:
    user = _user(request)
    if not auth.verify_password(body.old_password or "", user.get("password_hash") or ""):
        return err("原密码不正确")
    error = auth.password_error(body.new_password or "")
    if error:
        return err(error)
    if body.old_password == body.new_password:
        return err("新密码不能与原密码相同")
    auth.reset_password(int(user["id"]), body.new_password)
    return ok({"token": auth.new_session(int(user["id"]), str(user.get("role") or "student"))})


@app.patch("/api/auth/me")
def auth_patch_me(body: UpdateMeIn, request: Request) -> dict:
    """学生更新个人资料：display_name、学籍三字段（college/major/class_name）。
    至少传一个非空字段；若学籍三字段都填全，则自动 bound=1。"""
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "仅学生账号可修改个人资料")
    updates: dict = {}
    dn = (body.display_name or "").strip()
    col = (body.college or "").strip()
    maj = (body.major or "").strip()
    cls = (body.class_name or "").strip()
    if dn:
        updates["display_name"] = dn
    if col:
        updates["college"] = col
    if maj:
        updates["major"] = maj
    if cls:
        _validate_student_class(user, cls)
        updates["class_name"] = cls
    if not updates:
        return err("至少提供一个要修改的字段")
    if col and maj and cls:
        updates["bound"] = 1
    db.update_user(int(user["id"]), **updates)
    return ok(auth.public_user(db.get_user(int(user["id"]))))


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
def list_courses(request: Request, include_archived: bool = Query(False)) -> dict:
    rows = db.list_projects()
    if not include_archived:
        rows = [p for p in rows if (p.get("status") or "active") != "archived"]
    user = _user(request)
    if user.get("role") == "student":
        cls = (user.get("class_name") or "").strip()
        rows = [p for p in rows if user.get("bound") and cls and (p.get("class_name") or "").strip() == cls]
    return ok([_course_out(p) for p in rows])


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


@app.get("/api/courses/{cid}/rounds")
def list_course_rounds(cid: int) -> dict:
    """列出该课程根项目及其全部轮次（历史轮次即「子项目」）。"""
    p = db.get_project(cid)
    if not p:
        raise HTTPException(404, "课程不存在")
    root_id = int(p.get("parent_id") or p["id"])
    out = []
    for r in db.list_rounds(root_id):
        meta = {}
        items = db.list_artifacts("rounds", project_id=int(r["id"]))
        if items:
            meta = items[0][1] or {}
        out.append({
            "id": r["id"],
            "name": r["name"],
            "round": int(r.get("round") or 1),
            "status": r.get("status") or "active",
            "archived_at": r.get("archived_at"),
            "progress": r.get("progress") or "",
            "current_session": int(r.get("current_session") or 0),
            "total_sessions": int(r.get("total_sessions") or 0),
            "file_count": int(r.get("file_count") or 0),
            "task_count": int(r.get("task_count") or 0),
            "zip_file_id": meta.get("zip_file_id"),
        })
    return ok({"root_id": root_id, "rounds": out})


# 归档后带入新一轮的教学资料分类
TEACHING_FILE_CATEGORIES = ("教材", "课件", "案例", "评分标准", "试题")


class RoundIn(BaseModel):
    name: Optional[str] = None
    class_: Optional[str] = Field(None, alias="class")
    class_name: Optional[str] = None
    classSize: Optional[int] = None
    totalHours: Optional[int] = None
    totalSessions: Optional[int] = None
    hours: Optional[str] = None
    textbook: Optional[str] = None
    textbook_version: Optional[str] = None
    objectives: Optional[str] = None
    key: Optional[str] = None
    key_points: Optional[str] = None
    diff: Optional[str] = None
    difficulties: Optional[str] = None
    note: Optional[str] = None
    desc: Optional[str] = None
    description: Optional[str] = None
    audience: Optional[str] = None


def _unique_project_name(base: str) -> str:
    """课程名在库里唯一，重名时追加序号。"""
    names = {p.get("name") for p in db.list_projects(limit=1000)}
    if base not in names:
        return base
    i = 2
    while f"{base}（{i}）" in names:
        i += 1
    return f"{base}（{i}）"


@app.post("/api/courses/{cid}/rounds/archive")
def archive_course_round(cid: int, body: RoundIn) -> dict:
    """归档当前轮次：打包 ZIP + 标记旧项目为历史轮次 + 创建新一轮（保留教学进度）。"""
    p = db.get_project(cid)
    if not p:
        raise HTTPException(404, "课程不存在")
    if (p.get("status") or "active") == "archived":
        raise HTTPException(400, "该课程已归档，不能重复归档")

    root_id = int(p.get("parent_id") or p["id"])
    round_no = int(p.get("round") or 1)

    pkg = edu.build_round_archive(cid)
    zip_name = f"第{round_no}轮教学归档_{time.strftime('%Y%m%d')}.zip"
    try:
        zip_id = db.save_file(
            name=zip_name, ext="ZIP", kind="doc", content=pkg["zip"],
            size=len(pkg["zip"]), project_id=cid, visibility="teacher",
            category="归档", ai_context=0, parse_status="parsed",
        )
    except Exception as e:
        raise HTTPException(500, f"归档包保存失败：{e}")

    db.archive_project(cid)

    raw_name = (body.name or p.get("name") or "未命名课程").strip()
    base_name = re.sub(r"（第\d+轮）$", "", raw_name) or raw_name
    new_pid = db.create_project(
        _unique_project_name(f"{base_name}（第{round_no + 1}轮）"),
        description=(body.description or body.desc or p.get("description") or ""),
    )
    db.update_course(
        new_pid,
        audience=body.audience or p.get("audience"),
        class_name=body.class_ or body.class_name or p.get("class_name"),
        hours=(str(int(body.totalHours)) if body.totalHours is not None
               else (body.hours or p.get("hours"))),
        textbook_version=body.textbook or body.textbook_version or p.get("textbook_version"),
        objectives=body.objectives or p.get("objectives"),
        key_points=body.key or body.key_points or p.get("key_points"),
        difficulties=body.diff or body.difficulties or p.get("difficulties"),
        progress=(p.get("progress") or ""),
        class_size=(body.classSize if body.classSize is not None else p.get("class_size")),
        current_session=int(p.get("current_session") or 0),
        total_sessions=(body.totalSessions if body.totalSessions is not None
                        else p.get("total_sessions")),
        note=(body.note if body.note is not None else p.get("note")),
    )
    db.set_project_round(new_pid, root_id, round_no + 1)

    copied = 0
    for f in db.list_files(project_id=cid, limit=500):
        if (f.get("category") or "") not in TEACHING_FILE_CATEGORIES:
            continue
        full = db.get_file(int(f["id"]), with_content=True) or {}
        db.save_file(
            name=full.get("name") or f["name"],
            ext=full.get("ext") or f.get("ext") or "",
            kind=full.get("kind") or f.get("kind") or "doc",
            content=full.get("content"),
            size=int(full.get("size") or 0),
            rows=int(full.get("rows") or 0),
            cols=int(full.get("cols") or 0),
            chars=int(full.get("chars") or 0),
            parsed_text=full.get("parsed_text"),
            project_id=new_pid,
            visibility=full.get("visibility") or "teacher",
            category=full.get("category") or "",
            ai_context=int(full.get("ai_context") or 1),
            parse_status=full.get("parse_status") or "parsed",
        )
        copied += 1

    db.save_artifact("rounds", cid, {
        "round": round_no, "zip_file_id": zip_id, "next_id": new_pid,
        "archived_at": time.time(), "copied_files": copied,
    }, project_id=cid)
    return ok({"archived_id": cid, "next": _course_out(db.get_project(new_pid)),
               "zip_file_id": zip_id, "copied_files": copied})


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


@app.get("/api/files/{fid}/download")
def download_file(fid: int) -> Response:
    f = db.get_file(fid, with_content=True)
    if not f:
        raise HTTPException(404, "文件不存在")
    content = f.get("content") or b""
    if not content:
        raise HTTPException(404, "文件内容为空")
    ext = (f.get("ext") or "").upper()
    media = {
        "ZIP": "application/zip", "PDF": "application/pdf",
        "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "TXT": "text/plain; charset=utf-8", "CSV": "text/csv; charset=utf-8",
    }.get(ext, "application/octet-stream")
    return _file_resp(content, f.get("name") or f"file.{ext.lower()}", media)


@app.get("/api/files/{fid}/text")
def get_file_text(fid: int) -> dict:
    return ok({"text": db.get_file_text(fid) or ""})


# ---------------------------------------------------------------------------
# 学生名单：xlsx / csv 导入（学号 / 姓名 / 班级）、查看、清空
# ---------------------------------------------------------------------------
_STU_HEAD_ALIASES = {
    "student_no": ("学号", "学籍号", "学生学号", "studentno", "student_no", "no"),
    "name": ("姓名", "学生姓名", "名字", "name", "student"),
    "class_name": ("班级", "行政班级", "教学班", "class", "classname", "class_name"),
}


def _norm_head(v: Any) -> str:
    return re.sub(r"[\s\u3000:：()（）]", "", str(v or "")).lower()


def _cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _read_sheet_rows(name: str, data: bytes) -> list[list[Any]]:
    ext = Path(name).suffix.lower()
    if ext == ".csv":
        text = None
        for enc in ("utf-8-sig", "gbk", "utf-8"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise HTTPException(400, "CSV 编码无法识别，请另存为 UTF-8 后重试")
        return [row for row in csv.reader(io.StringIO(text))]
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if ext == ".xls":
        raise HTTPException(400, "不支持旧版 .xls，请另存为 .xlsx 或 .csv 后重试")
    raise HTTPException(400, "仅支持 .xlsx / .csv 名单文件")


def _parse_students(name: str, data: bytes, default_class: str = "") -> dict[str, Any]:
    rows = _read_sheet_rows(name, data)
    if not rows:
        raise HTTPException(400, "文件为空，未读取到任何行")

    head_idx, col_map = -1, {}
    for i, row in enumerate(rows[:10]):
        m: dict[str, int] = {}
        for j, cell in enumerate(row):
            h = _norm_head(cell)
            if not h:
                continue
            for key, aliases in _STU_HEAD_ALIASES.items():
                if key not in m and any(h == _norm_head(a) for a in aliases):
                    m[key] = j
        if "student_no" in m and "name" in m:
            head_idx, col_map = i, m
            break
    if head_idx < 0:
        raise HTTPException(400, "未识别到表头：文件前 10 行需包含「学号」和「姓名」两列")

    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = 0
    for i in range(head_idx + 1, len(rows)):
        row = rows[i]
        excel_row = i + 1

        def pick(key: str) -> str:
            j = col_map.get(key)
            return _cell_text(row[j]) if j is not None and j < len(row) else ""

        no, nm = pick("student_no"), pick("name")
        cls = pick("class_name") or default_class
        if not no and not nm:
            skipped += 1
            continue
        if not no:
            errors.append({"row": excel_row, "reason": "缺少学号", "name": nm})
            continue
        if not nm:
            errors.append({"row": excel_row, "reason": "缺少姓名", "student_no": no})
            continue
        if no in seen:
            errors.append({"row": excel_row, "reason": "文件内学号重复", "student_no": no, "name": nm})
            continue
        seen.add(no)
        items.append({"student_no": no, "name": nm, "class_name": cls, "row_no": excel_row})
    return {"items": items, "errors": errors, "skipped": skipped, "head_row": head_idx + 1}


@app.post("/api/students/import")
def import_students_api(response: Response, project_id: int = Form(...), file: UploadFile = File(...)) -> dict:
    if not db.get_project(project_id):
        raise HTTPException(404, "课程项目不存在")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "文件为空")
    name = file.filename or "名单"
    proj = db.get_project(project_id) or {}
    parsed = _parse_students(name, data, default_class=(proj.get("class_name") or ""))
    res = db.import_students(project_id, parsed["items"], source_file=name)
    # 名单里的学号同步开通学生账号（已有账号不覆盖密码与绑定信息）
    accounts = 0
    for it in parsed["items"]:
        if auth.ensure_student_user(it["student_no"], it["name"], it["class_name"]):
            accounts += 1
    response.headers["Cache-Control"] = "no-store"
    total = db.count_students(project_id)
    errs = parsed["errors"][:50]
    msg = f"新增 {res['added']} 人，更新 {res['updated']} 人"
    if accounts:
        msg += f"，新开通 {accounts} 个学生账号"
    if parsed["errors"]:
        msg += f"，跳过 {len(parsed['errors'])} 行异常"
    if parsed["skipped"]:
        msg += f"，忽略 {parsed['skipped']} 个空行"
    return ok({
        "file": name, "added": res["added"], "updated": res["updated"],
        "accounts_created": accounts,
        "skipped": parsed["skipped"], "error_count": len(parsed["errors"]),
        "errors": errs, "total": total, "message": msg,
    })


@app.get("/api/students")
def list_students_api(project_id: int = Query(...)) -> dict:
    items = db.list_students(project_id)
    classes: list[str] = []
    for s in items:
        c = (s.get("class_name") or "").strip()
        if c and c not in classes:
            classes.append(c)
    last = max((s.get("updated_at") or 0) for s in items) if items else 0
    return ok({"items": items, "total": len(items), "classes": classes, "last_import_at": last})


@app.delete("/api/students")
def clear_students_api(project_id: int = Query(...)) -> dict:
    n = db.clear_students(project_id)
    return ok({"deleted": n})


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


class TaskPublishIn(BaseModel):
    project_id: int
    title: str
    description: str = ""
    due: str = ""
    audience: Optional[list[str]] = None


@app.post("/api/tasks/publish")
def publish_task(body: TaskPublishIn, request: Request) -> dict:
    """教师一键发布班级任务（kind=homework），学生端按发布班级匹配后出现在首页。"""
    user = _user(request)
    if user.get("role") == "student":
        raise HTTPException(403, "仅教师可发布任务")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "任务标题不能为空")
    pid = int(body.project_id)
    if not db.get_project(pid):
        raise HTTPException(404, "课程项目不存在")
    desc = (body.description or "").strip()
    # 防重复下发：10 秒内同标题同描述视为重复点击，直接返回已有任务
    for t in db.list_tasks(project_id=pid, kind="homework", limit=20):
        meta = t.get("meta") or {}
        if (t.get("prompt") or "").strip() == title and (meta.get("description") or "").strip() == desc \
                and (time.time() - float(t.get("created_at") or 0)) < 10:
            return ok({"task_id": t.get("id"), "duplicate": True})
    classes = [str(c).strip() for c in (body.audience or []) if str(c).strip()]
    meta = {
        "published": True,
        "type": "homework",
        "description": desc,
        "due": (body.due or "").strip(),
        "audience": {"classes": classes},
        "published_at": time.time(),
        "publisher": str(user.get("display_name") or user.get("username") or "教师"),
    }
    tid = db.save_task(prompt=title, kind="homework", status="ok", project_id=pid, meta=meta)
    return ok({"task_id": tid, "duplicate": False,
               "audience": classes, "title": title})


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
    task = db.get_task(tid) or {}
    pkg = dict(item["pkg"])
    pkg["_published"] = bool((task.get("meta") or {}).get("published"))
    pkg["_audience"] = ((task.get("meta") or {}).get("audience") or {}).get("classes") or []
    return ok(pkg)


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
# 备课大纲（agent 工作流：生成大纲 → 教师审查 → 通过后按讲次生成备课包）
# ---------------------------------------------------------------------------
class OutlineIn(BaseModel):
    project_id: int
    extra: str = ""
    total_sessions: Optional[int] = None
    total_hours: Optional[int] = None
    teacher_note: str = ""


class OutlineUpdateIn(BaseModel):
    outline: Optional[dict] = None
    teacher_note: Optional[str] = None


class OutlineReviseIn(BaseModel):
    teacher_note: str = ""


# 批量生成进度（进程内）：project_id -> {running, cancel, total, done, current, failed}
_OUTLINE_JOBS: dict[int, dict[str, Any]] = {}


def _new_outline_item(project_id: int, outline: dict[str, Any],
                      version: int = 1, teacher_note: str = "",
                      ask: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    return {
        "project_id": project_id,
        "status": "draft",           # draft | edited | approved
        "version": version,
        "ask": ask or {},            # 生成要求（讲次数/课时/补充要求），按意见重写时沿用
        "teacher_note": teacher_note,
        "created": now,
        "updated": now,
        "approved_at": None,
        "outline": outline,
        "sessions_state": {},        # "1" -> {status: pending|generating|generated|failed, task_id, error}
        "job": None,
    }


def _persist_outline_lesson(project_id: int, topic: str, pkg: dict[str, Any],
                            session_no: int, outline_version: int,
                            materials: list[str] | None = None) -> int:
    """把大纲某一讲生成的备课包存入 lessons 桶（与一键备课共用同一条导出链路）。"""
    meta = {"pkg": pkg, "topic": topic, "version": "v1",
            "materials": materials or [], "model": "默认", "review_model": "",
            "dual_check": False, "lesson_type": "新授课",
            "outputs": [], "created": _now(), "params": {},
            "outline_version": outline_version, "outline_session": session_no,
            "review_status": "待教师确认", "issues": []}
    tid = db.save_task(prompt=topic, answer="备课包已生成", kind="lesson", status="ok",
                       duration_s=0.0, project_id=project_id, meta=meta)
    _store_put("lessons", tid, {"project_id": project_id, "topic": topic, "pkg": pkg,
                                "materials": materials or [], "version": "v1",
                                "ts": _now()})
    return tid


def _generate_outline_session(pid: int, item: dict[str, Any], no: int) -> int:
    """按大纲第 no 讲生成一份完整备课包，返回 task_id。"""
    outline = item.get("outline") or {}
    target = next((s for s in (outline.get("sessions") or [])
                   if isinstance(s, dict) and int(s.get("no") or 0) == int(no)), None)
    if not target:
        raise ValueError(f"大纲中不存在第 {no} 讲")
    ctx = edu.outline_session_context(outline, no)
    pkg = edu.generate_lesson_package(
        pid, str(target.get("topic") or f"第 {no} 讲"),
        hours=f"{target.get('hours') or 2} 课时",
        outputs=target.get("outputs") or None,
        outline_ctx=ctx,
    )
    return _persist_outline_lesson(pid, str(target.get("topic") or f"第 {no} 讲"), pkg,
                                   no, int(item.get("version") or 1))


@app.post("/api/outline/generate")
def outline_generate(body: OutlineIn) -> dict:
    if not db.get_project(body.project_id):
        raise HTTPException(404, "课程不存在")
    try:
        outline = edu.generate_course_outline(
            body.project_id, extra=body.extra,
            total_sessions=body.total_sessions, total_hours=body.total_hours,
            teacher_note=body.teacher_note)
    except Exception as e:
        return err(f"生成大纲失败：{e.__class__.__name__}: {e}", 500)
    old = _store_get("outlines", body.project_id) or {}
    item = _new_outline_item(body.project_id, outline,
                             version=int(old.get("version") or 0) + 1,
                             teacher_note=body.teacher_note,
                             ask={"total_sessions": body.total_sessions,
                                  "total_hours": body.total_hours,
                                  "extra": body.extra})
    _store_put("outlines", body.project_id, item)
    return ok(item)


@app.get("/api/outline")
def outline_get(project_id: int = Query(...)) -> dict:
    return ok(_store_get("outlines", project_id) or {})


@app.put("/api/outline/{pid}")
def outline_update(pid: int, body: OutlineUpdateIn) -> dict:
    item = _store_get("outlines", pid)
    if not item:
        raise HTTPException(404, "大纲不存在")
    if body.outline is not None:
        item["outline"] = edu.normalize_outline(body.outline, db.get_project(pid))
        if item.get("status") != "approved":
            item["status"] = "edited"
    if body.teacher_note is not None:
        item["teacher_note"] = body.teacher_note
    item["updated"] = _now()
    _store_put("outlines", pid, item)
    return ok(item)


@app.post("/api/outline/{pid}/revise")
def outline_revise(pid: int, body: OutlineReviseIn) -> dict:
    """对话式修改：教师给意见，agent 重写整份大纲（版本 +1，需重新审查）。"""
    item = _store_get("outlines", pid)
    if not item:
        raise HTTPException(404, "大纲不存在")
    note = (body.teacher_note or "").strip()
    if not note:
        raise HTTPException(400, "请先填写修改意见")
    ask = item.get("ask") or {}
    try:
        outline = edu.generate_course_outline(
            pid, teacher_note=note,
            extra=ask.get("extra") or "",
            total_sessions=ask.get("total_sessions"),
            total_hours=ask.get("total_hours"))
    except Exception as e:
        return err(f"按意见重写失败：{e.__class__.__name__}: {e}", 500)
    item["outline"] = outline
    item["status"] = "draft"
    item["version"] = int(item.get("version") or 0) + 1
    item["teacher_note"] = note
    item["updated"] = _now()
    item["approved_at"] = None
    # 大纲已变，之前按旧大纲生成的讲次不再对应当前大纲，需要重新生成
    item["sessions_state"] = {}
    _store_put("outlines", pid, item)
    return ok(item)


@app.post("/api/outline/{pid}/approve")
def outline_approve(pid: int) -> dict:
    item = _store_get("outlines", pid)
    if not item:
        raise HTTPException(404, "大纲不存在")
    sessions = [s for s in ((item.get("outline") or {}).get("sessions") or [])
                if isinstance(s, dict)]
    if not sessions:
        raise HTTPException(400, "大纲没有讲次，无法通过审查")
    item["status"] = "approved"
    item["approved_at"] = _now()
    item["updated"] = _now()
    _store_put("outlines", pid, item)
    return ok(item)


@app.post("/api/outline/{pid}/sessions/{no}/generate")
def outline_generate_one(pid: int, no: int) -> dict:
    item = _store_get("outlines", pid)
    if not item:
        raise HTTPException(404, "大纲不存在")
    if item.get("status") != "approved":
        raise HTTPException(400, "请先通过备课大纲审查，再生成备课包")
    try:
        tid = _generate_outline_session(pid, item, no)
    except Exception as e:
        item.setdefault("sessions_state", {})[str(no)] = {
            "status": "failed", "error": f"{e.__class__.__name__}: {e}", "task_id": None}
        _store_put("outlines", pid, item)
        return err(f"生成第 {no} 讲失败：{e.__class__.__name__}: {e}", 500)
    item.setdefault("sessions_state", {})[str(no)] = {"status": "generated", "task_id": tid}
    item["updated"] = _now()
    _store_put("outlines", pid, item)
    return ok({"task_id": tid, "session_no": no})


def _run_outline_batch(pid: int, session_nos: list[int]) -> None:
    job = _OUTLINE_JOBS.setdefault(pid, {})
    job.update({"running": True, "cancel": False, "total": len(session_nos),
                "done": 0, "current": None, "failed": [], "started": _now()})
    try:
        for no in session_nos:
            if job.get("cancel"):
                break
            item = _store_get("outlines", pid)
            if not item:
                break
            state = item.setdefault("sessions_state", {})
            state[str(no)] = {"status": "generating",
                              "task_id": (state.get(str(no)) or {}).get("task_id")}
            item["job"] = {"running": True, "total": job["total"], "done": job["done"],
                           "current": no, "failed": list(job["failed"])}
            _store_put("outlines", pid, item)
            job["current"] = no
            try:
                tid = _generate_outline_session(pid, item, no)
                state[str(no)] = {"status": "generated", "task_id": tid}
            except Exception as e:  # 单讲失败不阻断后续讲次
                state[str(no)] = {"status": "failed", "task_id": None,
                                  "error": f"{e.__class__.__name__}: {e}"}
                job["failed"].append(no)
            job["done"] += 1
            item["job"] = {"running": True, "total": job["total"], "done": job["done"],
                           "current": no, "failed": list(job["failed"])}
            item["updated"] = _now()
            _store_put("outlines", pid, item)
    finally:
        job["running"] = False
        job["current"] = None
        item = _store_get("outlines", pid)
        if item:
            item["job"] = {"running": False, "total": job.get("total"), "done": job.get("done"),
                           "current": None, "failed": list(job.get("failed") or []),
                           "finished": _now()}
            item["updated"] = _now()
            _store_put("outlines", pid, item)


@app.post("/api/outline/{pid}/generate-all")
def outline_generate_all(pid: int) -> dict:
    item = _store_get("outlines", pid)
    if not item:
        raise HTTPException(404, "大纲不存在")
    if item.get("status") != "approved":
        raise HTTPException(400, "请先通过备课大纲审查，再批量生成备课包")
    job = _OUTLINE_JOBS.get(pid)
    if job and job.get("running"):
        raise HTTPException(400, "该课程正在批量生成，请等待完成")
    state = item.get("sessions_state") or {}
    sessions = [s for s in ((item.get("outline") or {}).get("sessions") or [])
                if isinstance(s, dict)]
    todo = [int(s["no"]) for s in sessions
            if (state.get(str(s.get("no"))) or {}).get("status") != "generated"]
    if not todo:
        return ok({"started": False, "total": 0, "message": "全部讲次均已生成"})
    threading.Thread(target=_run_outline_batch, args=(pid, todo), daemon=True).start()
    return ok({"started": True, "total": len(todo)})


@app.post("/api/outline/{pid}/generate-all/cancel")
def outline_generate_all_cancel(pid: int) -> dict:
    job = _OUTLINE_JOBS.get(pid)
    if not job or not job.get("running"):
        return ok({"cancelled": False, "message": "当前没有进行中的批量生成"})
    job["cancel"] = True
    return ok({"cancelled": True})


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


@app.get("/api/training/templates")
def training_templates() -> dict:
    """实训场景模板：供前端一键填入场景描述。"""
    return ok(edu.training_templates())


@app.get("/api/training/{tid}")
def get_training(tid: int) -> dict:
    item = _store_get("trainings", tid)
    if not item:
        raise HTTPException(404, "实训包不存在")
    task = db.get_task(tid) or {}
    pkg = dict(item["pkg"])
    pkg["_audience"] = ((task.get("meta") or {}).get("audience") or {}).get("classes") or []
    return ok(pkg)


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
                     "status": v.get("status") or "ai", "ts": v["ts"],
                     "file_id": v.get("file_id") or 0,
                     "submission_id": v.get("submission_id") or 0,
                     "student_no": v.get("student_no") or ""})
    return ok(rows)


@app.get("/api/review/rubrics")
def review_rubrics() -> dict:
    """评分量规模板列表（复用 edu.RUBRIC_TEMPLATES）。"""
    rows = [{"key": k, "name": (v or {}).get("name") or k, "rows": (v or {}).get("rows") or []}
            for k, v in edu.RUBRIC_TEMPLATES.items()]
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
    if body.status == "returned" and not body.reason.strip():
        raise HTTPException(400, "退回时必须填写原因")
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
        "student": student, "class_name": class_name or old_meta.get("class_name", ""),
        "files": [file_name] if file_name else [], "file": file_name,
        "task": old_meta.get("task", ""), "rubric_name": old_meta.get("rubric_name", ""),
        "rubric": old_meta.get("rubric") or [],
        "ai": review,
        "teacher": {"scores": scores, "total": final_total,
                    "comment": comment, "reason": body.reason},
        "accepted": accepted, "final_total": final_total, "status": body.status,
        "versions": versions,
        # 学生提交链路字段：终评时不能丢，否则学生端无法把反馈挂回任务
        "file_id": old_meta.get("file_id") or 0,
        "student_no": old_meta.get("student_no") or "",
        "submission_id": old_meta.get("submission_id") or 0,
        "submission_task_id": old_meta.get("submission_task_id") or 0,
        "submission_version": old_meta.get("submission_version") or 0,
    }
    if task:
        db.update_task(tid, answer=comment, meta=meta)
    item.update({"student": student, "file_name": file_name,
                 "teacher": meta["teacher"], "accepted": accepted,
                 "final_total": final_total, "status": body.status})
    _store_put("reviews", tid, item)
    # 学生提交的记录：将结果仅同步到对应的历史版本
    new_status = {"published": "reviewed", "returned": "returned"}.get(body.status, "submitted")
    db.update_submission_version_result(
        tid, status=new_status,
        score=final_total if body.status == "published" else None,
        feedback=(body.reason or comment or "") if body.status == "returned" else (comment or ""),
    )
    return ok({"task_id": tid, "ai_total": ai_total, "final_total": final_total,
               "status": body.status, "teacher": meta["teacher"]})


class ReviewBatchIn(BaseModel):
    ids: list[int]
    status: str
    reason: str = ""
    comment: Optional[str] = None


@app.post("/api/review/batch")
def batch_finalize_reviews(body: ReviewBatchIn) -> dict:
    ids = list(dict.fromkeys(body.ids or []))
    if not ids or len(ids) > 100:
        raise HTTPException(400, "ids 数量必须为 1 到 100")
    if body.status not in ("published", "returned"):
        raise HTTPException(400, "status 仅支持 published / returned")
    if body.status == "returned" and not body.reason.strip():
        raise HTTPException(400, "退回时必须填写原因")
    results = []
    for tid in ids:
        try:
            finalize_review(tid, ReviewFinalizeIn(status=body.status, reason=body.reason,
                                                    comment=body.comment))
            results.append({"task_id": tid, "ok": True})
        except HTTPException as exc:
            results.append({"task_id": tid, "ok": False, "error": str(exc.detail)})
    success_count = sum(1 for result in results if result["ok"])
    return ok({"results": results, "success_count": success_count,
               "failed_count": len(results) - success_count})


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
    if ctx:
        ctx = ("以下课程上下文仅供参考（与问题无关或缺失时可忽略，不得因此拒绝回答）：\n" + ctx)
    try:
        # assistant 模式：直接用大模型自身能力作答，课程资料不作为限制条件
        res = agent.run(body.prompt, chat_history=[], context=ctx or "", mode="assistant")
    except Exception as e:
        return err(f"助手异常：{e.__class__.__name__}: {e}", 500)
    output = res.get("output") or res.get("error") or "(无输出)"
    tid = db.save_task(prompt=body.prompt, answer=output, kind="agent",
                       status="ok" if res.get("status") == "ok" else "error",
                       duration_s=round(_now() - t0, 1), project_id=body.project_id)
    return ok({"task_id": tid, "status": res.get("status"), "output": output,
               "steps": len(res.get("intermediate_steps") or [])})


class AssistantSaveIn(BaseModel):
    project_id: Optional[int] = None
    title: str = "AI 助手回答"
    content: str
    task_id: Optional[int] = None


@app.post("/api/assistant/save")
def assistant_save(body: AssistantSaveIn) -> dict:
    """把 AI 回答保存为当前课程的文本资料（教师可见），可在备课/答疑中引用。"""
    text = (body.content or "").strip()
    if not text:
        raise HTTPException(400, "内容为空，无法保存")
    title = (body.title or "AI 助手回答").strip()[:40] or "AI 助手回答"
    name = title + ".txt"
    try:
        fid = db.save_file(
            name=name, ext="TXT", kind="doc", content=text.encode("utf-8"),
            size=len(text.encode("utf-8")), chars=len(text), parsed_text=text,
            project_id=body.project_id, visibility="teacher", category="其他",
            ai_context=1,
        )
    except Exception as e:
        raise HTTPException(500, f"保存失败：{e}")
    if body.task_id:
        task = db.get_task(body.task_id)
        if task:
            meta = task.get("meta") or {}
            meta["saved_file_id"] = fid
            db.update_task(body.task_id, meta=meta)
    return ok({"id": fid, "name": name})


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
# 学生空间（一律按登录学生做数据隔离）
# ---------------------------------------------------------------------------
def _stu_key(t: dict) -> str:
    meta = t.get("meta") or {}
    return str(meta.get("student_no") or "").strip()


def _matches_student(t: dict, keys: set[str], *, student_mode: bool = False) -> bool:
    if student_mode:
        return bool(keys) and _stu_key(t) in keys
    legacy = str((t.get("meta") or {}).get("student") or "").strip()
    return not keys or _stu_key(t) in keys or legacy in keys


def _student_keys(user: dict) -> set[str]:
    """Authorization uses the immutable student number, never an editable name."""
    keys = {str(user.get("student_no") or "").strip()}
    return {k for k in keys if k}


def _enrollments(user: dict) -> list[dict]:
    no = str(user.get("student_no") or "").strip()
    return db.student_enrollments(no) if no else []


def _validate_student_class(user: dict, class_name: str) -> None:
    classes = {str(s.get("class_name") or "").strip() for s in _enrollments(user)}
    if not class_name or class_name not in classes:
        raise HTTPException(403, "班级与教师导入的名单不符，请联系教师确认")


def _student_project(user: dict, project_id: Optional[int]) -> Optional[int]:
    ids = [int(c["id"]) for c in _student_courses(user)]
    if project_id is not None:
        if project_id not in ids:
            raise HTTPException(403, "该课程不在你的名单范围")
        return project_id
    return ids[0] if ids else None


def _student_class(user: dict, project_id: Optional[int]) -> str:
    return next((str(s.get("class_name") or "").strip() for s in _enrollments(user)
                 if s.get("project_id") == project_id), "")


def _student_task(t: dict) -> dict:
    """Only release student-facing fields, not the teacher's generated package."""
    meta = t.get("meta") or {}
    public = {k: meta[k] for k in ("description", "due", "published", "published_at") if k in meta}
    public["pkg"] = {"title": (meta.get("pkg") or {}).get("title") or t.get("prompt") or ""}
    return {k: t.get(k) for k in ("id", "kind", "project_id", "prompt", "created_at")} | {"meta": public}


def _student_record(t: dict) -> dict:
    meta = t.get("meta") or {}
    fields = ("student_no", "status", "knowledge_point", "error_type")
    public = {k: meta[k] for k in fields if k in meta}
    if t.get("kind") == "review":
        public.update({k: meta[k] for k in ("file", "submission_task_id") if k in meta})
        teacher = meta.get("teacher") or {}
        teacher_fields = ("total", "comment", "reason", "scores") if meta.get("status") == "published" else ("comment", "reason")
        public["teacher"] = {k: teacher[k] for k in teacher_fields if k in teacher}
        if meta.get("status") == "published":
            public["final_total"] = meta.get("final_total")
    return {k: t.get(k) for k in ("id", "kind", "project_id", "prompt", "created_at")} | {"meta": public}


def _released_review(t: dict) -> bool:
    return (t.get("meta") or {}).get("status") in ("published", "returned")


def _audience_match(t: dict, class_name: str) -> bool:
    """发布范围：meta.audience 为空 / classes 为空 表示全部班级；否则需包含学生班级。"""
    aud = (t.get("meta") or {}).get("audience") or {}
    classes = [str(x).strip() for x in (aud.get("classes") or []) if str(x).strip()]
    if not classes:
        return True
    return (class_name or "").strip() in classes


def _published_lessons(project_id: Optional[int], class_name: str = "") -> list[dict[str, Any]]:
    return [t for t in db.list_tasks(project_id=project_id, kind="lesson", limit=100)
            if bool((t.get("meta") or {}).get("published")) and _audience_match(t, class_name)]


def _published_trainings(project_id: Optional[int], class_name: str = "") -> list[dict[str, Any]]:
    return [t for t in db.list_tasks(project_id=project_id, kind="training", limit=100)
            if str(((t.get("meta") or {}).get("pkg") or {}).get("status") or "") == "published"
            and _audience_match(t, class_name)]


def _published_homework(project_id: Optional[int], class_name: str = "") -> list[dict[str, Any]]:
    """教师一键发布的班级任务（kind=homework）。"""
    return [t for t in db.list_tasks(project_id=project_id, kind="homework", limit=100)
            if bool((t.get("meta") or {}).get("published")) and _audience_match(t, class_name)]


def _wrong_payload(project_id: Optional[int], keys: set[str], *, student_mode: bool = False) -> dict[str, Any]:
    """错题本：由真实评审低分维度与答疑错因派生，无数据时返回空列表。"""
    items: list[dict[str, Any]] = []
    for t in db.list_tasks(project_id=project_id, kind="review", limit=200,
                          student_keys=keys if student_mode else None, released_only=student_mode):
        if student_mode and (not keys or not _released_review(t)):
            continue
        if not _matches_student(t, keys, student_mode=student_mode):
            continue
        meta = t.get("meta") or {}
        ai = meta.get("ai") or {}
        topic = meta.get("file") or t.get("prompt") or "作业"
        for d in ([] if student_mode and meta.get("status") != "published" else ai.get("dimensions") or []):
            if student_mode:
                scores = (meta.get("teacher") or {}).get("scores") or {}
                if d.get("name") not in scores:
                    continue
                d = {"name": d.get("name"), "score": scores[d["name"]], "max": d.get("max")}
            try:
                score = float(d.get("score") or 0)
                mx = float(d.get("max") or 0)
            except (TypeError, ValueError):
                continue
            if mx <= 0 or score / mx >= 0.6:
                continue
            items.append({
                "topic": topic,
                "knowledge_point": d.get("name") or d.get("dimension") or "",
                "mastery": f"{round(score / mx * 100)}%",
                "last_error": (d.get("evidence") or d.get("suggestion") or "")[:60],
                "status": "待订正",
                "ts": t.get("created_at") or 0,
            })
    for t in db.list_tasks(project_id=project_id, kind="qa", limit=200,
                          student_keys=keys if student_mode else None):
        if student_mode and not keys:
            continue
        if not _matches_student(t, keys, student_mode=student_mode):
            continue
        meta = t.get("meta") or {}
        et = (meta.get("error_type") or "").strip()
        if not et:
            continue
        items.append({
            "topic": (t.get("prompt") or "答疑")[:40],
            "knowledge_point": meta.get("knowledge_point") or "",
            "mastery": "—",
            "last_error": et,
            "status": "已讲解",
            "ts": t.get("created_at") or 0,
        })
    items.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    corrected = len([i for i in items if i["status"] == "已讲解"])
    return {"items": items, "total": len(items), "corrected": corrected}


def _student_courses(user: dict) -> list[dict[str, Any]]:
    """Course access is granted by the teacher's roster, not profile fields."""
    if not user.get("bound"):
        return []
    enrolled = {s["project_id"] for s in _enrollments(user)}
    return [_course_out(p) for p in db.list_projects()
            if (p.get("status") or "active") != "archived"
            and p["id"] in enrolled]


@app.get("/api/student/overview")
def student_overview(request: Request, project_id: Optional[int] = Query(None),
                     offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)) -> dict:
    """学生空间首页汇总：身份、可访问课程、已发布任务、我的反馈/答疑/错题。"""
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "仅学生账号可访问")
    courses = _student_courses(user)
    pid = _student_project(user, project_id)
    keys = _student_keys(user)
    cls = _student_class(user, pid)
    lessons = _published_lessons(pid, cls) if pid else []
    trainings = _published_trainings(pid, cls) if pid else []
    homework = _published_homework(pid, cls) if pid else []
    reviews = ([t for t in db.list_tasks(project_id=pid, kind="review", limit=limit + 1,
                                        offset=offset, student_keys=keys, released_only=True)
                if _stu_key(t) in keys and _released_review(t)] if pid else [])
    qa = ([t for t in db.list_tasks(project_id=pid, kind="qa", limit=limit + 1,
                                   offset=offset, student_keys=keys)
           if _stu_key(t) in keys] if pid else [])
    wrong = _wrong_payload(pid, keys, student_mode=True) if pid else {"items": [], "total": 0, "corrected": 0}
    submissions = (db.list_submissions(pid, str(user.get("student_no") or "")) if pid else [])
    return ok({
        "profile": auth.public_user(user),
        "courses": courses,
        "project_id": pid,
        "lessons": [_student_task(t) for t in lessons],
        "trainings": [_student_task(t) for t in trainings],
        "homework": [_student_task(t) for t in homework],
        "my_reviews": [_student_record(t) for t in reviews[:limit]],
        "my_qa": [_student_record(t) for t in qa[:limit]],
        "pagination": {"offset": offset, "limit": limit, "reviews_has_more": len(reviews) > limit,
                       "qa_has_more": len(qa) > limit},
        "my_submissions": submissions,
        "wrong": wrong,
    })


@app.get("/api/student/dashboard")
def student_dashboard(request: Request, project_id: Optional[int] = Query(None),
                      student: str = Query("")) -> dict:
    user = _user(request)
    if user.get("role") == "student":
        result = student_overview(request, project_id, offset=0, limit=200)
        result["data"]["tutor_threads"] = []
        return result
    else:
        keys = {student.strip()} if student.strip() else set()
    reviews = [t for t in db.list_tasks(project_id=project_id, kind="review", limit=200)
               if _matches_student(t, keys)]
    qa = [t for t in db.list_tasks(project_id=project_id, kind="qa", limit=200)
          if _matches_student(t, keys)]
    return ok({
        "my_qa": qa, "my_reviews": reviews,
        "trainings": _published_trainings(project_id,
                                          str((_user(request).get("class_name") or ""))),
        "lessons": _published_lessons(project_id,
                                      str((_user(request).get("class_name") or ""))),
        "homework": _published_homework(project_id,
                                        str((_user(request).get("class_name") or ""))),
        "tutor_threads": [],
    })


@app.get("/api/student/wrong")
def student_wrong(request: Request, project_id: Optional[int] = Query(None),
                  student: str = Query("")) -> dict:
    user = _user(request)
    if user.get("role") == "student":
        keys = _student_keys(user)
        pid = _student_project(user, project_id)
        return ok(_wrong_payload(pid, keys, student_mode=True) if pid else
                  {"items": [], "total": 0, "corrected": 0})
    else:
        keys = {student.strip()} if student.strip() else set()
    return ok(_wrong_payload(project_id, keys))


@app.post("/api/student/task/{tid}/submit")
def student_submit_task(tid: int, request: Request, note: str = Form(""),
                        file: Optional[UploadFile] = File(None), request_key: str = Form("")) -> dict:
    """学生提交作业：附件落库 → 进入教师评审队列（生成 review 任务）。"""
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "仅学生账号可提交")
    task = db.get_task(tid)
    if not task or task.get("kind") not in ("lesson", "training", "homework"):
        raise HTTPException(404, "任务不存在")
    pid = task.get("project_id")
    allowed = {int(c["id"]) for c in _student_courses(user) if c and c.get("id") is not None}
    if pid not in allowed:
        raise HTTPException(403, "该任务不在你的班级范围")
    cls = _student_class(user, pid)
    published = (str(((task.get("meta") or {}).get("pkg") or {}).get("status") or "") == "published"
                 if task.get("kind") == "training"
                 else bool((task.get("meta") or {}).get("published")))
    if not published or not _audience_match(task, cls):
        raise HTTPException(403, "该任务未发布给你所在的班级")
    if request_key and (not 16 <= len(request_key) <= 100 or
                        not all(c.isascii() and (c.isalnum() or c == '-') for c in request_key)):
        raise HTTPException(400, "提交请求标识无效")
    def receipt(previous):
        if not previous.get("review_task_id"):
            raise HTTPException(409, "同一提交仍在处理中，请稍后重试；如持续未完成，请联系教师确认后重新提交")
        return ok({"submission_id": previous["id"], "version": previous["version"],
                   "review_task_id": previous["review_task_id"], "file_id": previous["file_id"],
                   "file_name": previous["file_name"], "status": previous["status"],
                   "score": previous.get("score"), "replayed": True,
                   "message": "已确认原提交，无需重复提交"})
    previous = db.get_submission_request(int(user["id"]), tid, request_key)
    if previous:
        return receipt(previous)
    if not file or not file.filename:
        return err("请选择要提交的作业文件")
    data = file.file.read(20 * 1024 * 1024 + 1)
    if not data:
        return err("文件为空")
    if len(data) > 20 * 1024 * 1024:
        return err("文件超过 20MB")
    name = file.filename
    ext = Path(name).suffix.lstrip(".").upper()
    try:
        text, meta = edu.extract_text(name, data)
    except Exception as e:
        text, meta = "", {"note": f"解析失败：{e}", "ext": ext}
    fid = db.save_file(
        name=name, ext=meta.get("ext") or ext, kind="doc", content=data, size=len(data),
        rows=meta.get("rows", 0), cols=meta.get("cols", 0), chars=meta.get("chars", 0),
        parsed_text=text or None, project_id=pid, visibility="teacher", category="学生作业",
        ai_context=0, parse_status="parsed" if text.strip() else "failed",
    )
    student_name = str(user.get("display_name") or user.get("student_no") or "学生")
    student_no = str(user.get("student_no") or "")
    sub = db.upsert_submission(project_id=int(pid), task_id=int(tid), student_id=int(user["id"]),
                               student_no=student_no, student_name=student_name,
                               file_id=int(fid), file_name=name, note=note.strip(), request_key=request_key)
    if sub.get("replayed"):
        db.delete_file(int(fid))
        return receipt(sub)
    review = {}
    if text.strip():
        try:
            review = edu.evaluate_submission(pid, text, name, student=student_name)
        except Exception:
            review = {}
    if not review:
        review = {"dimensions": [], "total": 0, "summary": "AI 未能解析该文件，教师将人工评审。",
                  "comment": ""}
    meta_r = {
        "student": student_name, "student_no": student_no, "class_name": cls,
        "file": name, "files": [name], "file_id": int(fid), "ai": review,
        "submission_id": int(sub["id"]), "submission_task_id": int(tid),
        "submission_version": int(sub["version"]),
        "status": "submitted", "final_total": None,
    }
    rid = db.save_task(prompt=f"{student_name}：{name}", kind="review",
                       project_id=int(pid), meta=meta_r)
    db.set_submission_review(int(sub["id"]), int(sub["version"]), int(rid))
    item = {"project_id": int(pid), "review": review, "student": student_name,
            "file_name": name, "ts": _now(), "status": "submitted",
            "file_id": int(fid), "submission_id": int(sub["id"]),
            "submission_task_id": int(tid), "student_no": student_no}
    item["submission_version"] = int(sub["version"])
    _store_put("reviews", int(rid), item)
    return ok({"submission_id": sub["id"], "review_task_id": rid, "status": "submitted",
               "version": sub["version"], "file_id": fid, "file_name": name, "score": None,
               "message": "已提交，等待教师评审"})


def _submission_versions_for_user(sid: int, user: dict[str, Any]) -> list[dict[str, Any]]:
    sub = db.get_submission(int(sid))
    if not sub:
        raise HTTPException(404, "提交记录不存在")
    if user.get("role") == "student" and str(sub.get("student_no")) != str(user.get("student_no")):
        raise HTTPException(404, "提交记录不存在")
    if user.get("role") == "student":
        _student_project(user, int(sub["project_id"]))
    if user.get("role") not in ("student", "teacher"):
        raise HTTPException(403, "无权访问")
    return db.list_submission_versions(int(sid))


def _submission_version_file(sid: int, version: int, user: dict[str, Any]) -> Response:
    _submission_versions_for_user(sid, user)
    record = db.get_submission_version(int(sid), int(version))
    if not record:
        raise HTTPException(404, "提交版本不存在")
    f = db.get_file(int(record.get("file_id") or 0), with_content=True)
    if not f or f.get("content") is None:
        raise HTTPException(404, "附件不存在")
    return _file_resp(f["content"], f.get("name") or record.get("file_name") or "submission",
                      "application/octet-stream")


@app.get("/api/student/submissions/{sid}/versions")
def student_submission_versions(sid: int, request: Request) -> dict:
    return ok(_submission_versions_for_user(sid, _user(request)))


@app.get("/api/student/submissions/{sid}/versions/{version}/file")
def student_submission_version_file(sid: int, version: int, request: Request) -> Response:
    return _submission_version_file(sid, version, _user(request))


@app.get("/api/submissions/{sid}/versions")
def teacher_submission_versions(sid: int, request: Request) -> dict:
    user = _user(request)
    if user.get("role") != "teacher":
        raise HTTPException(403, "仅教师账号可访问")
    if not db.get_submission(int(sid)):
        raise HTTPException(404, "提交记录不存在")
    return ok(db.list_submission_versions(int(sid)))


@app.get("/api/submissions/{sid}/versions/{version}/file")
def teacher_submission_version_file(sid: int, version: int, request: Request) -> Response:
    user = _user(request)
    if user.get("role") != "teacher":
        raise HTTPException(403, "仅教师账号可访问")
    return _submission_version_file(sid, version, user)


@app.get("/api/student/submissions/{sid}/file")
def student_submission_file(sid: int, request: Request) -> Response:
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "仅学生账号可访问")
    sub = db.get_submission(int(sid))
    if not sub or str(sub.get("student_no")) != str(user.get("student_no")):
        raise HTTPException(404, "提交记录不存在")
    _student_project(user, int(sub["project_id"]))
    f = db.get_file(int(sub.get("file_id") or 0), with_content=True)
    if not f or f.get("content") is None:
        raise HTTPException(404, "附件不存在")
    return _file_resp(f["content"], f.get("name") or sub.get("file_name") or "submission",
                      "application/octet-stream")


class StudentAskIn(BaseModel):
    project_id: Optional[int] = None
    question: str = ""
    knowledge_point: str = ""


@app.post("/api/student/ask")
def student_ask(body: StudentAskIn, request: Request) -> dict:
    """学生提问：走 AI 答疑，并把提问记到本人名下（按学号隔离）。"""
    user = _user(request)
    if user.get("role") != "student":
        raise HTTPException(403, "仅学生账号可访问")
    question = (body.question or "").strip()
    if not question:
        return err("请填写问题")
    pid = _student_project(user, body.project_id)
    if pid is None:
        return err("当前班级暂无可用课程，无法提问")
    display = str(user.get("display_name") or user.get("student_no") or "学生")
    res = tutor_reply(TutorIn(project_id=pid, question=question, student_mode=True, student=display))
    if not isinstance(res, dict) or not res.get("ok"):
        return res
    tid = (res.get("data") or {}).get("task_id")
    if tid:
        task = db.get_task(int(tid)) or {}
        meta = task.get("meta") or {}
        meta["student_no"] = str(user.get("student_no") or "")
        if body.knowledge_point:
            meta["knowledge_point"] = body.knowledge_point
        db.update_task(int(tid), meta=meta)
    return res


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
    audience: Optional[list[str]] = None   # 不传=不改；空列表=全部班级


@app.post("/api/training/{tid}/status")
def set_training_status(tid: int, body: TrainingStatusIn) -> dict:
    if body.status not in ("draft", "published"):
        raise HTTPException(400, "status 仅支持 draft / published")
    item = _store_get("trainings", tid)
    if not item:
        raise HTTPException(404, "实训包不存在")
    item["pkg"]["status"] = body.status
    task = db.get_task(tid)
    task_meta = (task or {}).get("meta") or {}
    if body.audience is not None:
        classes = [str(c).strip() for c in body.audience if str(c).strip()]
        task_meta["audience"] = {"classes": classes}
        item["pkg"]["audience"] = classes
    _store_put("trainings", tid, item)
    if task:
        task_meta["pkg"] = item["pkg"]
        db.update_task(tid, meta=task_meta)
    return ok({"task_id": tid, "status": body.status,
               "audience": (task_meta.get("audience") or {}).get("classes") or []})


@app.post("/api/lesson/{tid}/status")
def set_lesson_status(tid: int, body: TrainingStatusIn) -> dict:
    """备课包发布给学生 / 撤回为草稿（学生端按 meta.published + 发放班级过滤）。"""
    if body.status not in ("draft", "published"):
        raise HTTPException(400, "status 仅支持 draft / published")
    task = db.get_task(tid)
    if not task:
        raise HTTPException(404, "备课包不存在")
    meta = task.get("meta") or {}
    meta["published"] = body.status == "published"
    if body.audience is not None:
        meta["audience"] = {"classes": [str(c).strip() for c in body.audience if str(c).strip()]}
    db.update_task(tid, meta=meta)
    return ok({"task_id": tid, "published": meta["published"], "status": body.status,
               "audience": (meta.get("audience") or {}).get("classes") or []})


# ---------------------------------------------------------------------------
# 数据维护：备份 / 清理临时文件 / 清空全部数据
# ---------------------------------------------------------------------------
@app.get("/api/maintenance/backup")
def export_backup() -> Response:
    try:
        data = backup.create_backup(project_root=PROJECT_DIR, upload_root=UPLOAD_DIR,
                                     export_root=EXPORT_DIR, extra_roots=BACKUP_EXTRA_DIRS)
    except (ValueError, OSError) as e:
        raise HTTPException(409, f"备份未完成：{e}") from e
    response = _file_resp(data, f"workbench_backup_{time.strftime('%Y%m%d_%H%M%S')}.zip", "application/zip")
    response.headers["Cache-Control"] = "no-store"
    return response


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


# ---------- AI 课堂预演 ----------
@app.post("/api/rehearsals/demo", summary="创建演示预演（不调用模型）")
def api_create_demo_rehearsal(body: dict):
    cid = int(body.get("courseId") or 0)
    if not cid or not db.get_project(cid):
        raise HTTPException(400, "课程不存在")
    rid = rehearsal_engine.create_demo_rehearsal(cid, body.get("personas"))
    return {"ok": True, "id": rid}


@app.post("/api/rehearsals", summary="创建课堂预演")
def api_create_rehearsal(body: dict):
    cid = int(body.get("courseId") or 0)
    if not cid or not db.get_project(cid):
        raise HTTPException(400, "课程不存在")
    personas = body.get("personas") or ["novice", "challenger", "operator"]
    use_review_model = body.get("useReviewModel", True)
    if not isinstance(use_review_model, bool):
        raise HTTPException(400, "双模型审核设置必须为布尔值")
    lp_id = body.get("lessonPackageId")
    lesson = db.get_task(int(lp_id)) if lp_id else None
    if lp_id and (not lesson or lesson.get("kind") != "lesson" or lesson.get("project_id") != cid):
        raise HTTPException(400, "备课包不属于当前课程")
    if not lp_id:
        lessons = db.list_tasks(project_id=cid, kind="lesson", limit=1)
        lp_id = lessons[0]["id"] if lessons else None
    # Persist the selected lesson so reruns cannot silently switch source packages.
    rid = db.create_rehearsal(
        course_id=cid, lesson_package_id=int(lp_id) if lp_id else None,
        personas=personas, generation_model="deepseek", review_model="zhipu" if use_review_model else "",
    )
    # 同步执行（简单部署下不用 asyncio）
    try:
        rehearsal_engine.run_rehearsal(rehearsal_id=rid, course_id=cid, personas=personas, use_review_model=use_review_model)
    except Exception as exc:
        db.update_rehearsal(rid, status="failed", error=str(exc))
    return {"ok": True, "id": rid}


@app.get("/api/rehearsals", summary="列出某课程全部预演")
def api_list_rehearsals(courseId: int):
    return {"ok": True, "items": db.list_rehearsals(course_id=courseId)}


@app.get("/api/rehearsals/{rid}", summary="读取预演详情")
def api_get_rehearsal(rid: int):
    s = db.get_rehearsal(int(rid))
    if not s:
        raise HTTPException(404, "预演记录不存在")
    return {"ok": True, "item": s}


@app.post("/api/rehearsals/{rid}/run", summary="重新运行预演（失败后重试）")
def api_run_rehearsal(rid: int):
    s = db.get_rehearsal(int(rid))
    if not s:
        raise HTTPException(404, "预演记录不存在")
    db.update_rehearsal(int(rid), status="running", error=None)
    try:
        rehearsal_engine.run_rehearsal(
            rehearsal_id=int(rid), course_id=int(s["course_id"]),
            personas=s.get("personas") or ["novice", "challenger", "operator"],
            use_review_model=bool(s.get("review_model")),
        )
    except Exception as exc:
        db.update_rehearsal(int(rid), status="failed", error=str(exc))
    return {"ok": True}


@app.post("/api/rehearsals/{rid}/demo", summary="生成演示预演（不调 LLM）")
def api_demo_rehearsal(rid: int):
    s = db.get_rehearsal(int(rid))
    if not s:
        raise HTTPException(404, "预演记录不存在")
    demo_id = rehearsal_engine.create_demo_rehearsal(int(s["course_id"]), s.get("personas"))
    return {"ok": True, "id": demo_id}


@app.post("/api/rehearsals/{rid}/patches/{pid}/apply", summary="应用某个修补（生成备课包新草稿）")
def api_apply_patch(rid: int, pid: str, body: dict = {}):
    s = db.get_rehearsal(int(rid))
    if not s:
        raise HTTPException(404, "预演记录不存在")
    if s.get("is_demo") or not s.get("lesson_package_id"):
        raise HTTPException(400, "演示预演不能修改真实备课包")
    _check_rehearsal_draft(s)
    session = db.update_rehearsal_patch(int(rid), pid, "applied")
    if not session:
        raise HTTPException(404, "修补不存在")
    draft_id = _save_rehearsal_draft(session)
    return {"ok": True, "session": db.get_rehearsal(rid), "draft_task_id": draft_id}


def _check_rehearsal_draft(session: dict) -> dict:
    source = db.get_task(int(session.get("lesson_package_id") or 0))
    if not source or source.get("project_id") != session["course_id"] or source.get("kind") != "lesson":
        raise HTTPException(400, "原备课包不存在或不属于当前课程")
    if not isinstance((source.get("meta") or {}).get("pkg"), dict):
        raise HTTPException(400, "原备课包格式不支持修补")
    plan = source["meta"]["pkg"].get("lesson_plan", {})
    if not isinstance(plan, dict):
        raise HTTPException(400, "原备课包教案格式不支持修补")
    draft_id = (session.get("summary") or {}).get("draft_task_id")
    draft = db.get_task(int(draft_id)) if draft_id else None
    if draft and (draft.get("meta") or {}).get("published"):
        raise HTTPException(409, "修补草稿已经发布，请先取消发布再修改")
    return source


def _save_rehearsal_draft(session: dict) -> int:
    source = _check_rehearsal_draft(session)
    pkg = copy.deepcopy(source["meta"]["pkg"])
    applied = [p for p in session.get("patches") or [] if p.get("status") == "applied"]
    # Preserve structured content and record targeted changes as reviewable supplements.
    plan = pkg.setdefault("lesson_plan", {})
    preparation = plan.get("preparation") or []
    if not isinstance(preparation, list):
        preparation = [str(preparation)]
    plan["preparation"] = preparation + [
        f"[预演修补/{p.get('targetArtifact', '')}/{p.get('targetSection', '')}] {p.get('after', '')}"
        for p in applied]
    pkg["rehearsal_patches"] = copy.deepcopy(applied)
    meta = {"pkg": pkg, "topic": source.get("prompt"), "version": "v2",
            "published": False, "review_status": "待教师确认",
            "source_task_id": source["id"], "rehearsal_id": session["id"]}
    summary = dict(session.get("summary") or {})
    draft_id = summary.get("draft_task_id")
    if draft_id and db.get_task(int(draft_id)):
        db.update_task(int(draft_id), meta=meta)
        STORE["lessons"].pop(int(draft_id), None)
    else:
        draft_id = db.save_task(prompt=f"{source.get('prompt') or '备课包'}（预演修补草稿）",
                                kind="lesson", project_id=session["course_id"], meta=meta)
    summary["draft_task_id"] = int(draft_id)
    db.update_rehearsal(session["id"], summary=summary)
    return int(draft_id)


@app.post("/api/rehearsals/{rid}/patches/{pid}/reject", summary="拒绝修补（不应用）")
def api_reject_patch(rid: int, pid: str):
    existing = db.get_rehearsal(rid) or {}
    patch = next((p for p in existing.get("patches") or [] if p.get("patchId") == pid), {})
    if patch.get("status") == "applied":
        raise HTTPException(409, "请先撤销已应用的修补")
    s = db.update_rehearsal_patch(int(rid), pid, "rejected")
    return {"ok": bool(s), "session": s}


@app.post("/api/rehearsals/{rid}/patches/{pid}/undo", summary="撤销已应用的修补（恢复 pending）")
def api_undo_patch(rid: int, pid: str):
    existing = db.get_rehearsal(rid)
    if not existing:
        raise HTTPException(404, "预演记录不存在")
    if (existing.get("summary") or {}).get("draft_task_id"):
        _check_rehearsal_draft(existing)
    s = db.update_rehearsal_patch(int(rid), pid, "pending")
    if s and (s.get("summary") or {}).get("draft_task_id"):
        _save_rehearsal_draft(s)
        s = db.get_rehearsal(rid)
    return {"ok": bool(s), "session": s}


@app.delete("/api/rehearsals/{rid}", summary="删除预演记录")
def api_delete_rehearsal(rid: int):
    db.delete_rehearsal(int(rid))
    return {"ok": True}


# 静态站：同源托管 static-web/，单端口即可访问整站（本地仍可用 8765 预览）
_STATIC_DIR = ROOT / "static-web"
if _STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print(f"致壹 智能教育工作台 API → http://127.0.0.1:{API_PORT}")
    uvicorn.run(app, host=os.getenv("EDU_API_HOST", "127.0.0.1"), port=API_PORT, log_level="warning",
                timeout_keep_alive=30)
