"""SQLite 持久化层：项目 + 上传文件（含原始字节） + 往期任务 + 生成产物。

数据库文件：.data/workbench.db（随 app.config.ROOT 定位）。
- projects 是逻辑分组容器；files / tasks 通过 project_id 归属到某个项目；
- files.content 以 BLOB 保存文件原始字节，磁盘 .data/uploads 只是工作副本；
- 启动时若数据库为空，自动创建「默认项目」并把历史无 project_id 的记录挂上去。

所有函数自行管理连接，调用方无需显式初始化。
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

from app.config import ROOT

DB_PATH = (ROOT / ".data" / "workbench.db").resolve()

# "rows" 是 SQLite 关键字，统一加双引号
_PROJECTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    folder TEXT,
    audience TEXT NOT NULL DEFAULT '',
    hours TEXT NOT NULL DEFAULT '',
    objectives TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    review_model TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT 'v1',
    class_name TEXT NOT NULL DEFAULT '',
    key_points TEXT NOT NULL DEFAULT '',
    difficulties TEXT NOT NULL DEFAULT '',
    progress TEXT NOT NULL DEFAULT '',
    textbook_version TEXT NOT NULL DEFAULT '',
    class_size INTEGER NOT NULL DEFAULT 0,
    current_session INTEGER NOT NULL DEFAULT 0,
    total_sessions INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at DESC);
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    name TEXT NOT NULL,
    ext TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'table',
    size INTEGER NOT NULL DEFAULT 0,
    content BLOB,
    "rows" INTEGER NOT NULL DEFAULT 0,
    cols INTEGER NOT NULL DEFAULT 0,
    chars INTEGER NOT NULL DEFAULT 0,
    parsed_text TEXT,
    path TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    error TEXT,
    visibility TEXT NOT NULL DEFAULT 'teacher',
    category TEXT NOT NULL DEFAULT '',
    ai_context INTEGER NOT NULL DEFAULT 1,
    parse_status TEXT NOT NULL DEFAULT 'parsed',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'agent',
    prompt TEXT NOT NULL,
    answer TEXT,
    tools_used TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ok',
    duration_s REAL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
"""

_FILE_COLS = ('id,project_id,name,ext,kind,size,"rows",cols,chars,path,status,error,'
              'visibility,category,ai_context,parse_status,created_at')
_TASK_COLS = 'id,project_id,kind,prompt,answer,tools_used,status,duration_s,meta,created_at'


def _migrate(conn: sqlite3.Connection) -> None:
    """为旧库补齐 project_id 列，并把无归属记录挂到默认项目。"""
    cur = conn.execute("PRAGMA table_info(files)")
    file_cols = {r[1] for r in cur.fetchall()}
    cur = conn.execute("PRAGMA table_info(tasks)")
    task_cols = {r[1] for r in cur.fetchall()}

    if "project_id" not in file_cols:
        conn.execute("ALTER TABLE files ADD COLUMN project_id INTEGER")
    if "project_id" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN project_id INTEGER")
    if "visibility" not in file_cols:
        conn.execute("ALTER TABLE files ADD COLUMN visibility TEXT NOT NULL DEFAULT 'teacher'")
    if "category" not in file_cols:
        conn.execute("ALTER TABLE files ADD COLUMN category TEXT NOT NULL DEFAULT ''")
    if "ai_context" not in file_cols:
        conn.execute("ALTER TABLE files ADD COLUMN ai_context INTEGER NOT NULL DEFAULT 1")
    if "parse_status" not in file_cols:
        conn.execute("ALTER TABLE files ADD COLUMN parse_status TEXT NOT NULL DEFAULT 'parsed'")
    if "meta" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN meta TEXT")
    conn.commit()

    # 只做列迁移：不再自动创建「默认项目」。
    # 若历史上存在「默认项目」，把无归属记录挂上去；否则保留 NULL（未归属）。
    conn.executescript(_PROJECTS_SCHEMA)
    conn.commit()
    cur = conn.execute("PRAGMA table_info(projects)")
    proj_cols = {r[1] for r in cur.fetchall()}
    if "folder" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN folder TEXT")
    for col, ddl in (
        ("audience", "TEXT NOT NULL DEFAULT ''"),
        ("hours", "TEXT NOT NULL DEFAULT ''"),
        ("objectives", "TEXT NOT NULL DEFAULT ''"),
        ("model", "TEXT NOT NULL DEFAULT ''"),
        ("version", "TEXT NOT NULL DEFAULT 'v1'"),
        ("review_model", "TEXT NOT NULL DEFAULT ''"),
        ("class_name", "TEXT NOT NULL DEFAULT ''"),
        ("key_points", "TEXT NOT NULL DEFAULT ''"),
        ("difficulties", "TEXT NOT NULL DEFAULT ''"),
        ("progress", "TEXT NOT NULL DEFAULT ''"),
        ("textbook_version", "TEXT NOT NULL DEFAULT ''"),
        ("class_size", "INTEGER NOT NULL DEFAULT 0"),
        ("current_session", "INTEGER NOT NULL DEFAULT 0"),
        ("total_sessions", "INTEGER NOT NULL DEFAULT 0"),
        ("note", "TEXT NOT NULL DEFAULT ''"),
        ("is_demo", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in proj_cols:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {ddl}")
    conn.commit()
    row = conn.execute("SELECT id FROM projects WHERE name='默认项目'").fetchone()
    if row is not None:
        default_pid = row["id"]
        conn.execute("UPDATE files SET project_id=? WHERE project_id IS NULL", (default_pid,))
        conn.execute("UPDATE tasks SET project_id=? WHERE project_id IS NULL", (default_pid,))
        conn.commit()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # 1) 先建 projects 表
    conn.executescript(_PROJECTS_SCHEMA)
    # 2) 建 files/tasks 表（如果不存在，全新表自带 project_id 列）
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            name TEXT NOT NULL,
            ext TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'table',
            size INTEGER NOT NULL DEFAULT 0,
            content BLOB,
            "rows" INTEGER NOT NULL DEFAULT 0,
            cols INTEGER NOT NULL DEFAULT 0,
            chars INTEGER NOT NULL DEFAULT 0,
            parsed_text TEXT,
            path TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            error TEXT,
            visibility TEXT NOT NULL DEFAULT 'teacher',
            category TEXT NOT NULL DEFAULT '',
            ai_context INTEGER NOT NULL DEFAULT 1,
            parse_status TEXT NOT NULL DEFAULT 'parsed',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            kind TEXT NOT NULL DEFAULT 'agent',
            prompt TEXT NOT NULL,
            answer TEXT,
            tools_used TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'ok',
            duration_s REAL,
            meta TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            kind TEXT NOT NULL,
            ref TEXT NOT NULL,
            project_id INTEGER,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (kind, ref)
        );
        """
    )
    # 3) 对旧库：补 ALTER TABLE project_id 列，补默认项目并迁移归属
    _migrate(conn)
    # 4) 最后再建索引（此时列一定存在）
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(kind, project_id);
        """
    )
    return conn


def _d(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def ensure_default_project() -> Optional[int]:
    """返回「默认项目」的 id；不存在时返回 None（不再自动创建）。"""
    with _conn() as c:
        row = c.execute("SELECT id FROM projects WHERE name='默认项目'").fetchone()
    return int(row["id"]) if row else None


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------
def create_project(name: str, description: str = "", folder: str | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("项目名不能为空")
    with _conn() as c:
        existing = c.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
        if existing:
            # 已存在则直接返回（顺便补上文件夹，便于旧项目补建本地目录）
            if folder:
                c.execute(
                    "UPDATE projects SET folder=? WHERE id=? AND (folder IS NULL OR folder='')",
                    (folder, int(existing["id"])),
                )
            return int(existing["id"])
        cur = c.execute(
            "INSERT INTO projects(name,description,folder,created_at) VALUES (?,?,?,?)",
            (name, description, folder, time.time()),
        )
        return int(cur.lastrowid)


def set_project_folder(project_id: int, folder: str) -> None:
    with _conn() as c:
        c.execute("UPDATE projects SET folder=? WHERE id=?", (folder, int(project_id)))


def update_project(project_id: int, *, name: str | None = None, description: str | None = None,
                   folder: str | None = None) -> None:
    """更新项目基础字段（只更新传入的字段）。"""
    sets, args = [], []
    for col, val in (("name", name), ("description", description), ("folder", folder)):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(val)
    if not sets:
        return
    args.append(int(project_id))
    with _conn() as c:
        c.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", args)


def update_course(project_id: int, *, audience: str | None = None, hours: str | None = None,
                  objectives: str | None = None, model: str | None = None,
                  version: str | None = None, review_model: str | None = None,
                  class_name: str | None = None, key_points: str | None = None,
                  difficulties: str | None = None, progress: str | None = None,
                  textbook_version: str | None = None,
                  class_size: int | None = None, current_session: int | None = None,
                  total_sessions: int | None = None, note: str | None = None) -> None:
    """更新课程项目信息（只更新传入的字段）。"""
    sets, args = [], []
    for col, val in (
        ("audience", audience), ("hours", hours), ("objectives", objectives),
        ("model", model), ("version", version), ("review_model", review_model),
        ("class_name", class_name), ("key_points", key_points),
        ("difficulties", difficulties), ("progress", progress),
        ("textbook_version", textbook_version),
        ("class_size", class_size), ("current_session", current_session),
        ("total_sessions", total_sessions), ("note", note),
    ):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(val)
    if not sets:
        return
    args.append(int(project_id))
    with _conn() as c:
        c.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", args)


def list_projects(limit: int = 100) -> list[dict[str, Any]]:
    """列出全部项目，并附带每个项目的文件数/任务数（轻量 join）。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT p.id, p.name, p.description, p.folder, p.class_name, p.progress,"
            " p.audience, p.hours, p.objectives, p.key_points, p.difficulties,"
            " p.textbook_version, p.class_size, p.current_session, p.total_sessions,"
            " p.note, p.is_demo, p.created_at,"
            " (SELECT COUNT(*) FROM files WHERE project_id=p.id) AS file_count,"
            " (SELECT COUNT(*) FROM tasks WHERE project_id=p.id) AS task_count"
            " FROM projects p ORDER BY p.created_at DESC, p.id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [_d(r) for r in rows]


def get_project(project_id: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (int(project_id),)).fetchone()
    return _d(r) if r else None


def delete_project(project_id: int) -> None:
    """删除项目：其下文件/任务改为未归属（project_id=NULL），不丢数据。"""
    with _conn() as c:
        c.execute("UPDATE files SET project_id=NULL WHERE project_id=?", (int(project_id),))
        c.execute("UPDATE tasks SET project_id=NULL WHERE project_id=?", (int(project_id),))
        c.execute("DELETE FROM projects WHERE id=?", (int(project_id),))


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------
def save_file(*, name: str, ext: str, kind: str, content: bytes | None,
              size: int = 0, rows: int = 0, cols: int = 0, chars: int = 0,
              parsed_text: Optional[str] = None, path: Optional[str] = None,
              status: str = "ok", error: Optional[str] = None,
              project_id: Optional[int] = None,
              visibility: str = "teacher", category: str = "",
              ai_context: int = 1, parse_status: str = "parsed") -> int:
    """保存一个上传文件（含原始字节）。返回新记录 id。"""
    blob = bytes(content) if content is not None else None
    with _conn() as c:
        pid = project_id if project_id is not None else ensure_default_project()
        cur = c.execute(
            "INSERT INTO files(project_id,name,ext,kind,size,content,\"rows\",cols,chars,"
            "parsed_text,path,status,error,visibility,category,ai_context,parse_status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, name, ext, kind, int(size), blob, int(rows), int(cols), int(chars),
             parsed_text, path, status, error, visibility, category,
             int(bool(ai_context)), parse_status, time.time()),
        )
        return int(cur.lastrowid)


def list_files(project_id: Optional[int] = None, limit: int = 200,
               visibility: Optional[str] = None,
               category: Optional[str] = None) -> list[dict[str, Any]]:
    """列出文件元数据（不含 BLOB / 正文，轻量）。按时间倒序。

    visibility 过滤规则：传入 "student" 时只返回学生可见（student / both）。
    """
    clauses, args = [], []
    if project_id is not None:
        clauses.append("project_id=?")
        args.append(int(project_id))
    if visibility == "student":
        clauses.append("visibility IN ('student','both')")
    elif visibility:
        clauses.append("visibility=?")
        args.append(visibility)
    if category:
        clauses.append("category=?")
        args.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_FILE_COLS},"
            " (content IS NOT NULL) AS has_content,"
            " (parsed_text IS NOT NULL) AS has_text"
            f" FROM files {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(args) + (int(limit),),
        ).fetchall()
    return [_d(r) for r in rows]


def get_file(file_id: int, with_content: bool = False) -> Optional[dict[str, Any]]:
    cols = _FILE_COLS + (",content,parsed_text" if with_content else "")
    with _conn() as c:
        r = c.execute(f"SELECT {cols} FROM files WHERE id=?", (int(file_id),)).fetchone()
    return _d(r) if r else None


def get_file_text(file_id: int) -> Optional[str]:
    with _conn() as c:
        r = c.execute("SELECT parsed_text FROM files WHERE id=?", (int(file_id),)).fetchone()
    return r["parsed_text"] if r else None


def delete_file(file_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM files WHERE id=?", (int(file_id),))


def update_file(file_id: int, *, visibility: str | None = None,
                ai_context: int | None = None, category: str | None = None,
                parse_status: str | None = None) -> None:
    sets, args = [], []
    for col, val in (("visibility", visibility), ("ai_context", ai_context),
                     ("category", category), ("parse_status", parse_status)):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(val)
    if not sets:
        return
    args.append(int(file_id))
    with _conn() as c:
        c.execute(f"UPDATE files SET {','.join(sets)} WHERE id=?", args)


def set_project_demo(project_id: int, is_demo: int = 1) -> None:
    with _conn() as c:
        c.execute("UPDATE projects SET is_demo=? WHERE id=?", (int(is_demo), int(project_id)))


def delete_project_data(project_id: int, *, delete_project: bool = False) -> None:
    """清空某课程的全部资料与任务；delete_project 仅对演示课程生效。"""
    pid = int(project_id)
    with _conn() as c:
        c.execute("DELETE FROM files WHERE project_id=?", (pid,))
        c.execute("DELETE FROM tasks WHERE project_id=?", (pid,))
        if delete_project:
            c.execute("DELETE FROM projects WHERE id=? AND is_demo=1", (pid,))


def course_overview(project_id: int) -> dict[str, Any]:
    """课程驾驶舱统计：资料、可见资料、待评审、最近备课包等。"""
    pid = int(project_id)
    with _conn() as c:
        files_total = c.execute("SELECT COUNT(*) n FROM files WHERE project_id=?", (pid,)).fetchone()["n"]
        files_student = c.execute(
            "SELECT COUNT(*) n FROM files WHERE project_id=? AND visibility IN ('student','both')",
            (pid,)).fetchone()["n"]
        tasks = {}
        for kind, n in c.execute(
                "SELECT kind, COUNT(*) n FROM tasks WHERE project_id=? GROUP BY kind", (pid,)):
            tasks[kind] = n
    last_lesson = list_tasks(project_id=pid, kind="lesson", limit=1)
    pending_review = len([t for t in list_tasks(project_id=pid, kind="review", limit=500)
                          if (t.get("meta") or {}).get("status") not in ("published", "returned")])
    return {
        "files_total": files_total,
        "files_student": files_student,
        "lesson_count": tasks.get("lesson", 0),
        "training_count": tasks.get("training", 0),
        "qa_count": tasks.get("qa", 0),
        "review_count": tasks.get("review", 0),
        "nextlesson_count": tasks.get("nextlesson", 0),
        "pending_review": pending_review,
        "last_lesson_title": (last_lesson[0]["prompt"] if last_lesson else ""),
    }


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------
def save_task(*, prompt: str, answer: Optional[str] = None,
              tools_used: Optional[list[str]] = None, kind: str = "agent",
              status: str = "ok", duration_s: Optional[float] = None,
              project_id: Optional[int] = None,
              meta: Optional[dict[str, Any]] = None) -> int:
    """保存一条任务记录。kind: agent | load | lesson | training | qa | review | nextlesson。"""
    with _conn() as c:
        pid = project_id if project_id is not None else ensure_default_project()
        cur = c.execute(
            "INSERT INTO tasks(project_id,kind,prompt,answer,tools_used,status,duration_s,meta,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, kind, prompt, answer,
             json.dumps(tools_used or [], ensure_ascii=False),
             status, duration_s,
             json.dumps(meta or {}, ensure_ascii=False) if meta is not None else None,
             time.time()),
        )
        return int(cur.lastrowid)


def update_task(task_id: int, *, answer: Optional[str] = None,
                meta: Optional[dict[str, Any]] = None) -> None:
    sets, args = [], []
    if answer is not None:
        sets.append("answer=?")
        args.append(answer)
    if meta is not None:
        sets.append("meta=?")
        args.append(json.dumps(meta, ensure_ascii=False))
    if not sets:
        return
    args.append(int(task_id))
    with _conn() as c:
        c.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", args)


def get_task(task_id: int) -> Optional[dict[str, Any]]:
    """读取单条任务（meta 已解析为 dict），不存在时返回 None。"""
    with _conn() as c:
        r = c.execute(f"SELECT {_TASK_COLS} FROM tasks WHERE id=?",
                      (int(task_id),)).fetchone()
    if not r:
        return None
    d = _d(r)
    try:
        d["tools_used"] = json.loads(d.get("tools_used") or "[]")
    except Exception:
        d["tools_used"] = []
    try:
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else {}
    except Exception:
        d["meta"] = {}
    return d


def list_tasks(project_id: Optional[int] = None, limit: int = 200,
               kind: Optional[str] = None) -> list[dict[str, Any]]:
    clauses, args = [], []
    if project_id is not None:
        clauses.append("project_id=?")
        args.append(int(project_id))
    if kind:
        clauses.append("kind=?")
        args.append(kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_TASK_COLS} FROM tasks {where}"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(args) + (int(limit),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _d(r)
        try:
            d["tools_used"] = json.loads(d.get("tools_used") or "[]")
        except Exception:
            d["tools_used"] = []
        try:
            d["meta"] = json.loads(d["meta"]) if d.get("meta") else {}
        except Exception:
            d["meta"] = {}
        out.append(d)
    return out


def delete_task(task_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM tasks WHERE id=?", (int(task_id),))


def recent_tasks(limit: int = 5, project_id: Optional[int] = None) -> list[dict[str, Any]]:
    """侧栏快速渲染专用：只取最近若干条（默认 5），字段同 list_tasks。"""
    return list_tasks(project_id=project_id, limit=limit)


# ---------------------------------------------------------------------------
# artifacts：生成产物（备课包 / 实训包 / 评审 / 答疑会话 / 学情分析）持久化
# ---------------------------------------------------------------------------
def save_artifact(kind: str, ref: Any, payload: Any,
                  project_id: Optional[int] = None) -> None:
    """写入/覆盖一条生成产物（key = kind + ref），API 重启后仍可取回。"""
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO artifacts(kind,ref,project_id,payload,created_at)"
            " VALUES (?,?,?,?,?)",
            (kind, str(ref), int(project_id) if project_id is not None else None,
             json.dumps(payload, ensure_ascii=False), time.time()),
        )


def get_artifact(kind: str, ref: Any) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute("SELECT payload FROM artifacts WHERE kind=? AND ref=?",
                      (kind, str(ref))).fetchone()
    if not r:
        return None
    try:
        return json.loads(r["payload"])
    except Exception:
        return None


def list_artifacts(kind: str, project_id: Optional[int] = None) -> list[tuple[str, dict[str, Any]]]:
    clauses, args = ["kind=?"], [kind]
    if project_id is not None:
        clauses.append("project_id=?")
        args.append(int(project_id))
    with _conn() as c:
        rows = c.execute(
            f"SELECT ref,payload FROM artifacts WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at DESC, ref DESC",
            tuple(args),
        ).fetchall()
    out: list[tuple[str, dict[str, Any]]] = []
    for r in rows:
        try:
            out.append((r["ref"], json.loads(r["payload"])))
        except Exception:
            continue
    return out


def delete_artifact(kind: str, ref: Any) -> None:
    with _conn() as c:
        c.execute("DELETE FROM artifacts WHERE kind=? AND ref=?", (kind, str(ref)))


def reset_all() -> None:
    """清空业务数据（项目 / 资料 / 任务 / 产物），保留表结构。"""
    with _conn() as c:
        c.execute("DELETE FROM files")
        c.execute("DELETE FROM tasks")
        c.execute("DELETE FROM artifacts")
        c.execute("DELETE FROM projects")
        try:
            c.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass

