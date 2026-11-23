"""全局配置与路径。"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# 显式指定项目根目录下的 .env，避免从其他工作目录启动时读不到配置
load_dotenv(ROOT / ".env")


def _bool(k: str, default: bool) -> bool:
    v = os.getenv(k)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 智谱 GLM（OpenAI 兼容接口）
ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", "glm-4-flash")

ALLOWED_EXT = set(e.strip().lower() for e in os.getenv("ALLOWED_EXT", ".xlsx,.xls,.csv").split(","))

# 非表格文档：交给智谱「文件解析」转为正文文本（Lite 免费，支持以下格式）
PARSER_TOOL_TYPE = os.getenv("PARSER_TOOL_TYPE", "lite")
PARSER_TIMEOUT = int(os.getenv("PARSER_TIMEOUT", "120"))
PARSER_POLL_INTERVAL = float(os.getenv("PARSER_POLL_INTERVAL", "3"))
PARSER_MAX_WAIT = int(os.getenv("PARSER_MAX_WAIT", "300"))
DOC_EXT = set(e.strip().lower() for e in os.getenv(
    "DOC_EXT",
    ".pdf,.docx,.doc,.pptx,.ppt,.md,.txt,.html,.htm,.png,.jpg,.jpeg",
).split(","))
UPLOAD_EXT = ALLOWED_EXT | DOC_EXT
MAX_ROWS_IN_CONTEXT = int(os.getenv("MAX_ROWS_IN_CONTEXT", "120"))
STRICT_DATA_GATE = _bool("STRICT_DATA_GATE", True)
# 相对路径一律以项目根目录为基准，避免从其他目录启动时把文件落到别处
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ".data/uploads"))
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = (ROOT / UPLOAD_DIR).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 项目工作目录：每个项目一个本地文件夹，任务生成的文件都落在这里
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "projects"))
if not PROJECT_DIR.is_absolute():
    PROJECT_DIR = (ROOT / PROJECT_DIR).resolve()
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# 未归属项目时的默认输出目录
EXPORT_DIR = (ROOT / ".data" / "exports").resolve()
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
