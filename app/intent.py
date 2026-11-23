"""任务意图识别：把首页输入的一句话任务分配到对应的工作界面。

纯规则打分，不调用外部模型，结果可解释（返回命中的关键词）。
"""
from __future__ import annotations

from typing import Any

# 关键词表：按任务类型归类，统一落到「教学工具」（表格处理 / 数据分析 / 报告撰写
# 已合并进同一界面，任务类型仍分开保留，便于顶部横幅说明）。
_RULES: list[tuple[str, str, list[str]]] = [
    ("教学工具", "报告撰写", [
        "报告", "汇报", "总结", "周报", "月报", "复盘", "方案", "纪要",
        "ppt", "演示", "幻灯片", "写成", "撰写文稿", "生成文案", "对外说明",
    ]),
    ("教学工具", "数据分析", [
        "统计", "汇总", "对比", "差异", "趋势", "占比", "比例", "平均", "均值",
        "总计", "求和", "计数", "分组", "排名", "排序", "相关性", "异常值",
        "同比", "环比", "分布", "透视", "增长", "波动",
    ]),
    ("教学工具", "表格处理", [
        "清洗", "去重", "重复", "合并", "拆分", "筛选", "格式", "缺失", "空值",
        "列名", "表头", "单元格", "导入", "上传", "读取", "多表", "连接", "字段",
        "工作表", "sheet", "excel", "csv", "表格", "整表", "列", "行",
    ]),
]

_DATA_WORDS = set(_RULES[1][2]) | set(_RULES[2][2])


def classify(text: str) -> dict[str, Any]:
    """识别任务类型。

    Returns:
        {
          module: 目标界面（教学工具 / AI 助手）,
          type: 任务类型中文名（表格处理 / 数据分析 / 报告撰写）,
          keywords: 命中的关键词列表,
          needs_data: 是否需要已上传的数据,
          score: 各任务类型的命中数明细,
        }
    """
    t = (text or "").lower()
    scored: list[tuple[int, int, str, str, list[str]]] = []
    for idx, (module, type_name, words) in enumerate(_RULES):
        hits = [w for w in words if w in t]
        if hits:
            scored.append((len(hits), -idx, module, type_name, hits))

    if not scored:
        return {
            "module": "AI 助手",
            "type": "通用问答",
            "keywords": [],
            "needs_data": False,
            "score": {},
        }

    # 命中数最多者胜；同分按 _RULES 顺序（报告 > 分析 > 表格）
    _n, _neg_idx, module, type_name, hits = max(scored, key=lambda r: (r[0], r[1]))
    return {
        "module": module,
        "type": type_name,
        "keywords": hits,
        "needs_data": any(w in _DATA_WORDS for w in hits),
        "score": {r[3]: r[0] for r in scored},
    }
