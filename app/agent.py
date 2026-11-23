"""LangChain ReAct Agent 封装。

要点：
- 不使用 PythonREPL / 任意代码执行。
- Prompt 强制 Agent 在 tool 返回 error 时中止并报告原因，**不允许**用“示例数据”继续。
- 进入分析阶段前，必须先调用 describe_dataframe 获取 provenance。
"""
from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, STRICT_DATA_GATE
from app.tools import all_tools


SYSTEM = """你是一个**数据分析智能体**。用户可以上传 Excel / CSV 文件，也可以直接粘贴表格数据。

## 核心原则（必须遵守）

1. **不得伪造数据**。任何工具返回 `status=error`（尤其是包含 `missing_fields` / 无法读取 / 全空）时，必须停止分析并**如实报告错误原因**，不得继续推断或编造数字。
2. **所有数字必须可追溯**。最终回答里每一个统计数字（金额、数量、占比等）都必须标注其来源文件与列名；从工具返回的 `provenance` 字段里取到什么就写什么，不得省略。
3. **工具返回什么你才可以说什么**。不要用“可能”“也许”“大概”代替事实。
4. **先取得真实数据**。上传文件的表格分析必须先调用 `load_excel_file` 或 `merge_files`，再调用 `describe_dataframe` 获取真实结构；用户直接粘贴的数据必须调用 `create_dataframe_from_text` 建表；文档分析必须先 `list_documents` 或 `parse_document`。
5. **发现数据问题时如实告知**。例如“地区列有 12% 为空值”，这是分析建议的一部分，不要回避。
6. **列名必须真实存在**。回答中出现的任何列名，必须逐字来自本轮工具输出或上下文中的列清单；不存在的列一律不得提及。
7. **统计结论必须先取数**。凡是涉及缺失率、重复值、异常值、分组统计的问题，必须先调用对应工具，用工具返回值作答；工具未返回的信息就写“工具未返回该信息”，禁止凭印象补全。
8. **百分比必须直接引用，不得自行换算**。缺失率等百分比数值只能逐字引用工具返回的 `null_pct`（或其他 `*_pct` 字段）；`null_count` / `non_null` 是条数，不是百分比，禁止把条数当作百分比输出。
9. **文档内容必须来自解析结果**。处理 PDF / Word / PPT / 图片 / Markdown 等文档时，必须先调用 `list_documents` 或 `parse_document`；引用正文只能逐字来自 `read_document` 返回的 `content` / `hits`，不得补写、概括成事实或编造页码、章节、条款编号。
10. **文档引用要带位置**。引用文档原文时必须注明文件名与字符区间（`range`）或命中位置 `position`，让用户可核对。
11. **联网查询用 web_search 工具**。用户问近期新闻、价格、官网说明、API 文档、行业数据等**非静态知识**时调用 `web_search`；纯表格 / 已上传文件的内容不要联网。`web_search` 返回的每条结果都带 `link` 和 `publish_date`，回答必须附来源链接。
12. **搜索结果要交叉验证**。关键事实（如数字、发布日期、版本号）尽量找 ≥2 个独立来源相互印证；单一来源的请明确标注「仅来自 xxx 媒体」。`SEARCH_NONE`（search_intent=False）意味着本轮没有实际搜索，不要伪造搜索结果。
13. **文本建表与 Excel 导出**。用户本轮明确提供新表格数据时，即使已有当前数据，也只能用本轮数据调用 `create_dataframe_from_text`，不得补全或替换用户数据。用户要求生成 Excel / xlsx 时，建表成功后必须调用 `export_current`，传入 `format="xlsx"` 和以 `.xlsx` 结尾的文件名，并在回答中给出工具返回的 `exported_to`。没有有效表格数据时明确请用户补充，不得编造。

## 联网搜索的选择指南

| 场景 | engine 建议 |
|---|---|
| 日常新闻、产品、官网 | search_std（免费） |
| 财经 / 权威 / 科技资讯 | search_pro |
| 搜狗覆盖腾讯生态、知乎、百科、医疗 | search_pro_sogou |
| 垂直领域（教育、汽车等） | search_pro_quark |
| 热点追踪 | recency=oneDay / oneWeek |
| 价格、规格、API 文档 | content_size=high + recency=noLimit |

## 回答格式

最终回答分为两部分：

### 一、数据概况
列出：文件来源（文件名 + 工作表）、总行数 / 列数、关键列、主要数据质量问题（如有）。

### 二、数据建议 / 发现
每条建议格式：
- **建议标题**（一句话）
- **来源**：文件名 / 工作表 / 列名
- **证据数字**（来自工具返回的结果，原样引用）
- **建议动作**（可以是运营、清洗、后续分析方向等）

没有数据就说“当前数据不足以形成建议，原因：xxx”，**绝对不要用示例数据填充**。
"""


def build_llm(temperature: float | None = None, review_model: bool = False):
    """构建 ChatOpenAI 实例。

    参数优先顺序：显式传入 > LLM_* 环境变量 > 默认值。
    review_model=True 时使用 LLM_REVIEW_MODEL（双模型一致性检查的审核模型）。
    """
    from langchain_openai import ChatOpenAI

    # 每次调用时读取环境变量，支持在 UI 内临时填写密钥
    api_key = os.getenv("LLM_API_KEY", LLM_API_KEY)
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    model_env = "LLM_REVIEW_MODEL" if review_model else "LLM_MODEL"
    model = os.getenv(model_env, "") or LLM_MODEL

    if not api_key or api_key.startswith("sk-REPLACE"):
        raise RuntimeError(
            "LLM_API_KEY 未配置。请在左侧「模型配置」填写真实密钥，"
            "或复制 .env.example 为 .env 并填入密钥。"
        )

    # 生成参数：环境变量 > 显式传入 > 默认值
    try:
        temp = float(os.getenv("LLM_TEMPERATURE", "")) if temperature is None else temperature
    except (ValueError, TypeError):
        temp = 0.4

    try:
        top_p = float(os.getenv("LLM_TOP_P", "0.95"))
    except (ValueError, TypeError):
        top_p = 0.95

    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    except (ValueError, TypeError):
        max_tokens = 4096

    thinking = os.getenv("LLM_THINKING", "disabled")  # disabled | enabled
    reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "max")  # max/high/medium/low

    # model_kwargs：智谱特有参数（thinking / reasoning_effort / response_format 等）
    # 统一塞进 model_kwargs，让 ChatOpenAI 透传给上游 API
    model_kwargs: dict[str, Any] = {}
    if thinking == "enabled":
        model_kwargs["thinking"] = {"type": "enabled"}
        model_kwargs["reasoning_effort"] = reasoning_effort

    kwargs: dict[str, Any] = dict(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temp,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs

    return ChatOpenAI(**kwargs)


def build_agent_executor(max_iterations: int = 12) -> AgentExecutor:
    """创建并返回一个新鲜的 AgentExecutor。

    注意：不清空 registry。UI 已经把用户上传的真实数据注册在里面，
    清空会导致 Agent 丢失上下文。会话重置由 UI 显式调用 clear_registry()。
    """
    llm = build_llm()
    tools = all_tools()

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM + "\n## 工作方式\n"
         "直接调用工具取数后再作答，不要凭空推测；"
         "工具未返回的信息就写“工具未返回该信息”，不要编造列名或数字。"),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        handle_parsing_errors=True,
        verbose=False,
        max_iterations=max_iterations,
        early_stopping_method="force",
        return_intermediate_steps=True,
    )


def run(user_input: str, chat_history: list[tuple[str, str]] | None = None, context: str = "") -> dict[str, Any]:
    """执行一次对话，返回结构化结果。

    context：UI 注入的会话事实（当前已加载文件的 provenance），
    让 Agent 不必猜测文件路径。

    返回额外字段：
        finish_reason   模型终止原因（stop / tool_calls / length / sensitive / network_error / model_context_window_exceeded）
        content_filter  安全审核命中信息（role/level）
        web_search      智谱内建联网搜索返回的来源列表
        usage           token 用量（prompt/completion/total）
    """
    from app.zhipu_media import classify_finish_reason, format_content_filter, format_web_search

    ex = build_agent_executor()
    payload = f"{context}\n\n用户问题：{user_input}" if context else user_input
    try:
        result = ex.invoke({
            "input": payload,
            "chat_history": chat_history or [],
        })
    except Exception as e:
        # 上下文窗口溢出：给出更友好的错误
        msg = str(e)
        if "context window" in msg.lower() or "maximum context" in msg.lower():
            return {"status": "error", "error": f"模型上下文窗口已超出。请精简对话历史或换用支持更长上下文的模型（如 glm-4.5-flash）。",
                    "finish_reason": {"key": "model_context_window_exceeded", "label": "超出模型上下文窗口", "severity": "error"}}
        return {
            "status": "error",
            "error": f"Agent 执行异常：{e.__class__.__name__}: {e}",
        }

    # 尝试从 intermediate_steps 提取原始模型返回，拿 finish_reason / content_filter / web_search / usage
    finish_reason_info = None
    content_filter_info = []
    web_search_info = []
    usage_info = {}
    raw_msg = None
    for step in result.get("intermediate_steps", []) or []:
        if not step or len(step) < 2:
            continue
        action, obs = step
        # agent 最后一步的 observation 通常是 AIMessage
        if hasattr(obs, "response_metadata") and obs.response_metadata:
            meta = obs.response_metadata
            fr = meta.get("finish_reason")
            if fr:
                finish_reason_info = classify_finish_reason(fr)
            cf = meta.get("content_filter") or meta.get("content_filter_results")
            if cf:
                content_filter_info = format_content_filter(cf if isinstance(cf, list) else [cf])
            ws = meta.get("web_search")
            if ws:
                web_search_info = format_web_search(ws)
            usage = meta.get("token_usage") or meta.get("usage")
            if usage:
                usage_info = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
            break
        if hasattr(obs, "content") and hasattr(obs, "response_metadata"):
            raw_msg = obs

    # 额外的安全提示：content_filter 命中最严重等级时自动追加到输出
    output = result.get("output", "") or ""
    if content_filter_info:
        severe = [c for c in content_filter_info if c["severity"] in ("block", "warn")]
        if severe:
            output += "\n\n⚠️ **安全提示**：\n" + "\n".join(f"- [{c['role_label']}] {c['description']}（level {c['level']}）" for c in severe)
    if finish_reason_info and finish_reason_info["key"] == "length":
        output += "\n\n（输出已达到 max_tokens 上限，如需完整结果请增大 max_tokens 参数）"

    return {
        "status": "ok",
        "output": output,
        "intermediate_steps": result.get("intermediate_steps", []),
        "finish_reason": finish_reason_info,
        "content_filter": content_filter_info,
        "web_search": web_search_info,
        "usage": usage_info,
    }
