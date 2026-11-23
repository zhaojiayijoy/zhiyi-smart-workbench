"""智谱 AI 异步结果查询 + 图像生成 + 视频生成。

接口对齐 https://docs.bigmodel.cn/api-reference/async-result ：
    GET  {base}/async-result/{id}                    异步结果（对话补全 / 图像生成 / 视频生成）
    POST {base}/images/generations                   图像生成（异步，返回 task_id）
    POST {base}/videos/generations                   视频生成（异步，返回 task_id）

与 zhipu_parser 风格一致：返回 dict，status=ok|error，不抛异常。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import requests

from app.config import ZHIPU_API_KEY, ZHIPU_BASE_URL

_TIMEOUT = 120  # 单次 HTTP 超时


def _headers() -> dict:
    key = os.getenv("ZHIPU_API_KEY") or ZHIPU_API_KEY
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    return os.getenv("ZHIPU_BASE_URL") or ZHIPU_BASE_URL


def _error(msg: str, **kw) -> dict:
    out = {"status": "error", "error": msg}
    out.update(kw)
    return out


# ---------------------------------------------------------------------------
# 1. 查询异步结果（对话补全 / 图像生成 / 视频生成通用）
# ---------------------------------------------------------------------------
def query_async_result(task_id: str) -> dict[str, Any]:
    """GET /paas/v4/async-result/{id}

    返回结构：
        ChatCompletionResponse          对话补全结果（choices / usage / web_search / content_filter）
        AsyncImageGenerationResponse    图像生成（image_result[].url）
        AsyncVideoGenerationResponse    视频生成（video_result[].url / cover_image_url）
    """
    if not task_id:
        return _error("task_id 为空")
    url = f"{_base().rstrip('/')}/async-result/{task_id}"
    try:
        r = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
    except Exception as e:
        return _error(f"请求异常：{e.__class__.__name__}: {e}")
    if r.status_code != 200:
        return _error(f"HTTP {r.status_code}", detail=r.text[:300])
    try:
        data = r.json()
    except Exception:
        return _error("响应不是 JSON", detail=r.text[:200])
    # 处理 PROCESSING / SUCCESS / FAIL
    status = data.get("task_status") or "ok"
    if status in ("PROCESSING", "PENDING"):
        return {"status": "processing", "task_id": task_id, "raw": data}
    if status == "FAIL":
        return _error(data.get("error", "任务失败"), raw=data)
    return {"status": "ok", "task_id": task_id, "data": data}


def poll_async_result(task_id: str, max_wait: int = 180, interval: float = 3.0) -> dict[str, Any]:
    """轮询直到 SUCCESS / FAIL 或超时，返回最终结果。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        res = query_async_result(task_id)
        if res.get("status") != "processing":
            return res
        time.sleep(interval)
    return _error(f"轮询超时（{max_wait}s）", task_id=task_id)


# ---------------------------------------------------------------------------
# 2. 图像生成（异步提交 + 轮询）
# ---------------------------------------------------------------------------
# 智谱官方图像生成模型
IMAGE_MODELS = {
    "glm-image-plus": "高质量图像生成",
    "glm-image": "标准图像生成",
    "cogview-4": "CogView 4 多模态理解生成",
    "cogview-3": "经典 CogView 3",
}


def generate_image(prompt: str, model: str = "glm-image-plus",
                   size: str = "1024x1024", num: int = 1,
                   poll: bool = True, max_wait: int = 180) -> dict[str, Any]:
    """POST /paas/v4/images/generations

    参数：
        prompt  自然语言描述（中文或英文）
        model   glm-image-plus / glm-image / cogview-4 / cogview-3
        size    1024x1024（glm-image-plus 支持 1024x1024 / 1280x720 / 720x1280 / 2048x2048 等）
        num     生成数量（1-4）
        poll    True 则等待结果；False 立即返回 task_id 供后续轮询
        max_wait 轮询超时秒数

    返回（poll=True）：
        {"status":"ok","images":[{"url":"..."}],"task_id":"...","request_id":"..."}
    """
    if not prompt.strip():
        return _error("prompt 为空")
    url = f"{_base().rstrip('/')}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": max(1, min(4, int(num))),
    }
    try:
        r = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
    except Exception as e:
        return _error(f"请求异常：{e.__class__.__name__}: {e}")
    if r.status_code != 200:
        return _error(f"HTTP {r.status_code}", detail=r.text[:500])
    try:
        data = r.json()
    except Exception:
        return _error("响应不是 JSON", detail=r.text[:200])

    # 同步返回（某些模型直接给结果）
    images = data.get("image_result") or data.get("data") or []
    if images and data.get("task_status") in (None, "SUCCESS"):
        urls = [{"url": i.get("url", "")} for i in images]
        return {"status": "ok", "images": urls, "task_id": data.get("id") or data.get("task_id", ""),
                "request_id": data.get("request_id", ""), "model": data.get("model", model)}

    # 异步：先拿 task_id，再决定是否轮询
    task_id = data.get("id") or data.get("task_id", "") or ""
    if not task_id:
        return _error("未能获取 task_id", raw=data)
    if not poll:
        return {"status": "submitted", "task_id": task_id, "raw": data}

    final = poll_async_result(task_id, max_wait=max_wait)
    if final.get("status") != "ok":
        return final
    images = final["data"].get("image_result") or final["data"].get("data") or []
    urls = [{"url": i.get("url", "")} for i in images]
    return {"status": "ok", "images": urls, "task_id": task_id,
            "request_id": final["data"].get("request_id", ""),
            "model": final["data"].get("model", model)}


# ---------------------------------------------------------------------------
# 3. 视频生成（异步提交 + 轮询）
# ---------------------------------------------------------------------------
VIDEO_MODELS = {
    "glm-video-plus": "高质量视频生成",
    "glm-video": "标准视频生成",
    "cogvideox-2": "CogVideoX 2",
    "cogvideox": "经典 CogVideoX",
}


def generate_video(prompt: str, model: str = "glm-video",
                   duration: int = 5, poll: bool = True, max_wait: int = 600) -> dict[str, Any]:
    """POST /paas/v4/videos/generations

    参数：
        prompt   视频内容描述
        model    glm-video-plus / glm-video / cogvideox-2 / cogvideox
        duration 视频时长秒数（glm-video-plus: 5/10/15s）
        poll     True 则等待结果；False 立即返回 task_id
        max_wait 视频生成较慢，默认 10 分钟

    返回（poll=True）：
        {"status":"ok","videos":[{"url":"...","cover_image_url":"..."}],"task_id":"..."}
    """
    if not prompt.strip():
        return _error("prompt 为空")
    url = f"{_base().rstrip('/')}/videos/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "duration": max(1, min(15, int(duration))),
    }
    try:
        r = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
    except Exception as e:
        return _error(f"请求异常：{e.__class__.__name__}: {e}")
    if r.status_code != 200:
        return _error(f"HTTP {r.status_code}", detail=r.text[:500])
    try:
        data = r.json()
    except Exception:
        return _error("响应不是 JSON", detail=r.text[:200])

    videos = data.get("video_result") or data.get("data") or []
    if videos and data.get("task_status") in (None, "SUCCESS"):
        out = [{"url": v.get("url", ""), "cover": v.get("cover_image_url", "")} for v in videos]
        return {"status": "ok", "videos": out, "task_id": data.get("id") or data.get("task_id", ""),
                "request_id": data.get("request_id", ""), "model": data.get("model", model)}

    task_id = data.get("id") or data.get("task_id", "") or ""
    if not task_id:
        return _error("未能获取 task_id", raw=data)
    if not poll:
        return {"status": "submitted", "task_id": task_id, "raw": data}

    final = poll_async_result(task_id, max_wait=max_wait, interval=5.0)
    if final.get("status") != "ok":
        return final
    videos = final["data"].get("video_result") or final["data"].get("data") or []
    out = [{"url": v.get("url", ""), "cover": v.get("cover_image_url", "")} for v in videos]
    return {"status": "ok", "videos": out, "task_id": task_id,
            "request_id": final["data"].get("request_id", ""),
            "model": final["data"].get("model", model)}


# ---------------------------------------------------------------------------
# 4. finish_reason / content_filter / web_search 处理（辅助工具）
# ---------------------------------------------------------------------------
# 智谱 finish_reason 枚举（文档 + 实测覆盖）
FINISH_REASON_MEANING: dict[str, str] = {
    "stop": "自然结束或触发 stop 词",
    "tool_calls": "命中函数/工具调用",
    "length": "达到输出长度上限 max_tokens",
    "sensitive": "内容被安全审核接口拦截",
    "network_error": "模型推理异常（网络问题）",
    "model_context_window_exceeded": "超出模型上下文窗口，请精简对话历史",
}


def classify_finish_reason(reason: Optional[str]) -> dict[str, str]:
    """把 finish_reason 翻译成可读信息，便于前端展示。"""
    if not reason:
        return {"key": "", "label": "", "severity": "ok"}
    label = FINISH_REASON_MEANING.get(reason, f"未知: {reason}")
    severity_map = {
        "stop": "ok", "tool_calls": "ok",
        "length": "warn",       # 建议调大 max_tokens
        "sensitive": "error",   # 安全拦截，需要用户调整 prompt
        "network_error": "error",
        "model_context_window_exceeded": "error",
    }
    return {"key": reason, "label": label, "severity": severity_map.get(reason, "ok")}


def format_content_filter(filters: Optional[list[dict]]) -> list[dict]:
    """把 content_filter 数组（role/level）格式化为前端友好的信息。

    level 0=最严重 3=轻微。
    """
    if not filters:
        return []
    role_map = {"assistant": "模型输出", "user": "用户输入", "history": "历史上下文"}
    out = []
    for f in filters:
        lvl = int(f.get("level", 3))
        out.append({
            "role": f.get("role", ""),
            "role_label": role_map.get(f.get("role", ""), f.get("role", "")),
            "level": lvl,
            "severity": "block" if lvl <= 1 else ("warn" if lvl == 2 else "info"),
            "description": ["严重违规", "较高风险", "轻微提醒", "提示"][min(lvl, 3)],
        })
    return out


def format_web_search(results: Optional[list[dict]]) -> list[dict]:
    """把 web_search 数组格式化为前端友好的引用列表。"""
    if not results:
        return []
    out = []
    for r in results:
        out.append({
            "icon": r.get("icon", ""),
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "media": r.get("media", ""),
            "publish_date": r.get("publish_date", ""),
            "content": (r.get("content", "") or "")[:500],  # 截断避免 payload 过大
            "refer": r.get("refer", ""),
        })
    return out
