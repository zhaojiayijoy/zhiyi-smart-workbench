"""SQLite 持久化层：项目 + 上传文件（含原始字节） + 往期任务 + 生成产物。

数据库文件：.data/workbench.db（随 app.config.ROOT 定位）。
- projects 是逻辑分组容器；files / tasks 通过 project_id 归属到某个项目；
- files.content 以 BLOB 保存文件原始字节，磁盘 .data/uploads 只是工作副本；
- 启动时若数据库为空，自动创建「默认项目」并把历史无 project_id 的记录挂上去。

所有函数自行管理连接，调用方无需显式初始化。
"""
from __future__ import annotations

import json
import hashlib
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from app.config import ROOT

DB_PATH = (ROOT / ".data" / "workbench.db").resolve()
_SCHEMA_VERSION = 4
_INIT_LOCK = threading.RLock()


class _Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, factory=_Connection)
    conn.row_factory = sqlite3.Row
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
            with _INIT_LOCK:
                if conn.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
                    _initialize(conn)
        return conn
    except Exception:
        conn.close()
        raise


def initialize() -> None:
    with _conn():
        pass


def backup_to(destination: str | Path) -> None:
    with _conn() as source:
        with sqlite3.connect(destination, factory=_Connection) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("数据库备份完整性检查失败")

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
    parent_id INTEGER,
    round INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    archived_at REAL,
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
        ("parent_id", "INTEGER"),
        ("round", "INTEGER NOT NULL DEFAULT 1"),
        ("status", "TEXT NOT NULL DEFAULT 'active'"),
        ("archived_at", "REAL"),
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


def _initialize(conn: sqlite3.Connection) -> None:
    previous_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
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
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            student_no TEXT NOT NULL,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            row_no INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(project_id, student_no)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL DEFAULT 'student',
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            student_no TEXT NOT NULL DEFAULT '',
            college TEXT NOT NULL DEFAULT '',
            major TEXT NOT NULL DEFAULT '',
            class_name TEXT NOT NULL DEFAULT '',
            bound INTEGER NOT NULL DEFAULT 0,
            must_change INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            key TEXT PRIMARY KEY,
            started_at REAL NOT NULL,
            attempts INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            student_no TEXT NOT NULL,
            student_name TEXT NOT NULL DEFAULT '',
            file_id INTEGER NOT NULL DEFAULT 0,
            file_name TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            review_task_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'submitted',
            score REAL,
            feedback TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(task_id, student_no)
        );
        CREATE TABLE IF NOT EXISTS submission_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            student_no TEXT NOT NULL,
            student_name TEXT NOT NULL DEFAULT '',
            file_id INTEGER NOT NULL DEFAULT 0,
            file_name TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            review_task_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'submitted',
            score REAL,
            feedback TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            UNIQUE(submission_id, version)
        );
        """
    )
    # 3) 对旧库：补 ALTER TABLE project_id 列，补默认项目并迁移归属
    _migrate(conn)
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "activation_expires_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN activation_expires_at REAL")
    if previous_version < 4:
        pending = conn.execute(
            "SELECT id, COALESCE(NULLIF(TRIM(student_no), ''), username) AS student_no"
            " FROM users WHERE role='student' AND must_change=1"
        ).fetchall()
        for user in pending:
            student_no = str(user["student_no"] or "").strip()
            if not student_no:
                continue
            password = student_no[-6:] if len(student_no) >= 6 else student_no
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
            conn.execute(
                "UPDATE users SET password_hash=?, activation_expires_at=NULL, updated_at=? WHERE id=?",
                (f"pbkdf2_sha256$120000${salt}${digest.hex()}", time.time(), int(user["id"])),
            )
        conn.execute("DELETE FROM sessions WHERE user_id IN"
                     " (SELECT id FROM users WHERE role='student' AND must_change=1)")
    conn.commit()
    # 4) 幂等回填当前快照为首个历史版本
    version_cols = {r[1] for r in conn.execute("PRAGMA table_info(submission_versions)")}
    if "request_key" not in version_cols:
        conn.execute("ALTER TABLE submission_versions ADD COLUMN request_key TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "INSERT OR IGNORE INTO submission_versions (submission_id, version, project_id, task_id,"
        " student_id, student_no, student_name, file_id, file_name, note, review_task_id,"
        " status, score, feedback, created_at)"
        " SELECT id, 1, project_id, task_id, student_id, student_no, student_name, file_id,"
        " file_name, note, review_task_id, status, score, feedback, created_at FROM submissions"
    )
    # 5) 最后再建索引（此时列一定存在）
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(kind, project_id);
        CREATE INDEX IF NOT EXISTS idx_projects_parent ON projects(parent_id);
        CREATE INDEX IF NOT EXISTS idx_students_project ON students(project_id, student_no);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role, username);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_submissions_task ON submissions(task_id, student_no);
        CREATE INDEX IF NOT EXISTS idx_submissions_project ON submissions(project_id, student_no);
        CREATE INDEX IF NOT EXISTS idx_login_attempts_started ON login_attempts(started_at);
        CREATE INDEX IF NOT EXISTS idx_versions_review ON submission_versions(review_task_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_versions_request
            ON submission_versions(student_id, task_id, request_key) WHERE request_key<>'';
        CREATE INDEX IF NOT EXISTS idx_tasks_student ON tasks(project_id, kind,
            TRIM(CAST(json_extract(CASE WHEN json_valid(meta) THEN meta ELSE '{}' END,
                                   '$.student_no') AS TEXT)), created_at DESC, id DESC);
        """
    )
    _ensure_rehearsal_table(conn)
    conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
    conn.commit()


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
            " p.parent_id, p.round, p.status, p.archived_at,"
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
        c.execute("UPDATE projects SET parent_id=NULL WHERE parent_id=?", (int(project_id),))
        c.execute("DELETE FROM projects WHERE id=?", (int(project_id),))


def archive_project(project_id: int) -> None:
    """把项目标记为已归档（历史轮次）。"""
    with _conn() as c:
        c.execute("UPDATE projects SET status='archived', archived_at=? WHERE id=?",
                  (time.time(), int(project_id)))


def set_project_round(project_id: int, parent_id: Optional[int], round_no: int) -> None:
    """写入轮次关系：parent_id 指向课程根项目，round 为轮次序号。"""
    with _conn() as c:
        c.execute("UPDATE projects SET parent_id=?, round=? WHERE id=?",
                  (int(parent_id) if parent_id is not None else None,
                   int(round_no), int(project_id)))


def list_rounds(root_id: int) -> list[dict[str, Any]]:
    """列出某课程根项目及其全部轮次（子项目），按轮次升序。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT p.id, p.name, p.class_name, p.progress, p.current_session, p.total_sessions,"
            " p.parent_id, p.round, p.status, p.archived_at, p.created_at,"
            " (SELECT COUNT(*) FROM files WHERE project_id=p.id) AS file_count,"
            " (SELECT COUNT(*) FROM tasks WHERE project_id=p.id) AS task_count"
            " FROM projects p WHERE p.id=? OR p.parent_id=?"
            " ORDER BY p.round ASC, p.id ASC",
            (int(root_id), int(root_id)),
        ).fetchall()
    return [_d(r) for r in rows]


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
               kind: Optional[str] = None, *, student_keys: Optional[set[str]] = None,
               released_only: bool = False, offset: int = 0) -> list[dict[str, Any]]:
    clauses, args = [], []
    if project_id is not None:
        clauses.append("project_id=?")
        args.append(int(project_id))
    if kind:
        clauses.append("kind=?")
        args.append(kind)
    # Invalid legacy JSON cannot bypass the identity filter or break the query.
    safe_meta = "CASE WHEN json_valid(meta) THEN meta ELSE '{}' END"
    if student_keys is not None:
        keys = sorted(str(k).strip() for k in student_keys if str(k).strip())
        if not keys:
            return []
        clauses.append(f"TRIM(CAST(json_extract({safe_meta}, '$.student_no') AS TEXT))"
                       f" IN ({','.join('?' for _ in keys)})")
        args.extend(keys)
    if released_only:
        clauses.append(f"json_extract({safe_meta}, '$.status') IN ('published','returned')")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_TASK_COLS} FROM tasks {where}"
            " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            tuple(args) + (max(1, min(int(limit), 10000)), max(0, int(offset))),
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
    """Clear business data and student accounts; retain teachers and ID sequences."""
    with _conn() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("submission_versions", "submissions", "students", "files",
                      "tasks", "artifacts", "rehearsals", "projects"):
            if table in tables:
                c.execute(f'DELETE FROM "{table}"')
        c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE role='student')")
        c.execute("DELETE FROM users WHERE role='student'")


# ---------------------------------------------------------------------------
# rehearsals：AI 课堂预演持久化（SQLite，非破坏性）
# ---------------------------------------------------------------------------
_REHEARSAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS rehearsals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    lesson_package_id INTEGER,
    lesson_package_ref TEXT,
    status TEXT NOT NULL DEFAULT 'configuring',
    personas TEXT NOT NULL DEFAULT '[]',
    timeline TEXT NOT NULL DEFAULT '[]',
    events TEXT NOT NULL DEFAULT '[]',
    risks TEXT NOT NULL DEFAULT '[]',
    patches TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    generation_model TEXT NOT NULL DEFAULT '',
    review_model TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_rehearsals_course ON rehearsals(course_id, created_at DESC);
"""


def _ensure_rehearsal_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_REHEARSAL_SCHEMA)


def _conn_rehearsals() -> sqlite3.Connection:
    return _conn()


def create_rehearsal(*, course_id: int, lesson_package_id: Optional[int] = None,
                     lesson_package_ref: str = "", personas: Optional[list[str]] = None,
                     generation_model: str = "", review_model: str = "",
                     is_demo: bool = False) -> int:
    with _conn_rehearsals() as c:
        cur = c.execute(
            "INSERT INTO rehearsals(course_id,lesson_package_id,lesson_package_ref,"
            "personas,generation_model,review_model,is_demo,created_at,status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (int(course_id),
             int(lesson_package_id) if lesson_package_id is not None else None,
             lesson_package_ref,
             json.dumps(personas or [], ensure_ascii=False),
             generation_model, review_model,
             int(bool(is_demo)), time.time(), "configuring"),
        )
        return int(cur.lastrowid)


def update_rehearsal(rehearsal_id: int, *, status: Optional[str] = None,
                     timeline: Optional[list] = None, events: Optional[list] = None,
                     risks: Optional[list] = None, patches: Optional[list] = None,
                     summary: Optional[dict] = None, error: Optional[str] = None,
                     completed_at: Optional[float] = None,
                     is_demo: Optional[bool] = None) -> None:
    sets, args = [], []
    for col, val in (
        ("status", status), ("summary", summary), ("error", error),
    ):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(json.dumps(val, ensure_ascii=False) if col == "summary" else val)
    for col, val in (("timeline", timeline), ("events", events),
                     ("risks", risks), ("patches", patches)):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(json.dumps(val, ensure_ascii=False))
    if completed_at is not None:
        sets.append("completed_at=?")
        args.append(completed_at)
    if is_demo is not None:
        sets.append("is_demo=?")
        args.append(int(is_demo))
    if not sets:
        return
    args.append(int(rehearsal_id))
    with _conn_rehearsals() as c:
        c.execute(f"UPDATE rehearsals SET {','.join(sets)} WHERE id=?", args)


def get_rehearsal(rehearsal_id: int) -> Optional[dict[str, Any]]:
    with _conn_rehearsals() as c:
        r = c.execute("SELECT * FROM rehearsals WHERE id=?", (int(rehearsal_id),)).fetchone()
    if not r:
        return None
    d = _d(r)
    for col in ("personas", "timeline", "events", "risks", "patches"):
        try:
            d[col] = json.loads(d.get(col) or "[]")
        except Exception:
            d[col] = []
    for col in ("summary",):
        try:
            d[col] = json.loads(d[col]) if d.get(col) else None
        except Exception:
            d[col] = None
    return d


def list_rehearsals(course_id: Optional[int] = None, limit: int = 50) -> list[dict[str, Any]]:
    clauses, args = [], []
    if course_id is not None:
        clauses.append("course_id=?")
        args.append(int(course_id))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn_rehearsals() as c:
        rows = c.execute(
            f"SELECT * FROM rehearsals {where}"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            tuple(args) + (int(limit),),
        ).fetchall()
    out = []
    for r in rows:
        d = _d(r)
        for col in ("personas", "timeline", "events", "risks", "patches"):
            try:
                d[col] = json.loads(d.get(col) or "[]")
            except Exception:
                d[col] = []
        try:
            d["summary"] = json.loads(d["summary"]) if d.get("summary") else None
        except Exception:
            d["summary"] = None
        out.append(d)
    return out


def delete_rehearsal(rehearsal_id: int) -> None:
    with _conn_rehearsals() as c:
        c.execute("DELETE FROM rehearsals WHERE id=?", (int(rehearsal_id),))


def update_rehearsal_patch(rehearsal_id: int, patch_id: str, status: str,
                           applied_at: Optional[float] = None) -> Optional[dict[str, Any]]:
    """更新某预演记录中单个修补的状态，返回更新后的 session。"""
    session = get_rehearsal(rehearsal_id)
    if not session:
        return None
    patches = session.get("patches") or []
    if not any(p.get("patchId") == patch_id for p in patches):
        return None
    for p in patches:
        if p.get("patchId") == patch_id:
            p["status"] = status
            if applied_at is not None:
                p["appliedAt"] = applied_at
            if status == "applied":
                p["appliedAt"] = p.get("appliedAt") or time.time()
            elif status in ("rejected", "pending") and "appliedAt" in p:
                del p["appliedAt"]
            break
    update_rehearsal(rehearsal_id, patches=patches)
    return get_rehearsal(rehearsal_id)



# ---------------------------------------------------------------------------
# students（班级学生名单：学号 / 姓名 / 班级）
# ---------------------------------------------------------------------------
def import_students(project_id: int, rows: list[dict[str, Any]], source_file: str = "") -> dict[str, int]:
    """按 (project_id, student_no) upsert 学生记录；返回 {added, updated}。"""
    now = time.time()
    added = updated = 0
    with _conn() as c:
        for r in rows:
            no = str(r.get("student_no") or "").strip()
            name = str(r.get("name") or "").strip()
            if not no or not name:
                continue
            cls = str(r.get("class_name") or "").strip()
            row_no = int(r.get("row_no") or 0)
            cur = c.execute(
                "SELECT id FROM students WHERE project_id=? AND student_no=?",
                (project_id, no),
            ).fetchone()
            if cur:
                c.execute(
                    "UPDATE students SET name=?, class_name=?, source_file=?, row_no=?, updated_at=? WHERE id=?",
                    (name, cls, source_file, row_no, now, cur["id"]),
                )
                updated += 1
            else:
                c.execute(
                    "INSERT INTO students (project_id, student_no, name, class_name, source_file, row_no, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (project_id, no, name, cls, source_file, row_no, now, now),
                )
                added += 1
        c.commit()
    return {"added": added, "updated": updated}


def list_students(project_id: int, limit: int = 2000) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, project_id, student_no, name, class_name, source_file, row_no, created_at, updated_at"
            " FROM students WHERE project_id=? ORDER BY student_no LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [_d(r) for r in rows]


def count_students(project_id: int) -> int:
    with _conn() as c:
        row = c.execute("SELECT COUNT(*) AS n FROM students WHERE project_id=?", (project_id,)).fetchone()
    return int(row["n"] if row else 0)


def clear_students(project_id: int) -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM students WHERE project_id=?", (project_id,))
        c.commit()
        return int(cur.rowcount or 0)


def list_all_students() -> list[dict[str, Any]]:
    """全部名单记录（跨课程去重前使用），用于学生账号回填。"""
    with _conn() as c:
        rows = c.execute(
            "SELECT student_no, name, class_name FROM students ORDER BY student_no"
        ).fetchall()
    return [_d(r) for r in rows]


def student_enrollments(student_no: str) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT project_id, student_no, class_name FROM students WHERE student_no=?",
                         (student_no,)).fetchall()
    return [_d(r) for r in rows]


# ---------------------------------------------------------------------------
# users / sessions（教师与学生账号、登录会话）
# ---------------------------------------------------------------------------
_USER_COLS = ("id, role, username, password_hash, display_name, student_no,"
              " college, major, class_name, bound, must_change, status, activation_expires_at, created_at, updated_at")


def create_user(*, role: str, username: str, password_hash: str,
                display_name: str = "", student_no: str = "",
                college: str = "", major: str = "", class_name: str = "",
                bound: int = 0, must_change: int = 0,
                activation_expires_at: Optional[float] = None) -> int:
    now = time.time()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO users (role, username, password_hash, display_name, student_no,"
            " college, major, class_name, bound, must_change, status, activation_expires_at, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'active',?,?,?)",
            (role, username, password_hash, display_name, student_no,
             college, major, class_name, int(bound), int(must_change), activation_expires_at, now, now),
        )
        c.commit()
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute(f"SELECT {_USER_COLS} FROM users WHERE username=?", (str(username),)).fetchone()
    return _d(r) if r else None


def get_user(user_id: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute(f"SELECT {_USER_COLS} FROM users WHERE id=?", (int(user_id),)).fetchone()
    return _d(r) if r else None


_USER_FIELDS = {"password_hash", "display_name", "student_no", "college", "major",
                 "class_name", "bound", "must_change", "status", "activation_expires_at"}


def reserve_login_attempt(account_key: str, source_key: str, now: float,
                          window: int = 900) -> int:
    """Atomically reserve an attempt across API workers, before password hashing."""
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("DELETE FROM login_attempts WHERE started_at<=?", (now - window,))
        for key, maximum in ((account_key, 8), (source_key, 200)):
            row = c.execute("SELECT started_at, attempts FROM login_attempts WHERE key=?", (key,)).fetchone()
            if row and row["attempts"] >= maximum:
                return max(1, int(row["started_at"] + window - now) + 1)
        for key in (account_key, source_key):
            c.execute("INSERT INTO login_attempts(key,started_at,attempts) VALUES(?,?,1)"
                      " ON CONFLICT(key) DO UPDATE SET attempts=attempts+1", (key, now))
    return 0


def clear_login_attempts(account_key: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM login_attempts WHERE key=?", (account_key,))


def update_user(user_id: int, **fields: Any) -> None:
    sets, args = [], []
    for k, v in fields.items():
        if k not in _USER_FIELDS:
            continue
        sets.append(f"{k}=?")
        args.append(v)
    if not sets:
        return
    sets.append("updated_at=?")
    args.append(time.time())
    args.append(int(user_id))
    with _conn() as c:
        c.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", args)
        c.commit()


def list_users(role: Optional[str] = None) -> list[dict[str, Any]]:
    sql = f"SELECT {_USER_COLS} FROM users"
    args: tuple = ()
    if role:
        sql += " WHERE role=?"
        args = (role,)
    with _conn() as c:
        rows = c.execute(sql + " ORDER BY id", args).fetchall()
    return [_d(r) for r in rows]


def create_session(token: str, user_id: int, role: str, expires_at: float) -> None:
    with _conn() as c:
        c.execute("INSERT INTO sessions (token, user_id, role, created_at, expires_at) VALUES (?,?,?,?,?)",
                  (token, int(user_id), role, time.time(), float(expires_at)))
        c.commit()


def get_session(token: str) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute("SELECT token, user_id, role, created_at, expires_at FROM sessions WHERE token=?",
                      (str(token),)).fetchone()
    return _d(r) if r else None


def delete_session(token: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (str(token),))
        c.commit()


def delete_user_sessions(user_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE user_id=?", (int(user_id),))
        c.commit()


def purge_expired_sessions(now: Optional[float] = None) -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM sessions WHERE expires_at<?", (now or time.time(),))
        c.commit()
        return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------
# submissions（学生提交作业）
# ---------------------------------------------------------------------------
_SUB_COLS = ("id, project_id, task_id, student_id, student_no, student_name, file_id,"
             " file_name, note, review_task_id, status, score, feedback, created_at, updated_at")
_VER_COLS = ("id, submission_id, version, project_id, task_id, student_id, student_no,"
             " student_name, file_id, file_name, note, review_task_id, status, score, feedback, created_at")


def _insert_submission_version(c: sqlite3.Connection, sid: int, version: int,
                              values: dict[str, Any], created_at: float) -> None:
    c.execute(
        "INSERT INTO submission_versions (submission_id, version, project_id, task_id, student_id,"
        " student_no, student_name, file_id, file_name, note, review_task_id, status, score,"
        " feedback, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, version, values["project_id"], values["task_id"], values["student_id"],
         values["student_no"], values["student_name"], values["file_id"], values["file_name"],
         values["note"], values["review_task_id"], values["status"], values["score"],
         values["feedback"], created_at),
    )


def upsert_submission(*, project_id: int, task_id: int, student_id: int,
                      student_no: str, student_name: str, file_id: int = 0,
                      file_name: str = "", note: str = "", request_key: str = "") -> dict[str, Any]:
    now = time.time()
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        if request_key:
            previous = c.execute(f"SELECT {_VER_COLS} FROM submission_versions"
                                 " WHERE student_id=? AND task_id=? AND request_key=?",
                                 (int(student_id), int(task_id), request_key)).fetchone()
            if previous:
                return {**_d(previous), "id": previous["submission_id"], "replayed": True}
        row = c.execute("SELECT id FROM submissions WHERE task_id=? AND student_no=?",
                        (int(task_id), str(student_no))).fetchone()
        if row:
            sid = int(row["id"])
            c.execute(
                "UPDATE submissions SET project_id=?, student_id=?, student_name=?, file_id=?, file_name=?,"
                " note=?, review_task_id=0, status='submitted', score=NULL, feedback='', updated_at=? WHERE id=?",
                (int(project_id), int(student_id), student_name, int(file_id), file_name, note, now, sid),
            )
            version = int(c.execute("SELECT COALESCE(MAX(version),0)+1 FROM submission_versions WHERE submission_id=?",
                                    (sid,)).fetchone()[0])
        else:
            cur = c.execute(
                "INSERT INTO submissions (project_id, task_id, student_id, student_no, student_name,"
                " file_id, file_name, note, review_task_id, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,0,'submitted',?,?)",
                (int(project_id), int(task_id), int(student_id), str(student_no), student_name,
                 int(file_id), file_name, note, now, now),
            )
            sid, version = int(cur.lastrowid), 1
        values = {"project_id": int(project_id), "task_id": int(task_id), "student_id": int(student_id),
                  "student_no": str(student_no), "student_name": student_name, "file_id": int(file_id),
                  "file_name": file_name, "note": note, "review_task_id": 0, "status": "submitted",
                  "score": None, "feedback": ""}
        _insert_submission_version(c, sid, version, values, now)
        if request_key:
            c.execute("UPDATE submission_versions SET request_key=? WHERE submission_id=? AND version=?",
                      (request_key, sid, version))
        r = c.execute(f"SELECT {_SUB_COLS} FROM submissions WHERE id=?", (sid,)).fetchone()
        c.commit()
    result = _d(r)
    result["version"] = version
    return result


def get_submission_request(student_id: int, task_id: int, request_key: str) -> Optional[dict[str, Any]]:
    if not request_key:
        return None
    with _conn() as c:
        row = c.execute(f"SELECT {_VER_COLS} FROM submission_versions"
                        " WHERE student_id=? AND task_id=? AND request_key=?",
                        (int(student_id), int(task_id), request_key)).fetchone()
    return {**_d(row), "id": row["submission_id"]} if row else None


def set_submission_review(sid: int, version: int, review_task_id: int) -> None:
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        cur = c.execute("UPDATE submission_versions SET review_task_id=?"
                        " WHERE submission_id=? AND version=? AND review_task_id=0",
                        (int(review_task_id), int(sid), int(version)))
        if cur.rowcount != 1:
            raise ValueError("提交版本不存在或已关联评审")
        c.execute("UPDATE submissions SET review_task_id=?, updated_at=? WHERE id=?"
                  " AND ?=(SELECT MAX(version) FROM submission_versions WHERE submission_id=?)",
                  (int(review_task_id), time.time(), int(sid), int(version), int(sid)))
        c.commit()


def update_submission_result(sid: int, *, status: str, score: Optional[float] = None,
                            feedback: str = "") -> None:
    with _conn() as c:
        c.execute("UPDATE submissions SET status=?, score=?, feedback=?, updated_at=? WHERE id=?",
                  (status, score, feedback, time.time(), int(sid)))
        c.execute("UPDATE submission_versions SET status=?, score=?, feedback=? WHERE submission_id=?"
                  " AND version=(SELECT MAX(version) FROM submission_versions WHERE submission_id=?)",
                  (status, score, feedback, int(sid), int(sid)))
        c.commit()


def update_submission_version_result(review_task_id: int, *, status: str,
                                     score: Optional[float] = None, feedback: str = "") -> None:
    with _conn() as c:
        c.execute("UPDATE submission_versions SET status=?, score=?, feedback=? WHERE review_task_id=?",
                  (status, score, feedback, int(review_task_id)))
        c.execute("UPDATE submissions SET status=?, score=?, feedback=?, updated_at=?"
                  " WHERE review_task_id=?",
                  (status, score, feedback, time.time(), int(review_task_id)))
        c.commit()


def get_submission(sid: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute(f"SELECT {_SUB_COLS} FROM submissions WHERE id=?", (int(sid),)).fetchone()
    return _d(r) if r else None


def get_submission_by_review_task(review_task_id: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute(f"SELECT {_SUB_COLS} FROM submissions WHERE review_task_id=?",
                      (int(review_task_id),)).fetchone()
    return _d(r) if r else None


def get_submission_version(sid: int, version: int) -> Optional[dict[str, Any]]:
    with _conn() as c:
        r = c.execute(f"SELECT {_VER_COLS} FROM submission_versions WHERE submission_id=? AND version=?",
                      (int(sid), int(version))).fetchone()
    return _d(r) if r else None


def list_submission_versions(sid: int) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(f"SELECT {_VER_COLS} FROM submission_versions WHERE submission_id=? ORDER BY version DESC",
                         (int(sid),)).fetchall()
    return [_d(r) for r in rows]


def list_submissions(project_id: Optional[int] = None,
                     student_no: Optional[str] = None) -> list[dict[str, Any]]:
    sql = (f"SELECT {', '.join('s.' + col.strip() for col in _SUB_COLS.split(','))},"
           " (SELECT MAX(v.version) FROM submission_versions v WHERE v.submission_id=s.id) AS version"
           " FROM submissions s")
    where, args = [], []
    if project_id is not None:
        where.append("s.project_id=?")
        args.append(int(project_id))
    if student_no:
        where.append("s.student_no=?")
        args.append(str(student_no))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.updated_at DESC"
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
        return [_d(r) for r in rows]
