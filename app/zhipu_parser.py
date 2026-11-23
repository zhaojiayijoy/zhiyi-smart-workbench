"""智谱「文件解析」客户端（异步任务 + 轮询取结果）。

接口（https://docs.bigmodel.cn/cn/guide/tools/file-parser）：
    POST {base}/files/parser/create          multipart: file, tool_type, file_type
    GET  {base}/files/parser/result/{task_id}/{format_type}   format_type: text | download_link

契约与 app.loader 保持一致：
    返回 dict，status = ok | error；不抛异常；绝不伪造正文内容。
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from app.config import (
    PARSER_MAX_WAIT,
    PARSER_POLL_INTERVAL,
    PARSER_TIMEOUT,
    PARSER_TOOL_TYPE,
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
)

# 扩展名 -> 接口 file_type 枚举
EXT_TO_FILE_TYPE: dict[str, str] = {
    ".pdf": "PDF", ".docx": "DOCX", ".doc": "DOC", ".xls": "XLS", ".xlsx": "XLSX",
    ".ppt": "PPT", ".pptx": "PPTX", ".png": "PNG", ".jpg": "JPG", ".jpeg": "JPEG",
    ".csv": "CSV", ".txt": "TXT", ".md": "MD", ".html": "HTML", ".htm": "HTML",
    ".bmp": "BMP", ".gif": "GIF", ".webp": "WEBP", ".heic": "HEIC", ".eps": "EPS",
    ".icns": "ICNS", ".im": "IM", ".pcx": "PCX", ".ppm": "PPM", ".tiff": "TIFF",
    ".xbm": "XBM", ".heif": "HEIF", ".jp2": "JP2",
}

# 各解析工具支持的 file_type（见官方「解析服务对比」）
TOOL_SUPPORTED: dict[str, set[str]] = {
    "lite": {
        "PDF", "DOCX", "DOC", "XLS", "XLSX", "PPT", "PPTX",
        "PNG", "JPG", "JPEG", "CSV", "TXT", "MD",
    },
    "expert": {"PDF"},
    "prime": set(EXT_TO_FILE_TYPE.values()),
}

SUCCESS_STATUS = {"succeeded", "success", "done", "completed"}
PENDING_STATUS = {"processing", "pending", "running", "queued", "starting"}


def _api_key() -> str:
    return (os.getenv("ZHIPU_API_KEY") or ZHIPU_API_KEY or "").strip()


def _base_url() -> str:
    return (os.getenv("ZHIPU_BASE_URL") or ZHIPU_BASE_URL).rstrip("/")


def _tool_type() -> str:
    return (os.getenv("PARSER_TOOL_TYPE") or PARSER_TOOL_TYPE).strip().lower()


def detect_file_type(path: str | Path) -> Optional[str]:
    return EXT_TO_FILE_TYPE.get(Path(path).suffix.lower())


def _post_file(url: str, headers: dict[str, str], file_path: Path, extra: dict[str, str]) -> dict[str, Any]:
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers=headers,
                files={"file": (file_path.name, f)},
                data=extra,
                timeout=PARSER_TIMEOUT,
            )
    except requests.RequestException as e:
        return {"status": "error", "error": f"上传失败：{e.__class__.__name__}: {e}"}
    return _parse_http(resp)


def _parse_http(resp: requests.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        body = None

    if not resp.ok:
        code, message = "", resp.text[:500]
        if isinstance(body, dict):
            err = body.get("error") if isinstance(body.get("error"), dict) else body
            code = str(err.get("code", "")) if isinstance(err, dict) else ""
            message = str(err.get("message", message)) if isinstance(err, dict) else message
        return {
            "status": "error",
            "error": f"HTTP {resp.status_code} {code}：{message}".strip(),
            "http_status": resp.status_code,
        }
    if not isinstance(body, dict):
        return {"status": "error", "error": f"响应不是 JSON：{resp.text[:300]}", "http_status": resp.status_code}
    return {"status": "ok", "body": body}


def create_task(path: str | Path, tool_type: str | None = None, file_type: str | None = None) -> dict[str, Any]:
    """创建解析任务，返回 {status, task_id, ...}。"""
    key = _api_key()
    if not key:
        return {"status": "error", "error": "未配置 ZHIPU_API_KEY，无法调用智谱文件解析"}

    p = Path(path)
    if not p.exists():
        return {"status": "error", "error": f"文件不存在：{p}"}

    ftype = (file_type or detect_file_type(p) or "").upper()
    if not ftype:
        return {"status": "error", "error": f"无法识别扩展名 {p.suffix} 对应的 file_type"}
    ttype = (tool_type or _tool_type()).lower()
    if ttype not in TOOL_SUPPORTED:
        return {"status": "error", "error": f"tool_type 只能是 lite / expert / prime，收到 {ttype!r}"}
    if ftype not in TOOL_SUPPORTED[ttype]:
        return {"status": "error",
                "error": f"{ttype} 解析服务不支持 {ftype} 格式，可用：{sorted(TOOL_SUPPORTED[ttype])}"}

    res = _post_file(
        f"{_base_url()}/files/parser/create",
        {"Authorization": f"Bearer {key}"},
        p,
        {"tool_type": ttype, "file_type": ftype},
    )
    if res["status"] != "ok":
        return res

    body = res["body"]
    task_id = body.get("task_id") or body.get("taskId") or body.get("id")
    if not task_id:
        return {"status": "error", "error": f"创建任务成功但未返回 task_id：{body}"}
    if body.get("success") is False:
        return {"status": "error", "error": f"创建任务失败：{body.get('message', body)}"}

    return {"status": "ok", "task_id": str(task_id), "tool_type": ttype, "file_type": ftype,
            "message": body.get("message", "")}


def get_result(task_id: str, format_type: str = "text") -> dict[str, Any]:
    """查询一次解析结果。status 透传接口的 processing / succeeded / failed。"""
    key = _api_key()
    if not key:
        return {"status": "error", "error": "未配置 ZHIPU_API_KEY，无法调用智谱文件解析"}

    try:
        resp = requests.get(
            f"{_base_url()}/files/parser/result/{task_id}/{format_type}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=PARSER_TIMEOUT,
        )
    except requests.RequestException as e:
        return {"status": "retry", "error": f"查询失败：{e.__class__.__name__}: {e}"}

    res = _parse_http(resp)
    if res["status"] != "ok":
        # 404 常见于任务刚创建尚未就绪，交给轮询重试
        res["status"] = "retry" if resp.status_code in (404, 429) or resp.status_code >= 500 else "error"
        return res

    body = res["body"]
    state = str(body.get("status", "")).lower()
    return {
        "status": state or "unknown",
        "message": body.get("message", ""),
        "content": body.get("content") or "",
        "result_url": body.get("parsing_result_url") or body.get("result_url"),
        "task_id": body.get("task_id", task_id),
        "raw": body,
    }


def parse_file(
    path: str | Path,
    tool_type: str | None = None,
    file_type: str | None = None,
    format_type: str = "text",
    poll_interval: float | None = None,
    max_wait: int | None = None,
    progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """创建任务并轮询到出结果。

    返回：
        {status:"ok", content, provenance:{file, file_type, tool_type, task_id, chars, elapsed_s, result_url}}
        {status:"error", error, provenance}
    """
    p = Path(path)
    created = create_task(p, tool_type=tool_type, file_type=file_type)
    prov: dict[str, Any] = {
        "file": p.name,
        "file_type": created.get("file_type") or detect_file_type(p),
        "tool_type": created.get("tool_type") or (tool_type or _tool_type()),
        "format_type": format_type,
        "task_id": created.get("task_id"),
        "chars": 0,
    }
    if created["status"] != "ok":
        return {"status": "error", "error": created.get("error", "创建解析任务失败"), "provenance": prov}

    task_id = created["task_id"]
    interval = PARSER_POLL_INTERVAL if poll_interval is None else poll_interval
    limit = PARSER_MAX_WAIT if max_wait is None else max_wait
    started = time.time()

    while True:
        elapsed = time.time() - started
        if elapsed > limit:
            return {"status": "error",
                    "error": f"解析超时（已等待 {int(elapsed)} 秒，task_id={task_id}），可稍后重新查询",
                    "provenance": {**prov, "elapsed_s": round(elapsed, 1)}}

        if progress:
            progress(f"解析中（{created.get('tool_type')}）· 已等待 {int(elapsed)} 秒")

        r = get_result(task_id, format_type)
        state = r["status"]

        if state in SUCCESS_STATUS:
            content = r.get("content") or ""
            result_url = r.get("result_url")

            # download_link 模式：接口不返回正文，只给结果压缩包链接
            if format_type == "download_link":
                if not result_url:
                    return {"status": "error",
                            "error": "解析成功但接口未返回 parsing_result_url",
                            "provenance": {**prov, "elapsed_s": round(elapsed, 1)}}
                return {"status": "ok",
                        "content": "",
                        "provenance": {**prov, "chars": 0,
                                       "elapsed_s": round(time.time() - started, 1),
                                       "result_url": result_url,
                                       "message": r.get("message", "")}}

            if content:
                return {"status": "ok",
                        "content": content,
                        "provenance": {**prov, "chars": len(content),
                                       "elapsed_s": round(time.time() - started, 1),
                                       "result_url": result_url,
                                       "message": r.get("message", "")}}

            # text 模式没给正文：再查一次 download_link，把结果链接如实交给调用方
            fallback = get_result(task_id, "download_link")
            link = fallback.get("result_url") if fallback["status"] in SUCCESS_STATUS else None
            return {"status": "error",
                    "error": "解析任务成功但 text 模式未返回正文"
                             + (f"，结果下载链接：{link}" if link else "，且未取到 download_link"),
                    "provenance": {**prov, "elapsed_s": round(elapsed, 1), "result_url": link}}

        if state in PENDING_STATUS or state == "retry":
            time.sleep(interval)
            continue

        # failed / 其它未知状态：如实返回接口消息
        return {"status": "error",
                "error": f"解析失败（status={state}）：{r.get('message') or r.get('error') or '接口未给出原因'}",
                "provenance": {**prov, "elapsed_s": round(elapsed, 1)}}


def parse_sync(
    path: str | Path,
    tool_type: str | None = None,
    file_type: str | None = None,
    format_type: str = "text",
    timeout: int | None = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    """同步解析：一次调用完成「创建任务 → 轮询结果」，阻塞到出结果才返回。

    与异步用法的区别：调用方拿到返回值时任务已经结束（成功 / 失败 / 超时），
    不需要自己维护 task_id 与轮询循环。on_progress 收到的是真实轮询状态文本。

    返回：
        {status:"ok", text, task_id, chars, elapsed_s, result_url, states}
        {status:"error", error, task_id, states}
    """
    states: list[str] = []

    def _progress(msg: str) -> None:
        states.append(msg)
        if on_progress:
            on_progress(msg)

    res = parse_file(
        path,
        tool_type=tool_type,
        file_type=file_type,
        format_type=format_type,
        max_wait=timeout,
        progress=_progress,
    )
    prov = res.get("provenance", {}) or {}

    if res.get("status") == "ok":
        states.append("解析完成")
        content = res.get("content", "")
        return {
            "status": "ok",
            "text": content,
            "task_id": prov.get("task_id"),
            "chars": prov.get("chars", len(content)),
            "elapsed_s": prov.get("elapsed_s"),
            "result_url": prov.get("result_url"),
            "provenance": prov,
            "states": states,
        }

    states.append(f"失败：{res.get('error', '解析失败')}")
    return {
        "status": "error",
        "error": res.get("error", "解析失败"),
        "task_id": prov.get("task_id"),
        "provenance": prov,
        "states": states,
    }
