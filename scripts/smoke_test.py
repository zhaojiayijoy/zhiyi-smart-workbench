"""自测脚本：不用 LLM，只验证 loader / tools / gate 的确定性链路。

运行：
    python scripts/smoke_test.py
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from openpyxl import Workbook

from app.loader import read_file, quality_gate
from app.tools import (
    load_excel_file, describe_dataframe, groupby_aggregate,
    describe_columns, sort_preview, filter_rows, register, get_registered, _json,
)


def _make_fixture(path: Path) -> None:
    """生成一份真实的多 sheet + 脏数据 Excel，用于回归。"""
    wb = Workbook()

    # Sheet1: 完整数据，日期格式混杂，金额文本化
    ws = wb.active
    ws.title = "2024_01"
    ws.append(["订单编号", "下单日期", "区域", "金额(元)", "销售员"])
    rows = [
        ("SO20240101", "2024/01/03", "华东", "¥1,280.50", "张伟"),
        ("SO20240102", "2024年1月5日", "华南", "¥3,490.00", "李娜"),
        ("SO20240103", "2024-01-07", "华北", "¥892.30", "张伟"),
        ("SO20240104", "2024.1.11", "华东", "¥2,150.00", "王强"),
        ("SO20240105", "20240115", "华南", "¥620.75", "李娜"),
        ("SO20240106", "2024-01-18", "", "¥1,999.99", "张伟"),   # 地区空
        ("SO20240107", "2024-13-45", "华北", "¥4,100.00", "王强"), # 日期非法
        ("SO20240108", "2024/01/22", "华东", "¥980.20", "李娜"),
        ("SO20240109", "2024-01-25", "西南", "¥2,780.00", "张伟"),
        ("SO20240110", "2024-01-28", "华南", "¥1,560.45", "王强"),
    ]
    for r in rows: ws.append(list(r))

    # Sheet2: 另一个月，字段名不同
    ws2 = wb.create_sheet("2024_02")
    ws2.append(["订单号", "日期", "区域", "金额"])
    rows2 = [
        ("SO20240201", "2024-02-02", "华东", 2100.50),
        ("SO20240202", "2024-02-06", "华南", 1450.00),
        ("SO20240203", "2024-02-10", "华北", 3200.00),
        ("SO20240204", "2024-02-14", "", 980.00),          # 地区空
        ("SO20240205", "待补", "西南", 2780.00),            # 日期非法
        ("SO20240206", "2024-02-22", "华东", 4100.00),
        ("SO20240207", "2024-02-26", "华南", 620.75),
    ]
    for r in rows2: ws2.append(list(r))

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> int:
    fixture = ROOT / "demo" / "sales_dirty.xlsx"
    _make_fixture(fixture)
    print(f"[1] fixture: {fixture}")

    # ----- 1) loader -----
    print("\n[2] read_file Sheet1 ...")
    ld = read_file(str(fixture), sheet_name="2024_01")
    assert ld["status"] == "ok", ld
    df = ld["_df"]
    print(f"    shape={df.shape}, cols={list(df.columns)}")
    print(f"    sample row 0: {dict(df.iloc[0])}")

    # ----- 2) 质量闸门 -----
    print("\n[3] quality_gate ...")
    gate = quality_gate(ld, required=["订单编号", "下单日期", "金额(元)"])
    print(f"    {gate['message']}")
    assert gate["ok"], gate

    # ----- 3) 工具调用（直接调用，不用 Agent） -----
    print("\n[4] register + describe + groupby ...")
    register(df, ld["provenance"])

    desc = describe_dataframe.invoke({})
    print(f"    describe sample keys: {json.loads(desc).keys()}")

    # 金额是文本含 ¥ 和千分位，先转
    df2 = df.copy()
    df2["金额"] = df2["金额(元)"].astype(str).str.replace("[¥,\\s]", "", regex=True).apply(float)
    df2 = df2.rename(columns={"订单编号": "订单号", "下单日期": "销售日期", "区域": "地区"})
    register(df2, {**ld["provenance"], "notes": "金额转换、字段重命名"})

    gb = groupby_aggregate.invoke({"group_by": "地区", "aggregate": "金额:sum,订单号:count"})
    gb_j = json.loads(gb)
    assert gb_j["status"] == "ok", gb_j
    print(f"    groupby region total={gb_j['grouped_result_total']}")
    print(f"    groupby preview={gb_j['grouped_result_preview']}")

    total_amount = sum(r["金额_sum"] for r in gb_j["grouped_result_preview"])
    # 注意：原始 df2 里 region="" 的行不会出现在 groupby(地区) 结果里，
    # 所以总汇总只统计非空分组；这是正确行为。
    non_null_total = df2.loc[df2["地区"].notna() & (df2["地区"] != ""), "金额"].sum()
    assert abs(total_amount - non_null_total) < 0.01, f"汇总不匹配 {total_amount} vs {non_null_total}"
    print(f"    ✅ 聚合可复算（排除空分组后），差异 < 0.01")

    # ----- 4) 统计 describe -----
    print("\n[5] describe_columns ...")
    stats = describe_columns.invoke({"columns": "金额"})
    st_j = json.loads(stats)
    print(f"    mean={st_j['numeric_stats']['金额']['mean']}, max={st_j['numeric_stats']['金额']['max']}")

    # ----- 5) sort_preview -----
    print("\n[6] sort_preview top-5 by 金额 ...")
    sp = sort_preview.invoke({"sort_by": "金额", "ascending": False, "top_n": 5})
    sp_j = json.loads(sp)
    print(f"    top 5: {[r['订单号'] + ':' + str(r['金额']) for r in sp_j['preview']]}")

    # ----- 6) filter + 导出 -----
    print("\n[7] filter 地区=华东 + 导出 csv ...")
    f2 = filter_rows.invoke({"column": "地区", "op": "eq", "value": "华东"})
    f2_j = json.loads(f2)
    print(f"    rows_before={f2_j['rows_before']}, rows_after={f2_j['rows_after']}")

    out = ROOT / ".data" / "out" / "east_china.csv"
    ex = __import__("app.tools", fromlist=["export_current"]).export_current.invoke({"path": str(out), "format": "csv"})
    ex_j = json.loads(ex)
    assert ex_j["status"] == "ok" and out.exists(), ex_j
    print(f"    ✅ exported {out} ({out.stat().st_size} bytes)")

    # ----- 7) CSV 回读 -----
    print("\n[8] CSV round-trip read_file ...")
    ld_csv = read_file(str(out))
    assert ld_csv["status"] == "ok", ld_csv
    print(f"    shape={ld_csv['_df'].shape}")

    # ----- 8) 伪造数据禁止 -----
    print("\n[9] 错误通道：缺失列 ...")
    gb_bad = groupby_aggregate.invoke({"group_by": "不存在的列", "aggregate": "金额:sum"})
    gb_bad_j = json.loads(gb_bad)
    assert gb_bad_j["status"] == "error", gb_bad_j
    print(f"    ✅ 返回 error：{gb_bad_j['error']}")

    print("\n=== SMOKE TEST PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
