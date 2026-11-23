"""LangChain 工具集。

所有工具都是确定的 pandas 操作，不执行任意 Python。
返回结构遵循 app.loader 的契约：status + provenance + payload 或 error。
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from langchain_core.tools import tool

from app.config import MAX_ROWS_IN_CONTEXT, EXPORT_DIR
from app.loader import read_file


# ---------------------------------------------------------------------------
# 输出目录 —— 由界面按「当前项目」设置，任务生成的文件都落到项目文件夹
# ---------------------------------------------------------------------------
_OUTPUT_DIR: Optional[Path] = None


def set_output_dir(path: str | Path | None) -> None:
    global _OUTPUT_DIR
    _OUTPUT_DIR = Path(path) if path else None


def get_output_dir() -> Path:
    return _OUTPUT_DIR or EXPORT_DIR


# ---------------------------------------------------------------------------
# 进程内数据寄存器 —— 工具间共享 DataFrame
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, dict[str, Any]] = {}


def register(df: pd.DataFrame, provenance: dict[str, Any], key: str = "current") -> None:
    _REGISTRY[key] = {"df": df, "provenance": provenance}


def get_registered(key: str = "current") -> Optional[dict[str, Any]]:
    return _REGISTRY.get(key)


def clear_registry() -> None:
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# 文档寄存器 —— 智谱文件解析出来的正文（PDF / Word / PPT / 图片 / Markdown …）
# ---------------------------------------------------------------------------
_DOCS: dict[str, dict[str, Any]] = {}
_DOC_PREVIEW = 2500


def register_document(name: str, content: str, provenance: dict[str, Any]) -> None:
    _DOCS[name] = {"content": content, "provenance": provenance}


def get_documents() -> dict[str, dict[str, Any]]:
    return _DOCS


def clear_documents() -> None:
    _DOCS.clear()


# ---------------------------------------------------------------------------
# 搜索结果寄存器 —— 智谱 Web Search API 返回的结构化结果
# ---------------------------------------------------------------------------
_SEARCHES: list[dict[str, Any]] = []


def register_search(result: dict[str, Any]) -> None:
    _SEARCHES.append(result)


def get_searches() -> list[dict[str, Any]]:
    return _SEARCHES


def clear_searches() -> None:
    _SEARCHES.clear()


# ---------------------------------------------------------------------------
# 工具：从用户直接输入的文本建表
# ---------------------------------------------------------------------------
@tool
def create_dataframe_from_text(text: str) -> str:
    """将用户直接输入的表格文本创建并注册为当前 DataFrame。

    Args:
        text: 只包含用户明确提供的表头和数据，支持 CSV、TSV、Markdown 表格或 JSON 对象数组。
              不要加入任务说明，不要补充用户未提供的字段或数据。
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    if not raw:
        return _json({"status": "error", "error": "没有收到可建表的数据"})

    try:
        if raw.startswith("["):
            payload = json.loads(raw)
            if not isinstance(payload, list) or not payload or not all(isinstance(row, dict) for row in payload):
                return _json({"status": "error", "error": "JSON 数据必须是非空的对象数组"})
            df = pd.DataFrame(payload)
        else:
            lines = [line for line in raw.splitlines() if line.strip()]
            sample = "\n".join(lines[:10])
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
            except csv.Error:
                delimiter = "\t" if "\t" in lines[0] else ("|" if "|" in lines[0] else ",")
            if delimiter == "|" and len(lines) > 1:
                separator_cells = lines[1].strip().strip("|").split("|")
                if all(cell.strip() and set(cell.strip()) <= {"-", ":"} for cell in separator_cells):
                    lines.pop(1)
            df = pd.read_csv(io.StringIO("\n".join(lines)), sep=delimiter, engine="python")
    except (json.JSONDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError, TypeError) as e:
        return _json({"status": "error", "error": f"文本表格解析失败：{e}"})

    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.empty or not len(df.columns):
        return _json({"status": "error", "error": "未识别到有效数据行，请提供表头和至少一行数据"})

    df.columns = [
        str(col).strip() if str(col).strip() and not str(col).startswith("Unnamed:") else f"列{i + 1}"
        for i, col in enumerate(df.columns)
    ]
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].map(lambda value: value.strip() if isinstance(value, str) else value)
    provenance = {
        "file": "用户直接输入",
        "sheet": "Sheet1",
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
        "columns": list(df.columns),
        "source": "inline_text",
    }
    register(df, provenance)
    return _json({
        "status": "ok",
        "provenance": provenance,
        "summary": {
            "shape": list(df.shape),
            "columns": list(df.columns),
            "dtypes": {col: str(df[col].dtype) for col in df.columns},
        },
        "df_preview": df.head(MAX_ROWS_IN_CONTEXT).fillna("").to_dict(orient="records"),
    })


# ---------------------------------------------------------------------------
# 工具：文件加载
# ---------------------------------------------------------------------------
@tool
def load_excel_file(path: str, sheet_name: str = "0") -> str:
    """读取一个 Excel / CSV 文件并注册到当前会话，后续工具都默认基于这份数据。

    Args:
        path: 绝对路径或相对路径（相对于当前工作目录），例如 `demo/sales.xlsx`
        sheet_name: 工作表名或索引（字符串 "0" / "Sheet1"）。CSV 文件忽略此参数

    Returns:
        JSON 字符串，包含 status / provenance / summary / sample_preview。
        当 status=error 时包含 error 与 missing_fields，调用方必须中止。
    """
    try:
        sheet_key: int | str = int(sheet_name) if sheet_name.isdigit() else sheet_name
    except ValueError:
        sheet_key = sheet_name
    result = read_file(path, sheet_name=sheet_key)
    if result.get("status") == "ok":
        register(result["_df"], result["provenance"])
        out = {k: v for k, v in result.items() if k != "_df"}
    else:
        out = result
    return _json(out)


# ---------------------------------------------------------------------------
# 工具：列出当前会话数据的列与统计
# ---------------------------------------------------------------------------
@tool
def describe_dataframe() -> str:
    """返回当前已注册 DataFrame 的列名、类型、空值、唯一值等摘要。

    用于在制定分析计划前了解数据结构。
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame，请先调用 load_excel_file"})
    df: pd.DataFrame = r["df"]
    summary = {
        "provenance": r["provenance"],
        "shape": list(df.shape),
        "columns": [
            {
                "name": c,
                "dtype": str(df[c].dtype),
                "non_null": int(df[c].notna().sum()),
                "null_count": int(df[c].isna().sum()),
                "null_pct": round(float(df[c].isna().mean()) * 100, 1),
                "n_unique": int(df[c].nunique(dropna=True)),
                "sample": df[c].dropna().astype(str).head(3).tolist(),
            }
            for c in df.columns
        ],
    }
    return _json({"status": "ok", "summary": summary})


# ---------------------------------------------------------------------------
# 工具：选择子集
# ---------------------------------------------------------------------------
@tool
def select_columns(columns: str) -> str:
    """只保留指定列。按列名（逗号分隔）。列名匹配大小写不敏感。

    Args:
        columns: 列名，逗号分隔。例如 `订单号, 销售日期, 销售额`
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    want = [c.strip() for c in columns.split(",") if c.strip()]
    df = r["df"]
    mapping = {c.lower(): c for c in df.columns}
    missing = [w for w in want if w.lower() not in mapping]
    if missing:
        return _json({"status": "error", "error": f"下列列不存在：{missing}",
                      "provenance": r["provenance"], "available_columns": list(df.columns)})
    keep = [mapping[w.lower()] for w in want]
    new_df = df[keep].copy()
    new_prov = {**r["provenance"], "cols": len(new_df.columns), "columns": keep}
    register(new_df, new_prov)
    return _json({"status": "ok", "provenance": new_prov, "columns_kept": keep})


# ---------------------------------------------------------------------------
# 工具：按维度分组聚合
# ---------------------------------------------------------------------------
@tool
def groupby_aggregate(group_by: str, aggregate: str = "销售额:sum,订单号:count") -> str:
    """按一个或多个维度分组，对一个或多个数值列执行聚合。

    Args:
        group_by: 分组列，逗号分隔。例如 `销售日期, 地区`
        aggregate: 聚合定义，格式 `列名:函数`，多个逗号分隔。
                   支持的函数：sum / mean / count / min / max / median / nunique。
                   例如 `销售额:sum, 订单号:count`

    Returns:
        JSON，status=ok 时 result 为聚合后的前 MAX_ROWS_IN_CONTEXT 行；
        同时给出 sum 聚合的合计 total 供 LLM 参考。
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    df = r["df"]
    cols_map = {c.lower(): c for c in df.columns}

    group_cols: list[str] = []
    for g in [s.strip() for s in group_by.split(",") if s.strip()]:
        real = cols_map.get(g.lower())
        if real is None:
            return _json({"status": "error", "error": f"分组列 {g!r} 不存在",
                          "provenance": r["provenance"], "available_columns": list(df.columns)})
        group_cols.append(real)

    agg_spec: dict[str, list[str]] = {}
    for spec in [s.strip() for s in aggregate.split(",") if s.strip()]:
        if ":" not in spec:
            return _json({"status": "error", "error": f"聚合格式错误：{spec!r}，应为 列名:函数"})
        col, func = [x.strip() for x in spec.split(":", 1)]
        real = cols_map.get(col.lower())
        if real is None:
            return _json({"status": "error", "error": f"聚合列 {col!r} 不存在",
                          "provenance": r["provenance"], "available_columns": list(df.columns)})
        # sum/mean/min/max/median 必须是数值；count/nunique 任意列都可
        numeric_funcs = {"sum", "mean", "min", "max", "median"}
        if func in numeric_funcs:
            if not pd.api.types.is_numeric_dtype(df[real]):
                converted = pd.to_numeric(df[real], errors="coerce")
                converted_ratio = float(converted.notna().mean())
                if converted_ratio < 0.5:
                    return _json({"status": "error",
                                  "error": f"聚合列 {real} 不是数值类型（转换成功率 {converted_ratio:.0%}），禁止对其执行 {func}"})
                df = df.copy()
                df[real] = converted
        agg_spec.setdefault(real, []).append(func)

    try:
        grouped = df.groupby(group_cols, as_index=False).agg(agg_spec)
    except Exception as e:
        return _json({"status": "error", "error": f"groupby 执行失败：{e}", "provenance": r["provenance"]})

    # MultiIndex 列拍平
    if isinstance(grouped.columns, pd.MultiIndex):
        grouped.columns = [c[0] if c[1] in ("", c[0]) else f"{c[0]}_{c[1]}" for c in grouped.columns]

    totals: dict[str, Any] = {}
    for col, funcs in agg_spec.items():
        for f in funcs:
            total_name = f"{col}_{f}" if f != "sum" else col
            if f == "sum":
                totals[total_name] = float(df[col].sum(skipna=True))

    sample = grouped.head(MAX_ROWS_IN_CONTEXT).fillna("").to_dict(orient="records")
    return _json({
        "status": "ok",
        "provenance": {**r["provenance"], "group_by": group_cols, "aggregate": agg_spec},
        "grouped_result_preview": sample,
        "grouped_result_total": totals,
        "grouped_rows": int(len(grouped)),
    })


# ---------------------------------------------------------------------------
# 工具：描述性统计
# ---------------------------------------------------------------------------
@tool
def describe_columns(columns: str = "") -> str:
    """对当前 DataFrame 的数值列给出均值/极值/分位数。

    Args:
        columns: 可选，逗号分隔。留空则统计所有数值列。
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    df = r["df"]
    cols_map = {c.lower(): c for c in df.columns}
    if columns.strip():
        targets = [cols_map[c.strip().lower()] for c in columns.split(",") if c.strip().lower() in cols_map]
    else:
        targets = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not targets:
        return _json({"status": "error", "error": "没有可统计的数值列", "provenance": r["provenance"]})

    stats = df[targets].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(4)
    # describe 的 columns 是单层（列名），index 是 ['count','mean','std','min','10%','25%','50%','75%','90%','max']
    stats_dict = {}
    for col in stats.columns:
        stats_dict[str(col)] = {str(idx): float(v) for idx, v in stats[col].items() if v == v}  # NaN check
    return _json({"status": "ok", "provenance": r["provenance"], "numeric_stats": stats_dict})


# ---------------------------------------------------------------------------
# 工具：排序筛选预览
# ---------------------------------------------------------------------------
@tool
def sort_preview(sort_by: str, ascending: bool = True, top_n: int = 20) -> str:
    """按某列排序后返回前 N 行预览（用于快速发现异常 / 头部数据）。"""
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    df = r["df"]
    mapping = {c.lower(): c for c in df.columns}
    real = mapping.get(sort_by.lower())
    if real is None:
        return _json({"status": "error", "error": f"列 {sort_by!r} 不存在"})
    sorted_df = df.sort_values(by=real, ascending=ascending).head(top_n)
    return _json({"status": "ok", "provenance": r["provenance"], "preview": sorted_df.fillna("").to_dict(orient="records")})


# ---------------------------------------------------------------------------
# 工具：过滤（字符串匹配 / 范围）
# ---------------------------------------------------------------------------
@tool
def filter_rows(column: str, op: str, value: str) -> str:
    """按条件过滤数据并注册为当前 DataFrame。

    Args:
        column: 列名
        op: 比较操作：eq / ne / gt / ge / lt / le / contains / is_null / not_null
        value: 比较值（字符串会自动尝试转数值）
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    df = r["df"]
    mapping = {c.lower(): c for c in df.columns}
    real = mapping.get(column.lower())
    if real is None:
        return _json({"status": "error", "error": f"列 {column!r} 不存在",
                      "available_columns": list(df.columns)})

    try:
        if op == "is_null":
            mask = df[real].isna()
        elif op == "not_null":
            mask = df[real].notna()
        else:
            numeric_val: Any
            try:
                numeric_val = float(value)
            except ValueError:
                numeric_val = value
            if op == "eq": mask = df[real] == numeric_val
            elif op == "ne": mask = df[real] != numeric_val
            elif op == "gt": mask = pd.to_numeric(df[real], errors="coerce") > numeric_val
            elif op == "ge": mask = pd.to_numeric(df[real], errors="coerce") >= numeric_val
            elif op == "lt": mask = pd.to_numeric(df[real], errors="coerce") < numeric_val
            elif op == "le": mask = pd.to_numeric(df[real], errors="coerce") <= numeric_val
            elif op == "contains": mask = df[real].astype(str).str.contains(value, na=False)
            else: return _json({"status": "error", "error": f"未知 op {op!r}"})
    except Exception as e:
        return _json({"status": "error", "error": f"过滤执行失败：{e}"})

    new_df = df[mask].copy().reset_index(drop=True)
    new_prov = {**r["provenance"], "rows": int(len(new_df)), "filter": {"column": real, "op": op, "value": value}}
    register(new_df, new_prov)
    return _json({"status": "ok", "provenance": new_prov, "rows_before": int(len(df)), "rows_after": int(len(new_df))})


# ---------------------------------------------------------------------------
# 工具：导出当前结果
# ---------------------------------------------------------------------------
@tool
def export_current(path: str, format: str = "csv") -> str:
    """将当前 DataFrame 导出到磁盘（统一保存到当前项目文件夹）。

    Args:
        path: 导出文件名，例如 `result.csv`。只取文件名，目录由当前项目决定
        format: csv / xlsx
    """
    r = get_registered()
    if not r:
        return _json({"status": "error", "error": "没有已加载的 DataFrame"})
    fmt = format.strip().lower()
    if fmt not in {"csv", "xlsx"}:
        return _json({"status": "error", "error": "导出格式仅支持 csv / xlsx"})
    base = get_output_dir()
    base.mkdir(parents=True, exist_ok=True)
    out = (base / Path(path).name).with_suffix(f".{fmt}")
    try:
        if fmt == "xlsx":
            r["df"].to_excel(out, index=False)
        else:
            r["df"].to_csv(out, index=False, encoding="utf-8-sig")
    except Exception as e:
        return _json({"status": "error", "error": f"导出失败：{e}"})
    return _json({"status": "ok", "exported_to": str(out), "provenance": r["provenance"], "rows": int(len(r["df"]))})


# ---------------------------------------------------------------------------
# 工具：多文件合并
# ---------------------------------------------------------------------------
@tool
def merge_files(file_paths: str, on_columns: str = "", how: str = "append") -> str:
    """加载多个文件并合并为当前 DataFrame。

    Args:
        file_paths: 逗号分隔的文件路径
        on_columns: join 模式下的关联键（逗号分隔）；append 模式留空
        how: append（纵向拼接）或 join（横向按键）
    """
    from app.loader import read_file
    paths = [p.strip() for p in file_paths.split(",") if p.strip()]
    loads = [read_file(p) for p in paths]
    ok_loads = [l for l in loads if l.get("status") == "ok"]
    bad_loads = [{"path": p, "error": l.get("error")} for p, l in zip(paths, loads) if l.get("status") != "ok"]

    if not ok_loads:
        return _json({"status": "error", "error": "所有文件加载失败", "failures": bad_loads})

    dfs = []
    for ld in ok_loads:
        d = ld["_df"].copy()
        d["__source_file__"] = ld["provenance"]["file"]
        if ld["provenance"].get("sheet"):
            d["__source_sheet__"] = ld["provenance"]["sheet"]
        dfs.append(d)

    try:
        if how == "join" and on_columns.strip():
            keys = [k.strip() for k in on_columns.split(",") if k.strip()]
            merged = dfs[0]
            for d in dfs[1:]:
                merged = merged.merge(d, on=keys, how="left")
        else:
            merged = pd.concat(dfs, ignore_index=True, sort=False)
    except Exception as e:
        return _json({"status": "error", "error": f"合并失败：{e}", "failures": bad_loads})

    prov = {"files": [l["provenance"]["file"] for l in ok_loads], "rows": int(len(merged)), "cols": int(merged.shape[1])}
    register(merged, prov)
    return _json({"status": "ok", "provenance": prov, "skipped_failures": bad_loads})


# ---------------------------------------------------------------------------
# 工具：文档解析（智谱文件解析 API）
# ---------------------------------------------------------------------------
@tool
def parse_document(path: str, tool_type: str = "lite") -> str:
    """解析 PDF / Word / PPT / 图片 / Markdown 等非表格文件，提取可检索的正文。

    解析结果会注册到当前会话，后续用 read_document 读取细节。
    同一文件重复调用会复用已解析结果，不会重复计费。

    Args:
        path: 文件的绝对路径或相对项目根目录的路径，例如 `.data/uploads/xxx.pdf`
        tool_type: 解析服务：lite（免费，常见办公文档）/ expert（仅 PDF，精度高）/ prime（复杂版式）
    """
    from pathlib import Path
    from app.zhipu_parser import parse_file

    p = Path(path)
    if not p.exists():
        return _json({"status": "error", "error": f"文件不存在：{p}"})
    if p.name in _DOCS:
        doc = _DOCS[p.name]
        return _json({
            "status": "ok",
            "provenance": doc["provenance"],
            "chars": len(doc["content"]),
            "preview": doc["content"][:_DOC_PREVIEW],
            "note": "该文件已解析，以下为复用结果；完整正文请用 read_document 按区间读取。",
        })

    res = parse_file(str(p), tool_type=tool_type)
    if res["status"] != "ok":
        return _json(res)
    register_document(p.name, res["content"], res["provenance"])
    return _json({
        "status": "ok",
        "provenance": res["provenance"],
        "chars": len(res["content"]),
        "preview": res["content"][:_DOC_PREVIEW],
        "preview_chars": min(len(res["content"]), _DOC_PREVIEW),
        "note": "preview 只是正文开头；引用正文其余部分前必须调用 read_document。",
    })


@tool
def list_documents() -> str:
    """列出当前会话已解析的文档及其字符数、解析服务、task_id。"""
    if not _DOCS:
        return _json({"status": "error", "error": "当前会话还没有已解析的文档"})
    return _json({
        "status": "ok",
        "documents": [
            {"file": name, "chars": len(d["content"]), **d["provenance"]}
            for name, d in _DOCS.items()
        ],
    })


@tool
def read_document(name: str = "", start: int = 0, length: int = 4000, keyword: str = "") -> str:
    """读取已解析文档的正文片段。

    Args:
        name: 文档文件名；留空且只有一个文档时自动选用该文档
        start: 起始字符位置（从 0 开始）
        length: 读取长度（默认 4000 字符）
        keyword: 若填写，则返回该关键词在正文中的所有命中位置及上下文（忽略 start / length）
    """
    if not _DOCS:
        return _json({"status": "error", "error": "当前会话还没有已解析的文档，请先调用 parse_document"})
    key = name.strip()
    if not key:
        if len(_DOCS) == 1:
            key = next(iter(_DOCS))
        else:
            return _json({"status": "error", "error": "存在多个文档，必须指定 name",
                          "available_documents": list(_DOCS)})
    doc = _DOCS.get(key)
    if doc is None:
        return _json({"status": "error", "error": f"文档 {key!r} 未解析",
                      "available_documents": list(_DOCS)})

    content: str = doc["content"]
    prov = doc["provenance"]

    if keyword.strip():
        kw = keyword.strip()
        hits, pos = [], content.find(kw)
        while pos != -1 and len(hits) < 20:
            hits.append({"position": pos, "context": content[max(0, pos - 200): pos + len(kw) + 200]})
            pos = content.find(kw, pos + len(kw))
        return _json({"status": "ok", "provenance": prov, "keyword": kw,
                      "hit_count": len(hits), "hits": hits})

    s = max(0, int(start))
    e = min(len(content), s + max(1, int(length)))
    return _json({
        "status": "ok",
        "provenance": prov,
        "range": [s, e],
        "total_chars": len(content),
        "content": content[s:e],
        "has_more": e < len(content),
    })


# ---------------------------------------------------------------------------
# 工具：网络搜索（智谱 Web Search API）
# ---------------------------------------------------------------------------
@tool
def web_search(
    query: str,
    count: int = 10,
    engine: str = "search_std",
    recency: str = "noLimit",
    intent: bool = True,
) -> str:
    """调用智谱网络搜索获取实时、可溯源的网页结果。

    查询近期新闻、产品价格、官网说明、API 文档、行业数据等**需要联网**的信息时调用；
    纯文本分析或已上传文件的内容不要调本工具，直接用 describe_dataframe / read_document。

    Args:
        query: 要搜索的内容，建议 ≤70 字符
        count: 返回条数 1-50，默认 10
        engine: search_std（智谱基础）/ search_pro（智谱高阶）/ search_pro_sogou / search_pro_quark
        recency: oneDay / oneWeek / oneMonth / oneYear / noLimit
        intent: True 先做意图识别；False 直接搜索
    """
    from app.zhipu_search import web_search as _search

    r = _search(
        query=query,
        search_engine=engine,
        search_intent=intent,
        count=count,
        recency_filter=recency,
    )
    if r["status"] != "ok":
        return _json(r)

    register_search(r)
    summary = {
        "request_id": r.get("request_id"),
        "intent": r.get("intent"),
        "elapsed_s": r.get("elapsed_s"),
        "note": r.get("note"),
    }
    preview = []
    for item in r["results"][:min(count, 12)]:
        preview.append({
            "title": item["title"],
            "media": item["media"],
            "publish_date": item["publish_date"],
            "link": item["link"],
            "content": item["content"][:280],
        })
    return _json({
        "status": "ok",
        "summary": summary,
        "count": r["count"],
        "results": preview,
        "note": "每条结果都带 link；关键事实要附来源链接，不要只给标题。",
    })


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _json(obj: Any) -> str:
    """比 json.dumps 更宽松：numpy / datetime / tuple 自动转换。"""
    import numpy as np
    from datetime import datetime, date

    def default(o: Any):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, (datetime, date)): return o.isoformat()
        if isinstance(o, tuple): return list(o)
        return str(o)

    import json as _j
    return _j.dumps(obj, ensure_ascii=False, default=default)


def all_tools():
    """暴露给 Agent 的工具列表（保持稳定顺序）。"""
    return [
        create_dataframe_from_text,
        load_excel_file,
        parse_document,
        list_documents,
        read_document,
        web_search,
        merge_files,
        describe_dataframe,
        select_columns,
        groupby_aggregate,
        describe_columns,
        sort_preview,
        filter_rows,
        export_current,
    ]
