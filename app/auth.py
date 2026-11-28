"""账号与登录会话。

- 密码使用 PBKDF2-HMAC-SHA256（随机盐）散列后存库，永不保存明文
- 会话令牌写入 sessions 表，默认 7 天有效，退出登录即删除
- 教师账号在启动时按 EDU_TEACHER_USER / EDU_TEACHER_PASS 创建；未配置时使用本地默认账号
- 学生账号由名单回填：用户名 = 学号，初始密码 = 学号后 6 位（不足 6 位取全串）
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Optional

from app import db

_PBKDF2_ROUNDS = 120_000
SESSION_TTL = 7 * 24 * 3600
PASSWORD_MIN_LENGTH = 12


class LoginRateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("登录尝试过多，请稍后重试")


def password_error(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        return "新密码至少 12 位"
    if len(password) > 256:
        return "密码不能超过 256 位"
    return ""


def hash_password(password: str, rounds: int = _PBKDF2_ROUNDS) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = str(stored).split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), int(rounds))
    return hmac.compare_digest(dk.hex(), digest)


def initial_password(student_no: str) -> str:
    """初始密码规则：学号后 6 位；学号不足 6 位时取整个学号。"""
    no = str(student_no or "").strip()
    return no[-6:] if len(no) >= 6 else no


TEACHER_USER = os.getenv("EDU_TEACHER_USER") or "teacher"
TEACHER_PASS = os.getenv("EDU_TEACHER_PASS") or "Zhiyi@2026"


def public_user(user: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """去掉密码散列，补上前端需要的派生字段。"""
    if not user:
        return None
    out = {k: v for k, v in user.items() if k != "password_hash"}
    out["bound"] = bool(out.get("bound"))
    out["must_change"] = bool(out.get("must_change"))
    return out


# ---------------------------------------------------------------------------
# 账号初始化
# ---------------------------------------------------------------------------
def ensure_student_user(student_no: str, name: str = "", class_name: str = "") -> bool:
    """按学号确保学生账号存在；返回是否新建。已有账号不覆盖密码与绑定信息。"""
    no = str(student_no or "").strip()
    if not no:
        return False
    if db.get_user_by_username(no):
        return False
    db.create_user(
        role="student", username=no, password_hash=hash_password(initial_password(no)),
        display_name=str(name or "").strip(), student_no=no,
        class_name=str(class_name or "").strip(), bound=0, must_change=1,
    )
    return True


def backfill_student_accounts() -> int:
    """把名单里出现过的学号都补成学生账号（历史名单升级用）。"""
    created, seen = 0, set()
    for row in db.list_all_students():
        no = str(row.get("student_no") or "").strip()
        if not no or no in seen:
            continue
        seen.add(no)
        if ensure_student_user(no, row.get("name") or "", row.get("class_name") or ""):
            created += 1
    return created


def ensure_bootstrap() -> dict[str, Any]:
    """启动时执行：建默认教师账号 + 回填学生账号 + 清理过期会话。"""
    db.initialize()
    teacher_created = False
    if not db.get_user_by_username(TEACHER_USER):
        db.create_user(
            role="teacher", username=TEACHER_USER, password_hash=hash_password(TEACHER_PASS),
            display_name="教师", bound=1,
        )
        teacher_created = True
    students_created = backfill_student_accounts()
    purged = db.purge_expired_sessions()
    return {"teacher_created": teacher_created, "students_created": students_created,
            "sessions_purged": purged}


# ---------------------------------------------------------------------------
# 登录 / 会话
# ---------------------------------------------------------------------------
def new_session(user_id: int, role: str) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(token, int(user_id), role, time.time() + SESSION_TTL)
    return token


def login(role: str, username: str, password: str, *, source: str = "local") -> tuple[Optional[dict[str, Any]], str]:
    """校验账号密码并签发会话；返回 (user, token) 或 (None, 错误信息)。"""
    name = str(username or "").strip()
    if not name or not password:
        return None, "请输入账号和密码"
    account_key = "account:" + hashlib.sha256(name.encode("utf-8")).hexdigest()
    source_key = "source:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
    retry = db.reserve_login_attempt(account_key, source_key, time.time())
    if retry:
        raise LoginRateLimited(retry)
    if len(name) > 256 or len(password) > 256:
        return None, "账号或密码错误"
    user = db.get_user_by_username(name)
    if not user or not verify_password(password, user.get("password_hash") or ""):
        return None, "账号或密码错误"
    if str(user.get("status") or "active") != "active":
        return None, "账号已停用，请联系教师"
    if user.get("role") != role:
        return None, "该账号不是" + ("教师账号" if role == "teacher" else "学生账号")
    db.clear_login_attempts(account_key)
    return user, new_session(int(user["id"]), role)


def resolve_token(token: Optional[str]) -> Optional[dict[str, Any]]:
    """令牌 -> 用户；过期或用户停用返回 None。"""
    if not token:
        return None
    sess = db.get_session(token)
    if not sess:
        return None
    if float(sess.get("expires_at") or 0) < time.time():
        db.delete_session(token)
        return None
    user = db.get_user(int(sess["user_id"]))
    if not user or str(user.get("status") or "active") != "active":
        return None
    return user


def reset_password(user_id: int, password: str, must_change: bool = False) -> None:
    """改密；must_change=True 用于教师重置，学生下次登录必须先改密。"""
    error = password_error(password)
    if error:
        raise ValueError(error)
    db.update_user(int(user_id), password_hash=hash_password(password),
                   must_change=1 if must_change else 0,
                   activation_expires_at=None)
    db.delete_user_sessions(int(user_id))
