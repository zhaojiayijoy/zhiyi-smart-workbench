"""数据加载与质量闸门。

所有工具函数都遵循同一条契约：
    返回 dict，包含 status（ok | error）、provenance、payload 或 error/missing_fields。
绝不抛异常给调用方，绝不返回伪造 / 推断的数据。
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from app.config import MAX_ROWS_IN_CONTEXT


# ---------------------------------------------------------------------------
# Provenance 记录 —— 每条输出必须可追溯
# ---------------------------------------------------------------------------
@dataclass
class Provenance:
    file: str                     # 原始文件名
    sheet: Optional[str] = None   # sheet 名（CSV 为 None）
    rows: int = 0                 # 处理的行数
    cols: int = 0                 # 处理的列数
    columns: list[str] = field(default_factory=list)  # 实际涉及的列

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def _header_row_detection(df: pd.DataFrame, max_scan: int = 15) -> int:
    """pandas 自动推断表头行的启发式。

    真实办公文件经常在表格顶部有多行说明、标题、空白行。
    默认尝试 header=None，扫描前 N 行中，第一个「非空且唯一列名」的位置。
    """
    for i in range(max_scan):
        row = df.iloc[i].astype(str).tolist()
        non_empty = [c for c in row if c and c.lower() != "nan"]
        if not non_empty:
            continue
        if len(set(non_empty)) == len(non_empty) and len(non_empty) >= 2:
            return i
    return 0


def read_file(path: str | Path, sheet_name: int | str = 0) -> dict[str, Any]:
    """统一入口：支持 xlsx / xls / csv。

    返回结构：
        ok=True  -> {status:"ok", provenance, df_preview:list[dict], summary}
        ok=False -> {status:"error", error:str, provenance(部分), missing_fields:list[str]}
    """
    p = Path(path)
    if not p.exists():
        return {"status": "error", "error": f"文件不存在：{p}", "provenance": Provenance(file=p.name).dict()}
    ext = p.suffix.lower()
    if ext not in {".xlsx", ".xls", ".csv"}:
        return {"status": "error",
                "error": f"不支持的扩展名 {ext}，仅允许 .xlsx / .xls / .csv",
                "provenance": Provenance(file=p.name).dict()}

    prov = Provenance(file=p.name)

    try:
        encoding: str | None = None
        if ext in {".xlsx", ".xls"}:
            xl = pd.ExcelFile(p)
            prov.sheet = xl.sheet_names[sheet_name] if isinstance(sheet_name, int) and sheet_name < len(xl.sheet_names) else sheet_name
            try:
                raw = pd.read_excel(xl, sheet_name=prov.sheet, header=None)
            except Exception as e:
                return {"status": "error",
                        "error": f"读取工作表 {prov.sheet} 失败：{e}",
                        "provenance": prov.dict(),
                        "missing_fields": [str(e)]}
            header_row = _header_row_detection(raw)
            df = pd.read_excel(xl, sheet_name=prov.sheet, header=header_row)
        else:  # csv
            # 先尝试 utf-8，再 utf-8-sig，最后 gbk / gb18030
            encoding = None
            for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin1"):
                try:
                    df = pd.read_csv(p, encoding=enc)
                    encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            if encoding is None:
                return {"status": "error",
                        "error": "CSV 编码不可识别（尝试 utf-8 / utf-8-sig / gbk / gb18030 均失败）",
                        "provenance": prov.dict(),
                        "missing_fields": ["encoding"]}

        # 清理：Unnamed: n → 重命名为 col_n；重复列名 → 去重
        df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed:\s*\d+$")]
        seen: dict[str, int] = {}
        new_cols = []
        for c in df.columns.astype(str):
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}__{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        df.columns = new_cols
        df = df.dropna(how="all").reset_index(drop=True)

        prov.rows = int(len(df))
        prov.cols = int(df.shape[1])
        prov.columns = list(df.columns)

        summary = {
            "shape": [prov.rows, prov.cols],
            "columns": list(df.columns),
            "dtypes": {c: str(df[c].dtype) for c in df.columns},
            # null_counts 是空值条数；null_pcts 是缺失率百分比（0-100）。
            # 两者必须同时给出，避免模型把条数误当成百分比。
            "null_counts": {c: int(df[c].isna().sum()) for c in df.columns},
            "null_pcts": {c: round(float(df[c].isna().mean()) * 100, 1) for c in df.columns},
            "unique_counts": {c: int(df[c].nunique(dropna=True)) for c in df.columns},
            "sample": df.head(3).fillna("").to_dict(orient="records"),
        }
        preview = df.head(MAX_ROWS_IN_CONTEXT).fillna("").to_dict(orient="records")
        return {
            "status": "ok",
            "provenance": prov.dict(),
            "encoding": encoding,
            "summary": summary,
            "df_preview": preview,
            "_df": df,
        }

    except Exception as e:
        return {"status": "error",
                "error": f"读取文件失败：{e.__class__.__name__}: {e}",
                "provenance": prov.dict(),
                "missing_fields": [str(e)]}


# ---------------------------------------------------------------------------
# 质量闸门
# ---------------------------------------------------------------------------
def quality_gate(load_result: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """在允许 LLM 进入分析前执行。

    Args:
        load_result: read_file 的返回值。
        required: 关键列名列表。列名匹配大小写不敏感。

    Returns:
        {ok, missing_columns, empty_columns, null_rate_columns, message}
    """
    if load_result.get("status") != "ok":
        return {"ok": False, "missing_columns": [], "empty_columns": [], "message": load_result.get("error", "文件未成功加载")}

    df: pd.DataFrame = load_result["_df"]
    cols_lower = {c.lower(): c for c in df.columns}

    missing, empty, null_rate = [], [], []
    for rq in required:
        real = cols_lower.get(rq.lower())
        if real is None:
            missing.append(rq)
            continue
        non_null = df[real].dropna()
        if len(non_null) == 0:
            empty.append(real)
            continue
        null_pct = float(df[real].isna().mean())
        if null_pct > 0.8:
            null_rate.append(f"{real}({null_pct:.0%}空)")

    return {
        "ok": not (missing or empty),
        "missing_columns": missing,
        "empty_columns": empty,
        "null_rate_columns": null_rate,
        "message": (
            "通过：所有关键列均存在且含非空值。"
            if not (missing or empty)
            else f"阻断：缺失列={missing}；全空列={empty}。LLM 不得继续分析。"
        ),
    }


# ---------------------------------------------------------------------------
# 多文件合并（真实场景）
# ---------------------------------------------------------------------------
def merge_loads(loads: list[dict[str, Any]], on: Optional[list[str]] = None, how: str = "append") -> dict[str, Any]:
    """合并多个已加载的文件。

    how="append"：纵向拼接（要求列名对齐）；
    how="join"  ：横向按键连接。

    只接收 read_file 返回的 ok 结果，其余自动跳过并在 provenance 中说明。
    """
    dfs: list[pd.DataFrame] = []
    prov_files: list[str] = []
    for ld in loads:
        if ld.get("status") != "ok":
            continue
        d = ld["_df"].copy()
        d["__source_file__"] = ld["provenance"]["file"]
        if ld["provenance"].get("sheet"):
            d["__source_sheet__"] = ld["provenance"]["sheet"]
        dfs.append(d)
        prov_files.append(ld["provenance"]["file"])

    if not dfs:
        return {"status": "error", "error": "没有可合并的已加载数据", "provenance": {"files": []}}

    try:
        if how == "join":
            if not on:
                return {"status": "error", "error": "join 模式必须提供 on（关联键）", "provenance": {"files": prov_files}}
            merged = dfs[0]
            for d in dfs[1:]:
                merged = merged.merge(d, on=on, how="left")
        else:
            merged = pd.concat(dfs, ignore_index=True, sort=False)

        return {
            "status": "ok",
            "provenance": {"files": prov_files, "rows": int(len(merged)), "cols": int(merged.shape[1])},
            "_df": merged,
        }
    except Exception as e:
        return {"status": "error", "error": f"合并失败：{e}", "provenance": {"files": prov_files}}
