"""智谱 Web Search API 客户端。

接口（https://docs.bigmodel.cn/api-reference/工具-api/网络搜索）：
    POST {base}/web_search   JSON body

契约：返回 dict，status = ok | error；绝不伪造搜索结果。
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from app.config import ZHIPU_API_KEY, ZHIPU_BASE_URL

SEARCH_ENGINES = ("search_std", "search_pro", "search_pro_sogou", "search_pro_quark")
RECENCY_FILTERS = ("oneDay", "oneWeek", "oneMonth", "oneYear", "noLimit")
CONTENT_SIZES = ("medium", "high")
DEFAULT_ENGINE = "search_std"
DEFAULT_TIMEOUT = 15

# 智谱 Web Search API 特有的错误码
# https://docs.bigmodel.cn/api-reference/工具-api/网络搜索
ERROR_CODES: dict[str, str] = {
    "1701": "网络搜索并发已达上限，请稍后重试或减少并发请求",
    "1702": "系统未找到可用的搜索引擎服务，请检查配置或联系管理员",
    "1703": "搜索引擎未返回有效数据，请调整查询条件",
}


def _explain_error(code: str) -> str:
    """把智谱 web_search 错误码翻译成中文描述。"""
    return ERROR_CODES.get(str(code), "")


def _api_key() -> str:
    return (os.getenv("ZHIPU_API_KEY") or ZHIPU_API_KEY or "").strip()


def _base_url() -> str:
    return (os.getenv("ZHIPU_BASE_URL") or ZHIPU_BASE_URL).rstrip("/")


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
        hint = _explain_error(code)
        if hint:
            message = f"{hint}（code={code}，原始：{message}）" if message else hint
        elif code:
            message = f"code={code} {message}".strip()
        return {"status": "error", "error": f"HTTP {resp.status_code} {message}".strip(),
                "http_status": resp.status_code, "code": code}
    if not isinstance(body, dict):
        return {"status": "error", "error": f"响应不是 JSON：{resp.text[:300]}"}
    return {"status": "ok", "body": body}


def web_search(
    query: str,
    search_engine: str = DEFAULT_ENGINE,
    search_intent: bool = True,
    count: int = 10,
    domain_filter: str | None = None,
    recency_filter: str = "noLimit",
    content_size: str = "medium",
    request_id: str | None = None,
    user_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """一次调用完成联网搜索。

    Args:
        query: 搜索内容，建议 ≤70 字符
        search_engine: search_std / search_pro / search_pro_sogou / search_pro_quark
        search_intent: True 时先做意图识别（判断是否需要搜索）
        count: 1-50，默认 10
        domain_filter: 限定白名单域名（如 www.example.com）
        recency_filter: oneDay / oneWeek / oneMonth / oneYear / noLimit
        content_size: medium（摘要）/ high（最大化上下文）
        request_id / user_id: 可选，长度见 OpenAPI 说明

    Returns:
        ok={status:"ok", intent, results:[{title,content,link,media,icon,publish_date,refer}]}
        err={status:"error", error}
    """
    key = _api_key()
    if not key:
        return {"status": "error", "error": "未配置 ZHIPU_API_KEY，无法调用智谱网络搜索"}

    q = query.strip()
    if not q:
        return {"status": "error", "error": "搜索内容为空"}
    if len(q) > 70:
        q = q[:70]

    eng = search_engine.strip().lower()
    if eng not in SEARCH_ENGINES:
        return {"status": "error",
                "error": f"search_engine 必须是 {SEARCH_ENGINES}，收到 {eng!r}"}
    if not (1 <= count <= 50):
        return {"status": "error", "error": f"count 必须在 1-50，收到 {count}"}
    if recency_filter not in RECENCY_FILTERS:
        return {"status": "error",
                "error": f"search_recency_filter 必须是 {RECENCY_FILTERS}，收到 {recency_filter!r}"}
    if content_size not in CONTENT_SIZES:
        return {"status": "error",
                "error": f"content_size 必须是 {CONTENT_SIZES}，收到 {content_size!r}"}

    payload: dict[str, Any] = {
        "search_query": q,
        "search_engine": eng,
        "search_intent": bool(search_intent),
        "count": int(count),
        "search_recency_filter": recency_filter,
        "content_size": content_size,
    }
    if domain_filter:
        payload["search_domain_filter"] = domain_filter.strip()
    if request_id:
        payload["request_id"] = request_id
    if user_id:
        payload["user_id"] = user_id

    started = time.time()
    try:
        resp = requests.post(
            f"{_base_url()}/web_search",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as e:
        return {"status": "error",
                "error": f"请求失败：{e.__class__.__name__}: {e}",
                "elapsed_s": round(time.time() - started, 2)}

    res = _parse_http(resp)
    if res["status"] != "ok":
        res["elapsed_s"] = round(time.time() - started, 2)
        return res

    body = res["body"]
    intent = body.get("search_intent") or []
    results = body.get("search_result") or []

    intent_type = (intent[0].get("intent") if isinstance(intent, list) and intent else "SEARCH_ALWAYS")
    if intent_type == "SEARCH_NONE":
        return {
            "status": "ok",
            "intent": intent,
            "results": [],
            "note": "search_intent 判定为 SEARCH_NONE，本次请求未执行实际搜索",
            "elapsed_s": round(time.time() - started, 2),
        }

    normalized: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        normalized.append({
            "title": r.get("title") or "",
            "content": r.get("content") or "",
            "link": r.get("link") or "",
            "media": r.get("media") or "",
            "icon": r.get("icon") or "",
            "publish_date": r.get("publish_date") or "",
            "refer": r.get("refer") or "",
        })

    return {
        "status": "ok",
        "request_id": body.get("request_id"),
        "intent": intent,
        "results": normalized,
        "count": len(normalized),
        "elapsed_s": round(time.time() - started, 2),
    }
