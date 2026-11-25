"""智谱「智能体对话」封装：POST /v1/agents。

文档：https://docs.bigmodel.cn/cn/guide/agents/translation
- 鉴权：Bearer ZHIPU_API_KEY
- 请求：{agent_id, stream, messages[{role, content}], custom_variables}
- 响应：choices[0].messages[].content + finish_reason + usage

与 zhipu_media / zhipu_parser 风格一致：返回 dict，status=ok|error，不抛异常。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

from app.config import ZHIPU_API_KEY, ZHIPU_AGENT_URL

_TIMEOUT = int(os.getenv("ZHIPU_AGENT_TIMEOUT", "180"))

# 文档中提供的内嵌智能体；custom 为需要用户填写的扩展参数
AGENTS: list[dict[str, Any]] = [
    {"id": "intelligent_education_solve_agent", "name": "智能教育解题",
     "desc": "讲解题目思路、拆解知识点，适合备课与答疑", "custom": []},
    {"id": "general_translation", "name": "通用翻译",
     "desc": "多语种互译，可指定源语言与目标语言", "custom": ["source_lang", "target_lang"]},
    {"id": "slides_glm_agent", "name": "幻灯片生成",
     "desc": "根据主题生成演示文稿内容", "custom": []},
    {"id": "ai_drawing_agent", "name": "AI 绘画",
     "desc": "按文字描述生成教学配图", "custom": []},
    {"id": "receipt_recognition_agent", "name": "票据识别",
     "desc": "识别发票、小票等票据图片", "custom": []},
    {"id": "clothes_recognition_agent", "name": "服饰识别",
     "desc": "识别图片中的服饰品类与属性", "custom": []},
    {"id": "vidu_template_agent", "name": "视频模板",
     "desc": "生成视频模板化内容", "custom": []},
]

# 通用翻译智能体的语言取值（文档 lang 枚举的常用子集）
LANGUAGES = ["auto", "zh-CN", "zh-TW", "en", "en-US", "ja", "ko", "fr", "de",
             "es", "ru", "pt", "it", "ar", "th", "vi"]

DEFAULT_AGENT = "intelligent_education_solve_agent"


def _headers() -> dict:
    key = os.getenv("ZHIPU_API_KEY") or ZHIPU_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _error(msg: str, **kw) -> dict:
    out = {"status": "error", "error": msg}
    out.update(kw)
    return out


def _content_text(content: Any) -> tuple[str, list[dict[str, str]]]:
    """把响应 content（字符串 / 单个对象 / 数组）拆成 文本 + 附件链接。"""
    if isinstance(content, str):
        return content, []
    items = content if isinstance(content, list) else [content]
    texts: list[str] = []
    attachments: list[dict[str, str]] = []
    for it in items or []:
        if not isinstance(it, dict):
            texts.append(str(it))
            continue
        if it.get("text"):
            texts.append(str(it["text"]))
        for key in ("image_url", "file_url", "audio_url", "video_url"):
            if it.get(key):
                attachments.append({"type": key[:-4], "url": str(it[key])})
    return "\n".join(t for t in texts if t).strip(), attachments


def chat(agent_id: str, messages: list[dict[str, Any]],
         custom_variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """调用智能体对话（同步）。

    messages: [{"role": "user"|"assistant"|"system", "content": ...}]
    返回：{status, agent_id, conversation_id, content, attachments,
           finish_reason, finish_label, usage}
    """
    if not agent_id:
        return _error("agent_id 为空")
    msgs = [m for m in (messages or [])
            if isinstance(m, dict) and m.get("role") and m.get("content") not in (None, "")]
    if not msgs:
        return _error("messages 不能为空")
    key = os.getenv("ZHIPU_API_KEY") or ZHIPU_API_KEY
    if not key:
        return _error("未配置 ZHIPU_API_KEY")

    payload: dict[str, Any] = {"agent_id": agent_id, "stream": False, "messages": msgs}
    if custom_variables:
        payload["custom_variables"] = custom_variables

    try:
        r = requests.post(ZHIPU_AGENT_URL, headers=_headers(), json=payload, timeout=_TIMEOUT)
    except Exception as e:
        return _error(f"请求异常：{e.__class__.__name__}: {e}")

    try:
        data = r.json()
    except Exception:
        return _error(f"HTTP {r.status_code}", detail=r.text[:300])

    if r.status_code != 200:
        e = data.get("error") if isinstance(data, dict) else None
        if isinstance(e, dict):
            return _error(e.get("message") or "调用失败", code=e.get("code"), detail=r.text[:300])
        return _error(f"HTTP {r.status_code}", detail=r.text[:300])

    # 业务失败时仍返回 200，错误放在顶层 status/error 里
    top_error = data.get("error")
    if isinstance(top_error, dict):
        return _error(top_error.get("message") or "调用失败", code=top_error.get("code"))
    if data.get("status") in ("failed", "error"):
        return _error(f"智能体返回失败状态：{data.get('status')}")

    choices = data.get("choices") or []
    if not choices:
        return _error("响应中没有 choices", detail=str(data)[:300])
    first = choices[0] if choices else {}
    resp_msgs = first.get("messages") or []
    content, attachments = "", []
    for m in resp_msgs:
        text, atts = _content_text(m.get("content"))
        content = (content + "\n" + text).strip() if content else text
        attachments.extend(atts)

    finish = first.get("finish_reason") or ""
    try:
        from app.zhipu_media import classify_finish_reason
        finish_info = classify_finish_reason(finish)
    except Exception:
        finish_info = {"key": finish, "label": finish, "severity": "ok"}

    return {
        "status": "ok",
        "agent_id": data.get("agent_id") or agent_id,
        "conversation_id": data.get("conversation_id") or "",
        "content": content,
        "attachments": attachments,
        "finish_reason": finish,
        "finish_label": finish_info.get("label", ""),
        "usage": data.get("usage") or {},
    }
